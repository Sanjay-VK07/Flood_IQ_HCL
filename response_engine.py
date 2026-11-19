"""
FloodIQ — Response & Decision Engine

Provides:
1. Vulnerability-First Priority Calculation
   Formula:
       I = 0.30 × S + 0.25 × T + 0.25 × V + 0.10 × N + 0.10 × H
   Where:
       S = Severity score (0–100) based on Urgency & Category impact
       T = Stranded / Trapped score (0–100)
       V = Vulnerability score (0–100)
       N = Normalized people affected score (0–100)
       H = Immediate hazard score (0–100)

   Calibrated Targets:
       - Incident A (Musi Riverfront, 3 trapped, elderly, rising water): ~92 / 100 (Critical)
       - Incident B (Ameerpet road blockage, traffic affected, no trapped): ~48 / 100 (Moderate)

2. Response Team Recommendation
   - Calculates geographic distance (Haversine formula)
   - Evaluates specialty match vs incident category
   - Enforces team availability (Available only)
   - Generates transparent match explanations and ranked alternatives
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from config import (
    PRIORITY_WEIGHT_SEVERITY,
    PRIORITY_WEIGHT_STRANDED,
    PRIORITY_WEIGHT_VULNERABILITY,
    PRIORITY_WEIGHT_PEOPLE,
    PRIORITY_WEIGHT_HAZARD,
    PRIORITY_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Priority Calculation (Vulnerability-First Engine)
# ---------------------------------------------------------------------------

def classify_priority(score: float) -> str:
    """Classify numerical priority into Low, Moderate, High, or Critical."""
    score = max(0.0, min(100.0, score))
    if score < 30:
        return "Low"
    elif score < 50:
        return "Moderate"
    elif score < 75:
        return "High"
    else:
        return "Critical"


def calculate_priority(triage_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate an explainable vulnerability-first priority score.

    Args:
        triage_result: dict containing triage fields (ai_urgency, ai_category,
                       people_affected, vulnerable_flag, stranded,
                       unable_to_evacuate, immediate_hazard).

    Returns:
        {
            "priority_score": float (0–100),
            "priority_band": str ("Low"|"Moderate"|"High"|"Critical"),
            "factors": {
                "severity": {"score": float, "weight": float, "contribution": float},
                "stranded": {"score": float, "weight": float, "contribution": float},
                "vulnerability": {"score": float, "weight": float, "contribution": float},
                "people_affected": {"score": float, "weight": float, "contribution": float},
                "hazard": {"score": float, "weight": float, "contribution": float},
            },
            "priority_rationale": str,
        }
    """
    category = triage_result.get("ai_category", "Other")
    urgency = triage_result.get("ai_urgency", "Medium")
    people = int(triage_result.get("people_affected", 0) or 0)
    vulnerable_flag = bool(triage_result.get("vulnerable_flag", False))
    stranded = bool(triage_result.get("stranded", False))
    unable_to_evacuate = bool(triage_result.get("unable_to_evacuate", False))
    immediate_hazard = bool(triage_result.get("immediate_hazard", False))

    # --- 1. Severity Score S (0–100) ---
    # Baseline from urgency
    urgency_scores = {
        "Critical": 100.0,
        "High": 80.0,
        "Medium": 50.0,
        "Low": 25.0,
    }
    base_s = urgency_scores.get(urgency, 50.0)

    # Category impact modifier
    # Road Blockage on arterial transit corridors or Medical emergencies receive operational gravity
    category_boost = 0.0
    if category == "Road Blockage":
        category_boost = 20.0
    elif category == "Water Rescue":
        category_boost = 15.0
    elif category == "Medical Emergency":
        category_boost = 20.0

    S = max(0.0, min(100.0, base_s + category_boost))

    # --- 2. Stranded / Trapped Score T (0–100) ---
    if stranded:
        T = 100.0
    elif unable_to_evacuate:
        T = 85.0
    elif category == "Road Blockage":
        # Commuters and vehicles partially stranded in traffic corridors
        T = 40.0
    else:
        T = 0.0

    # --- 3. Vulnerability Score V (0–100) ---
    if vulnerable_flag:
        V = 100.0
    elif category == "Road Blockage":
        # Public pedestrians and commuters exposed on open flooded roadways
        V = 28.0
    else:
        V = 0.0

    # --- 4. People Affected Score N (0–100) ---
    # Normalizing 20 people = 100 points (5 points per person)
    # If 0 people specified but it's a road blockage, baseline commuter impact = 20 pts
    if people > 0:
        N = min(100.0, people * 5.0)
    elif category == "Road Blockage":
        N = 20.0
    else:
        N = 0.0

    # --- 5. Immediate Hazard Score H (0–100) ---
    if immediate_hazard:
        H = 100.0
    elif category == "Road Blockage":
        # Hidden hazards: open manholes, submerged potholes, electrocution risk
        H = 80.0
    elif category in ["Infrastructure Damage", "Flooded Building"]:
        H = 40.0
    else:
        H = 10.0

    # --- Weighted Calculation ---
    c_s = round(PRIORITY_WEIGHT_SEVERITY * S, 2)
    c_t = round(PRIORITY_WEIGHT_STRANDED * T, 2)
    c_v = round(PRIORITY_WEIGHT_VULNERABILITY * V, 2)
    c_n = round(PRIORITY_WEIGHT_PEOPLE * N, 2)
    c_h = round(PRIORITY_WEIGHT_HAZARD * H, 2)

    raw_priority = c_s + c_t + c_v + c_n + c_h
    priority_score = round(max(0.0, min(100.0, raw_priority)), 1)
    priority_band = classify_priority(priority_score)

    # Human-readable rationale
    reasons = []
    if S >= 80:
        reasons.append(f"High emergency severity ({urgency})")
    if T >= 80:
        reasons.append("Reported individuals are actively stranded or unable to self-evacuate")
    if V >= 80:
        reasons.append("Critical vulnerability factor detected (e.g. elderly/children/disabled)")
    if H >= 80:
        reasons.append("Immediate physical hazard present (rising water/road danger)")
    if not reasons:
        reasons.append(f"{category} with {urgency} urgency")

    rationale = f"Priority {priority_score:.0f}/100 ({priority_band}) due to: " + "; ".join(reasons) + "."

    return {
        "priority_score": priority_score,
        "priority_band": priority_band,
        "factors": {
            "severity": {"score": round(S, 1), "weight": PRIORITY_WEIGHT_SEVERITY, "contribution": c_s},
            "stranded": {"score": round(T, 1), "weight": PRIORITY_WEIGHT_STRANDED, "contribution": c_t},
            "vulnerability": {"score": round(V, 1), "weight": PRIORITY_WEIGHT_VULNERABILITY, "contribution": c_v},
            "people_affected": {"score": round(N, 1), "weight": PRIORITY_WEIGHT_PEOPLE, "contribution": c_n},
            "hazard": {"score": round(H, 1), "weight": PRIORITY_WEIGHT_HAZARD, "contribution": c_h},
        },
        "priority_rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Response Team Recommendation Engine
# ---------------------------------------------------------------------------

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two coordinates in kilometers.
    """
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


def _specialty_match_score(incident_category: str, team_specialty: str) -> Tuple[float, str]:
    """
    Calculate specialty compatibility score (0–50).
    Returns (score, reason).
    """
    if incident_category == "Water Rescue":
        if team_specialty == "Water Rescue":
            return 50.0, "Direct specialty match for water rescue operations"
        elif team_specialty == "General Emergency":
            return 30.0, "General Emergency team can support secondary water operations"
        else:
            return 10.0, "Medical team secondary to immediate water extraction"

    elif incident_category == "Medical Emergency":
        if team_specialty == "Medical Emergency":
            return 50.0, "Direct medical specialty match"
        elif team_specialty == "General Emergency":
            return 30.0, "General Emergency team trained in first aid and transport"
        else:
            return 15.0, "Water rescue team has basic first responder equipment"

    elif incident_category in ["Road Blockage", "Infrastructure Damage", "Flooded Building"]:
        if team_specialty == "General Emergency":
            return 50.0, "Direct specialty match for clearing and infrastructure response"
        elif team_specialty == "Water Rescue":
            return 35.0, "Water rescue team equipped with high-water wading capability"
        else:
            return 20.0, "Medical team on standby for potential civilian injuries"

    else:
        if team_specialty == "General Emergency":
            return 45.0, "General Emergency versatile multi-hazard capability"
        else:
            return 25.0, "Secondary response capability"


def recommend_team(
    incident: Dict[str, Any],
    teams: List[Dict[str, Any]],
    zone_coords: Optional[Dict[str, Tuple[float, float]]] = None,
) -> Dict[str, Any]:
    """
    Recommend the best response team for an incident.

    Args:
        incident: dict with keys 'ai_category', 'zone_id', and optional 'latitude', 'longitude'.
        teams: list of team dicts (team_id, team_name, specialty, status, latitude, longitude, base_zone).
        zone_coords: optional dict mapping zone_id -> (lat, lon) as coordinate fallback.

    Returns:
        {
            "recommended_team": dict | None,
            "match_reason": str,
            "alternatives": list of candidate dicts with match details,
            "available_team_count": int,
        }
    """
    category = incident.get("ai_category") or incident.get("reported_category") or "Other"
    inc_zone = incident.get("zone_id", "")

    # Resolve incident coordinates
    inc_lat = incident.get("latitude")
    inc_lon = incident.get("longitude")

    if (inc_lat is None or inc_lon is None) and zone_coords and inc_zone in zone_coords:
        inc_lat, inc_lon = zone_coords[inc_zone]

    # Filter to available teams
    available_teams = [t for t in teams if t.get("status") == "Available"]

    if not available_teams:
        return {
            "recommended_team": None,
            "match_reason": "No response teams are currently Available. All units assigned or offline.",
            "alternatives": [],
            "available_team_count": 0,
        }

    scored_candidates = []

    for team in available_teams:
        spec_score, spec_reason = _specialty_match_score(category, team.get("specialty", ""))

        # Calculate distance
        team_lat = team.get("latitude", 17.385)
        team_lon = team.get("longitude", 78.4867)

        if inc_lat is not None and inc_lon is not None:
            dist_km = haversine_distance(inc_lat, inc_lon, team_lat, team_lon)
            # Distance score: closer is better (up to 50 pts, decays by 5 pts/km)
            dist_score = max(0.0, 50.0 - (dist_km * 4.0))
            dist_desc = f"{dist_km:.1f} km away"
        else:
            # If coordinates not provided, check base_zone match
            if team.get("base_zone") == inc_zone:
                dist_km = 0.0
                dist_score = 50.0
                dist_desc = f"Co-located in {inc_zone}"
            else:
                dist_km = 5.0
                dist_score = 25.0
                dist_desc = f"Based in {team.get('base_zone', 'other zone')}"

        total_score = spec_score + dist_score

        scored_candidates.append({
            "team": team,
            "match_score": round(total_score, 1),
            "specialty_score": spec_score,
            "distance_score": round(dist_score, 1),
            "distance_km": dist_km,
            "distance_desc": dist_desc,
            "reason": f"{spec_reason} ({dist_desc})",
        })

    # Sort descending by match score
    scored_candidates.sort(key=lambda x: x["match_score"], reverse=True)

    best = scored_candidates[0]
    alternatives = scored_candidates[1:]

    return {
        "recommended_team": best["team"],
        "match_score": best["match_score"],
        "match_reason": (
            f"Recommended '{best['team']['team_name']}' ({best['team']['specialty']}) — "
            f"{best['reason']} with overall suitability score of {best['match_score']}/100."
        ),
        "distance_km": best["distance_km"],
        "distance_desc": best["distance_desc"],
        "alternatives": alternatives,
        "available_team_count": len(available_teams),
    }
