"""
Tests for FloodIQ FastAPI backend endpoints.
"""

import pytest
from fastapi.testclient import TestClient

import api
import database


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_api.db")
    monkeypatch.setattr(database, "DATABASE_PATH", db_file)
    database.init_db(db_file)
    with TestClient(api.app) as c:
        yield c


def _login_headers(client, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_and_dashboard_and_zones(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    headers = _login_headers(client, "authority@floodiq.demo", "Authority@123")
    resp = client.get("/api/dashboard?rainfall_mm=100&use_simulation=true", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["weather"]["mode"] == "simulation"
    assert data["weather"]["rainfall_mm"] == 100.0
    assert len(data["zones"]) == 5
    assert len(data["incidents"]) == 2
    assert len(data["teams"]) == 5

    zones_resp = client.get("/api/zones")
    assert zones_resp.status_code == 200
    assert len(zones_resp.json()) == 5


def test_risk_simulation_endpoint(client):
    resp = client.post("/api/risk/simulate", json={"rainfall_mm": 100, "use_simulation": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["High"] + data["summary"]["Critical"] == 5


def test_incident_lifecycle_and_timeline(client):
    auth = _login_headers(client, "authority@floodiq.demo", "Authority@123")

    # 1. Create incident
    create_resp = client.post(
        "/api/incidents",
        json={
            "zone_id": "musi_riverfront",
            "description": "Three people including an elderly resident are stranded on the first floor as water rises.",
            "location_text": "Chaderghat Bridge",
            "reported_category": "Water Rescue",
            "people_affected": 3,
        },
        headers=auth,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    inc_id = created["incident"]["incident_id"]
    assert created["incident"]["status"] == "Triaged"
    assert created["incident"]["priority_score"] >= 75

    # 2. Recommendations
    rec_resp = client.get(f"/api/incidents/{inc_id}/recommendations", headers=auth)
    assert rec_resp.status_code == 200
    rec_team_id = rec_resp.json()["recommended_team"]["team_id"]

    # 3. Approve dispatch
    disp_resp = client.post(
        f"/api/incidents/{inc_id}/approve-dispatch",
        json={"team_id": rec_team_id, "note": "Approved by test operator"},
        headers=auth,
    )
    assert disp_resp.status_code == 200
    assert disp_resp.json()["incident"]["status"] == "Team Assigned"

    # 4. Status transitions -> In Progress -> Resolved
    prog_resp = client.patch(
        f"/api/incidents/{inc_id}/status",
        json={"status": "In Progress", "note": "Team on site"},
        headers=auth,
    )
    assert prog_resp.status_code == 200
    assert prog_resp.json()["incident"]["status"] == "In Progress"

    res_resp = client.patch(
        f"/api/incidents/{inc_id}/status",
        json={"status": "Resolved", "note": "All evacuated"},
        headers=auth,
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["incident"]["status"] == "Resolved"

    # 5. Timeline has all chronological events
    tl_resp = client.get(f"/api/incidents/{inc_id}/timeline", headers=auth)
    assert tl_resp.status_code == 200
    statuses = [e["new_status"] for e in tl_resp.json()]
    assert statuses == ["Triaged", "In Review", "Team Assigned", "In Progress", "Resolved"]


def test_system_status_hides_api_key(client):
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "GROQ_API_KEY" not in str(data)
    assert "GEMINI_API_KEY" not in str(data)
    assert data["ai"]["mode"] in ("groq", "rule_based")
    assert "groq_configured" in data["ai"]
    assert "latest_provider_status" in data["ai"]
    assert len(data["limitations"]) >= 3


def test_patch_status_cannot_bypass_dispatch_approval(client):
    auth = _login_headers(client, "authority@floodiq.demo", "Authority@123")
    incs = client.get("/api/incidents", headers=auth).json()
    inc_id = incs[0]["incident_id"]
    resp = client.patch(f"/api/incidents/{inc_id}/status", json={"status": "Team Assigned"}, headers=auth)
    assert resp.status_code == 409
    assert "approve-dispatch" in resp.json()["detail"]


def test_repeated_submissions_and_duplicate_assignment_blocked(client):
    auth = _login_headers(client, "authority@floodiq.demo", "Authority@123")
    r1 = client.post(
        "/api/incidents",
        json={"zone_id": "begumpet", "description": "Two people stranded on roof", "people_affected": 2},
    )
    r2 = client.post(
        "/api/incidents",
        json={"zone_id": "begumpet", "description": "Two people stranded on roof", "people_affected": 2},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    id1 = r1.json()["incident"]["incident_id"]
    id2 = r2.json()["incident"]["incident_id"]
    assert id1 != id2

    d1 = client.post(f"/api/incidents/{id1}/approve-dispatch", json={"team_id": "wrt_01"}, headers=auth)
    d2 = client.post(f"/api/incidents/{id2}/approve-dispatch", json={"team_id": "wrt_01"}, headers=auth)
    assert d1.status_code == 200
    assert d2.status_code == 409
