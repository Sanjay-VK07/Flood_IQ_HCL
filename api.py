"""
FloodIQ — FastAPI Backend

Exposes existing Python business logic (SQLite persistence, Open-Meteo weather,
explainable risk engine, Groq AI triage + deterministic fallback, and
vulnerability-first response recommendation) over a typed REST API.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ai_engine import get_ai_status, triage_incident
from auth import (
    create_access_token,
    get_current_user,
    get_optional_user,
    require_roles,
    revoke_token,
    verify_password,
)
from config import (
    INCIDENT_CATEGORIES,
    OFFLINE_MODE,
    PRIORITY_WEIGHT_HAZARD,
    PRIORITY_WEIGHT_PEOPLE,
    PRIORITY_WEIGHT_SEVERITY,
    PRIORITY_WEIGHT_STRANDED,
    PRIORITY_WEIGHT_VULNERABILITY,
    RAINFALL_NORM_CEILING,
    RISK_WEIGHT_DRAINAGE,
    RISK_WEIGHT_LOWLYING,
    RISK_WEIGHT_RAINFALL,
    STATUS_TRANSITIONS,
)
from database import (
    create_incident,
    get_incident,
    get_incident_by_tracking,
    get_incident_updates,
    get_response_teams,
    get_user_by_email,
    get_zones,
    init_db,
    list_incidents,
    list_incidents_for_citizen,
    list_incidents_for_team,
    reset_demo_data,
    update_incident_workflow,
)
from response_engine import calculate_priority, recommend_team
from risk_engine import evaluate_zones, get_risk_summary
from data_pipeline import (
    TRAINING_CSV_PATH,
    build_training_dataset,
    get_dataset_status,
)
from geo_context import get_rainviewer_radar, get_zone_osm_context
from weather import get_rainfall_for_zones, get_weather_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="FloodIQ Operations API",
    description="Backend API for FloodIQ — Urban Flood Intelligence & Emergency Response",
    version="1.0.0",
    lifespan=lifespan,
)

_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class SimulateRiskRequest(BaseModel):
    rainfall_mm: float = Field(default=20.0, ge=0.0, le=300.0)
    use_simulation: bool = True


class CreateIncidentRequest(BaseModel):
    zone_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=3)
    location_text: str = ""
    reported_category: str = "Other"
    people_affected: int = Field(default=0, ge=0, le=1000)
    photo_data_url: Optional[str] = Field(default=None, max_length=700000)


class ApproveDispatchRequest(BaseModel):
    team_id: str = Field(..., min_length=1)
    note: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., min_length=1)
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evaluate_risk_context(rainfall_mm: Optional[float], use_simulation: bool) -> dict[str, Any]:
    zones = get_zones()
    sim_val = float(rainfall_mm) if (use_simulation and rainfall_mm is not None) else (20.0 if use_simulation else None)
    rainfall_map = get_rainfall_for_zones(zones, simulated_rainfall_mm=sim_val)
    evaluated = evaluate_zones(zones, rainfall_map)
    summary = get_risk_summary(evaluated)

    sources = {z["rainfall_source"] for z in evaluated}
    if use_simulation:
        mode = "simulation"
        source_label = f"Simulated ({sim_val:.0f} mm)"
    elif "live_open_meteo" in sources:
        mode = "live_open_meteo"
        source_label = "Live Open-Meteo API"
    elif "cached" in sources:
        mode = "cached"
        source_label = "Open-Meteo (Cached)"
    else:
        mode = "default_fallback"
        source_label = "Offline Default Fallback"

    avg_rain = round(sum(z["rainfall_mm"] for z in evaluated) / max(len(evaluated), 1), 1)

    # Enrich zones with real cached SRTM elevation & historical rainfall context when available
    ds_status = get_dataset_status()
    elev_by_zone: dict[str, Any] = {}
    if ds_status.get("available"):
        for src in ds_status.get("sources", []):
            if "elevations_by_zone" in src:
                elev_by_zone = src["elevations_by_zone"]
                break

    for z in evaluated:
        z["elevation_m"] = elev_by_zone.get(z["zone_id"])

    return {
        "mode": mode,
        "source_label": source_label,
        "use_simulation": use_simulation,
        "rainfall_mm": sim_val if use_simulation else avg_rain,
        "model_mode": "explainable_heuristic_with_real_telemetry",
        "dataset_available": bool(ds_status.get("available")),
        "zones": evaluated,
        "summary": summary,
    }


def _priority_breakdown_for_incident(inc: dict[str, Any]) -> dict[str, Any]:
    return calculate_priority({
        "ai_category": inc.get("ai_category") or inc.get("reported_category") or "Other",
        "ai_urgency": inc.get("ai_urgency") or "Medium",
        "people_affected": inc.get("people_affected", 0),
        "vulnerable_flag": bool(inc.get("vulnerable_flag")),
        "stranded": bool(inc.get("stranded")),
        "unable_to_evacuate": bool(inc.get("unable_to_evacuate")),
        "immediate_hazard": bool(inc.get("immediate_hazard")),
    })


def _ensure_incident_access(inc: dict[str, Any], user: dict[str, Any]) -> None:
    role = user.get("role")
    if role == "authority":
        return
    if role == "citizen" and inc.get("created_by_user_id") == user.get("user_id"):
        return
    if role == "response_team" and user.get("team_id") and inc.get("assigned_team_id") == user.get("team_id"):
        return
    raise HTTPException(status_code=403, detail="Not authorized to access this incident.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "floodiq-api"}


@app.post("/api/auth/login")
def api_login(payload: LoginRequest) -> dict[str, Any]:
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    public_user = {
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "team_id": user["team_id"],
    }
    token = create_access_token(public_user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": public_user,
    }


@app.post("/api/auth/logout")
def api_logout(authorization: Optional[str] = Header(default=None)) -> dict[str, str]:
    if authorization and authorization.lower().startswith("bearer "):
        revoke_token(authorization[7:].strip())
    return {"status": "logged_out"}


@app.get("/api/auth/me")
def api_me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": user}


@app.get("/api/dashboard")
def get_dashboard(
    rainfall_mm: Optional[float] = Query(default=20.0, ge=0.0, le=300.0),
    use_simulation: bool = Query(default=True),
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> dict[str, Any]:
    risk_ctx = _evaluate_risk_context(rainfall_mm, use_simulation)
    incidents = list_incidents()
    teams = get_response_teams()

    recent_events: list[dict[str, Any]] = []
    for inc in incidents:
        for u in get_incident_updates(inc["incident_id"]):
            recent_events.append({
                "update_id": u["update_id"],
                "incident_id": inc["incident_id"],
                "old_status": u["old_status"],
                "new_status": u["new_status"],
                "note": u["note"],
                "updated_at": u["updated_at"],
            })
    recent_events.sort(key=lambda e: e["updated_at"], reverse=True)

    return {
        "weather": {
            "mode": risk_ctx["mode"],
            "source_label": risk_ctx["source_label"],
            "use_simulation": risk_ctx["use_simulation"],
            "rainfall_mm": risk_ctx["rainfall_mm"],
        },
        "risk_summary": risk_ctx["summary"],
        "zones": risk_ctx["zones"],
        "incidents": incidents,
        "teams": teams,
        "recent_activity": recent_events[:10],
    }


@app.get("/api/zones")
def api_get_zones() -> list[dict[str, Any]]:
    return get_zones()


@app.get("/api/risk")
def api_get_risk(
    rainfall_mm: Optional[float] = Query(default=20.0, ge=0.0, le=300.0),
    use_simulation: bool = Query(default=True),
) -> dict[str, Any]:
    return _evaluate_risk_context(rainfall_mm, use_simulation)


@app.post("/api/risk/simulate")
def api_simulate_risk(payload: SimulateRiskRequest) -> dict[str, Any]:
    return _evaluate_risk_context(payload.rainfall_mm, payload.use_simulation)


@app.get("/api/incidents")
def api_list_incidents(
    status: Optional[str] = Query(default=None),
    zone_id: Optional[str] = Query(default=None),
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {}
    if status and status != "All":
        filters["status"] = status
    if zone_id and zone_id != "All":
        filters["zone_id"] = zone_id
    return list_incidents(filters or None)


@app.get("/api/citizen/incidents")
def api_citizen_incidents(
    user: dict[str, Any] = Depends(require_roles("citizen", "authority")),
) -> list[dict[str, Any]]:
    if user["role"] == "authority":
        return list_incidents()
    return list_incidents_for_citizen(user["user_id"])


@app.get("/api/team/incidents")
def api_team_incidents(
    user: dict[str, Any] = Depends(require_roles("response_team")),
) -> dict[str, Any]:
    team_id = user.get("team_id")
    if not team_id:
        raise HTTPException(status_code=403, detail="User is not linked to a response team.")
    teams = {t["team_id"]: t for t in get_response_teams()}
    return {
        "team": teams.get(team_id),
        "incidents": list_incidents_for_team(team_id),
    }


@app.get("/api/public/track/{incident_id}")
def api_public_track_incident(
    incident_id: str,
    tracking_code: str = Query(..., min_length=4),
) -> dict[str, Any]:
    inc = get_incident_by_tracking(incident_id.strip(), tracking_code.strip())
    if not inc:
        raise HTTPException(status_code=404, detail="No incident matches that ID and tracking code.")
    return {
        "incident": {
            "incident_id": inc["incident_id"],
            "tracking_code": inc["tracking_code"],
            "zone_id": inc["zone_id"],
            "location_text": inc["location_text"],
            "reported_category": inc["reported_category"],
            "ai_category": inc["ai_category"],
            "ai_urgency": inc["ai_urgency"],
            "status": inc["status"],
            "assigned_team_id": inc["assigned_team_id"],
            "reporter_type": inc["reporter_type"],
            "created_at": inc["created_at"],
            "updated_at": inc["updated_at"],
        },
        "timeline": get_incident_updates(inc["incident_id"]),
    }


@app.post("/api/incidents", status_code=201)
def api_create_incident(
    payload: CreateIncidentRequest,
    user: Optional[dict[str, Any]] = Depends(get_optional_user),
) -> dict[str, Any]:
    zones = get_zones()
    zone_map = {z["zone_id"]: z for z in zones}
    if payload.zone_id not in zone_map:
        raise HTTPException(status_code=400, detail=f"Unknown zone_id '{payload.zone_id}'")

    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="Incident description cannot be empty")

    if payload.photo_data_url is not None and not payload.photo_data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Uploaded photo must be a valid image data URL")

    zone_name = zone_map[payload.zone_id]["zone_name"]
    triage_res = triage_incident(
        description=payload.description.strip(),
        zone_name=zone_name,
        location_text=payload.location_text.strip(),
        people_affected=payload.people_affected,
    )
    priority_res = calculate_priority(triage_res)

    cat = payload.reported_category if payload.reported_category in INCIDENT_CATEGORIES else "Other"
    inc_payload = {
        "zone_id": payload.zone_id,
        "description": payload.description.strip(),
        "location_text": payload.location_text.strip(),
        "reported_category": cat,
        "people_affected": triage_res["people_affected"],
        "ai_category": triage_res["ai_category"],
        "ai_urgency": triage_res["ai_urgency"],
        "vulnerable_flag": triage_res["vulnerable_flag"],
        "vulnerable_group": triage_res["vulnerable_group"],
        "stranded": triage_res["stranded"],
        "unable_to_evacuate": triage_res["unable_to_evacuate"],
        "immediate_hazard": triage_res["immediate_hazard"],
        "ai_rationale": triage_res["ai_rationale"],
        "triage_mode": triage_res["triage_mode"],
        "priority_score": priority_res["priority_score"],
        "status": "Triaged",
        "created_by_user_id": user["user_id"] if user else None,
        "reporter_type": "authenticated" if user else "guest",
        "photo_data_url": payload.photo_data_url,
    }
    new_id = create_incident(inc_payload)
    created = get_incident(new_id)
    return {
        "incident": created,
        "priority_breakdown": priority_res,
        "timeline": get_incident_updates(new_id),
    }


@app.get("/api/incidents/{incident_id}")
def api_get_incident(
    incident_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    inc = get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    _ensure_incident_access(inc, user)
    return {
        "incident": inc,
        "priority_breakdown": _priority_breakdown_for_incident(inc),
        "timeline": get_incident_updates(incident_id),
    }


@app.post("/api/incidents/{incident_id}/triage")
def api_retriage_incident(
    incident_id: str,
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> dict[str, Any]:
    inc = get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    zones = {z["zone_id"]: z["zone_name"] for z in get_zones()}
    triage_res = triage_incident(
        description=inc["description"],
        zone_name=zones.get(inc["zone_id"], inc["zone_id"]),
        location_text=inc.get("location_text", ""),
        people_affected=inc.get("people_affected", 0),
    )
    priority_res = calculate_priority(triage_res)
    return {
        "incident_id": incident_id,
        "triage": triage_res,
        "priority_breakdown": priority_res,
    }


@app.get("/api/teams")
def api_get_teams(
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> list[dict[str, Any]]:
    return get_response_teams()


@app.get("/api/incidents/{incident_id}/recommendations")
def api_get_recommendations(
    incident_id: str,
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> dict[str, Any]:
    inc = get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    zones = get_zones()
    zone_coords = {z["zone_id"]: (z["latitude"], z["longitude"]) for z in zones}
    teams = get_response_teams()
    return recommend_team(inc, teams, zone_coords=zone_coords)


@app.post("/api/incidents/{incident_id}/approve-dispatch")
def api_approve_dispatch(
    incident_id: str,
    payload: ApproveDispatchRequest,
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> dict[str, Any]:
    inc = get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    teams = {t["team_id"]: t for t in get_response_teams()}
    if payload.team_id not in teams:
        raise HTTPException(status_code=404, detail=f"Response team '{payload.team_id}' not found")

    team_name = teams[payload.team_id]["team_name"]
    try:
        if inc["status"] == "Triaged":
            update_incident_workflow(
                incident_id=incident_id,
                new_status="In Review",
                note="Operator reviewed incident for dispatch.",
            )
        updated = update_incident_workflow(
            incident_id=incident_id,
            new_status="Team Assigned",
            assigned_team_id=payload.team_id,
            note=payload.note or f"Operator approved dispatch of {team_name} ({payload.team_id}).",
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "incident": updated,
        "timeline": get_incident_updates(incident_id),
    }


@app.patch("/api/incidents/{incident_id}/status")
def api_update_status(
    incident_id: str,
    payload: UpdateStatusRequest,
    user: dict[str, Any] = Depends(require_roles("authority", "response_team")),
) -> dict[str, Any]:
    if payload.status == "Team Assigned":
        raise HTTPException(
            status_code=409,
            detail="Use POST /api/incidents/{id}/approve-dispatch for operator-approved team assignment.",
        )
    inc = get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    if user["role"] == "response_team":
        if not user.get("team_id") or inc.get("assigned_team_id") != user["team_id"]:
            raise HTTPException(status_code=403, detail="Response teams can only update incidents assigned to their team.")
        if payload.status not in {"Acknowledged", "In Progress", "Resolved"}:
            raise HTTPException(
                status_code=403,
                detail="Response teams can only transition assigned incidents to Acknowledged, In Progress, or Resolved.",
            )
    try:
        updated = update_incident_workflow(
            incident_id=incident_id,
            new_status=payload.status,
            note=payload.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "incident": updated,
        "timeline": get_incident_updates(incident_id),
    }


@app.get("/api/incidents/{incident_id}/timeline")
def api_get_timeline(
    incident_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    inc = get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    _ensure_incident_access(inc, user)
    return get_incident_updates(incident_id)


@app.post("/api/demo/reset")
def api_reset_demo(
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> dict[str, Any]:
    reset_demo_data()
    incidents = list_incidents()
    teams = get_response_teams()
    return {
        "status": "reset",
        "incident_count": len(incidents),
        "team_count": len(teams),
    }


@app.get("/api/system/status")
def api_system_status() -> dict[str, Any]:
    w_status = get_weather_status()
    ai_status = get_ai_status()
    incidents = list_incidents()
    teams = get_response_teams()

    return {
        "weather": w_status,
        "ai": ai_status,
        "radar": get_rainviewer_radar(),
        "database": {
            "engine": "SQLite (WAL Mode)",
            "incident_count": len(incidents),
            "team_count": len(teams),
            "zone_count": len(get_zones()),
        },
        "formulas": {
            "risk": {
                "expression": "R = 0.40 * P + 0.30 * D + 0.30 * L",
                "weights": {
                    "rainfall": RISK_WEIGHT_RAINFALL,
                    "drainage": RISK_WEIGHT_DRAINAGE,
                    "low_lying": RISK_WEIGHT_LOWLYING,
                },
                "rainfall_ceiling_mm": RAINFALL_NORM_CEILING,
            },
            "priority": {
                "expression": "I = 0.30 * S + 0.25 * T + 0.25 * V + 0.10 * N + 0.10 * H",
                "weights": {
                    "severity": PRIORITY_WEIGHT_SEVERITY,
                    "stranded": PRIORITY_WEIGHT_STRANDED,
                    "vulnerability": PRIORITY_WEIGHT_VULNERABILITY,
                    "people": PRIORITY_WEIGHT_PEOPLE,
                    "hazard": PRIORITY_WEIGHT_HAZARD,
                },
            },
        },
        "status_transitions": STATUS_TRANSITIONS,
        "limitations": [
            "Zone risk scores use an explainable heuristic, not a validated hydrological model.",
            "Simulated rainfall values are operator scenario inputs, not live rain-gauge observations.",
            "Response team locations, specialties, and availability are illustrative demonstration data.",
            "AI/fallback triage assists intake; human operators retain sole dispatch authority.",
        ],
    }


@app.get("/api/geo/radar")
def api_geo_radar() -> dict[str, Any]:
    return get_rainviewer_radar()


@app.get("/api/geo/osm/{zone_id}")
def api_geo_osm(zone_id: str) -> dict[str, Any]:
    zones = {z["zone_id"]: z for z in get_zones()}
    if zone_id not in zones:
        raise HTTPException(status_code=404, detail=f"Unknown zone_id '{zone_id}'")
    z = zones[zone_id]
    return {
        "zone_id": zone_id,
        "zone_name": z["zone_name"],
        **get_zone_osm_context(zone_id, z["latitude"], z["longitude"]),
    }


@app.get("/api/dataset/status")
def api_dataset_status() -> dict[str, Any]:
    return get_dataset_status()


@app.post("/api/dataset/refresh")
def api_dataset_refresh(
    _user: dict[str, Any] = Depends(require_roles("authority")),
) -> dict[str, Any]:
    try:
        meta = build_training_dataset(force_refresh=True)
        meta["available"] = True
        meta["cache_age_seconds"] = 0.0
        return meta
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Dataset refresh failed: {exc}")


@app.get("/api/dataset/download")
def api_dataset_download():
    if not TRAINING_CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="Training dataset CSV not generated yet.")
    return FileResponse(
        path=str(TRAINING_CSV_PATH),
        media_type="text/csv",
        filename="floodiq_training_dataset.csv",
    )


@app.get("/api/weather/historical/{zone_id}")
def api_historical_weather(
    zone_id: str,
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    zones = {z["zone_id"]: z for z in get_zones()}
    if zone_id not in zones:
        raise HTTPException(status_code=404, detail=f"Unknown zone_id '{zone_id}'")
    if not TRAINING_CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="Historical dataset CSV not available yet.")

    import pandas as pd

    df = pd.read_csv(TRAINING_CSV_PATH)
    z_df = df[df["location_id"] == zone_id].copy()
    if z_df.empty:
        return {"zone_id": zone_id, "zone_name": zones[zone_id]["zone_name"], "records": [], "summary": {}}

    z_df = z_df.sort_values("timestamp")
    recent = z_df.tail(days)
    r24 = pd.to_numeric(z_df["rainfall_24h"], errors="coerce").dropna()

    return {
        "zone_id": zone_id,
        "zone_name": zones[zone_id]["zone_name"],
        "elevation_m": float(recent["elevation_m"].dropna().iloc[-1]) if not recent["elevation_m"].dropna().empty else None,
        "summary": {
            "total_days": int(len(z_df)),
            "max_24h_mm": round(float(r24.max()), 1) if not r24.empty else None,
            "p95_24h_mm": round(float(r24.quantile(0.95)), 1) if not r24.empty else None,
            "mean_24h_mm": round(float(r24.mean()), 2) if not r24.empty else None,
        },
        "records": [
            {
                "date": str(r["timestamp"])[:10],
                "rainfall_24h": None if pd.isna(r["rainfall_24h"]) else round(float(r["rainfall_24h"]), 2),
                "relative_humidity": None if pd.isna(r["relative_humidity"]) else round(float(r["relative_humidity"]), 1),
                "temperature": None if pd.isna(r["temperature"]) else round(float(r["temperature"]), 1),
                "soil_moisture": None if pd.isna(r["soil_moisture"]) else round(float(r["soil_moisture"]), 3),
                "flood_event": str(r["flood_event"]),
            }
            for _, r in recent.iterrows()
        ],
    }
