"""
Tests for multi-role authentication, RBAC isolation, guest tracking,
and cross-role end-to-end incident lifecycle in FloodIQ.
"""

import pytest
from fastapi.testclient import TestClient

import api
import database


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_rbac.db")
    monkeypatch.setattr(database, "DATABASE_PATH", db_file)
    database.init_db(db_file)
    with TestClient(api.app) as c:
        yield c


def _login(client, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_auth_login_me_logout(client):
    bad = client.post("/api/auth/login", json={"email": "citizen@floodiq.demo", "password": "wrong"})
    assert bad.status_code == 401

    headers = _login(client, "citizen@floodiq.demo", "Citizen@123")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "citizen"

    out = client.post("/api/auth/logout", headers=headers)
    assert out.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_unauthenticated_protected_routes_return_401(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/incidents").status_code == 401
    assert client.get("/api/citizen/incidents").status_code == 401
    assert client.get("/api/team/incidents").status_code == 401
    assert client.get("/api/teams").status_code == 401
    assert client.post("/api/demo/reset").status_code == 401


def test_citizen_isolation_and_guest_tracking(client):
    c1 = _login(client, "citizen@floodiq.demo", "Citizen@123")
    c2 = _login(client, "citizen2@floodiq.demo", "Citizen@123")

    # Citizen 1 submits an incident
    r1 = client.post(
        "/api/incidents",
        json={
            "zone_id": "begumpet",
            "description": "Water entering ground floor apartment near Prakash Nagar.",
            "location_text": "Prakash Nagar Lane 2",
            "reported_category": "Drainage Blockage",
            "people_affected": 2,
        },
        headers=c1,
    )
    assert r1.status_code == 201
    inc1 = r1.json()["incident"]
    assert inc1["reporter_type"] == "authenticated"
    assert inc1["tracking_code"].startswith("TRK-")

    # Citizen 1 sees it in /api/citizen/incidents, Citizen 2 does not
    c1_list = client.get("/api/citizen/incidents", headers=c1).json()
    c2_list = client.get("/api/citizen/incidents", headers=c2).json()
    assert any(i["incident_id"] == inc1["incident_id"] for i in c1_list)
    assert not any(i["incident_id"] == inc1["incident_id"] for i in c2_list)

    # Citizen 2 gets 403 on Citizen 1's incident & timeline
    assert client.get(f"/api/incidents/{inc1['incident_id']}", headers=c2).status_code == 403
    assert client.get(f"/api/incidents/{inc1['incident_id']}/timeline", headers=c2).status_code == 403

    # Citizen cannot access authority or team routes
    assert client.get("/api/dashboard", headers=c1).status_code == 403
    assert client.get("/api/team/incidents", headers=c1).status_code == 403

    # Guest submission returns tracking_code and works with /api/public/track
    guest = client.post(
        "/api/incidents",
        json={
            "zone_id": "kukatpally",
            "description": "Fallen electric pole in flooded street.",
            "location_text": "Road No 36",
            "reported_category": "Power Hazard",
            "people_affected": 1,
        },
    )
    assert guest.status_code == 201
    g_inc = guest.json()["incident"]
    assert g_inc["reporter_type"] == "guest"
    trk = client.get(f"/api/public/track/{g_inc['incident_id']}?tracking_code={g_inc['tracking_code']}")
    assert trk.status_code == 200
    assert trk.json()["incident"]["incident_id"] == g_inc["incident_id"]
    assert client.get(f"/api/public/track/{g_inc['incident_id']}?tracking_code=WRONG").status_code == 404


def test_cross_role_lifecycle_and_team_rbac(client):
    c1 = _login(client, "citizen@floodiq.demo", "Citizen@123")
    auth = _login(client, "authority@floodiq.demo", "Authority@123")
    alpha = _login(client, "alpha@floodiq.demo", "Team@123")
    bravo = _login(client, "bravo@floodiq.demo", "Team@123")

    # 1. Citizen submits with valid photo data URL
    sub = client.post(
        "/api/incidents",
        json={
            "zone_id": "musi_riverfront",
            "description": "Elderly resident stranded on first floor as floodwater rises.",
            "location_text": "Chaderghat Bridge",
            "reported_category": "Water Rescue",
            "people_affected": 2,
            "photo_data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        },
        headers=c1,
    )
    assert sub.status_code == 201
    inc_id = sub.json()["incident"]["incident_id"]

    # Response team cannot approve its own assignment or view unassigned incident
    assert client.post(f"/api/incidents/{inc_id}/approve-dispatch", json={"team_id": "wrt_01"}, headers=alpha).status_code == 403
    assert client.get(f"/api/incidents/{inc_id}", headers=alpha).status_code == 403

    # 2. Authority approves dispatch to wrt_01 (Alpha)
    disp = client.post(
        f"/api/incidents/{inc_id}/approve-dispatch",
        json={"team_id": "wrt_01", "note": "Dispatch Alpha Boat Unit"},
        headers=auth,
    )
    assert disp.status_code == 200
    assert disp.json()["incident"]["assigned_team_id"] == "wrt_01"

    # Alpha sees it, Bravo does not and gets 403
    alpha_list = client.get("/api/team/incidents", headers=alpha).json()["incidents"]
    bravo_list = client.get("/api/team/incidents", headers=bravo).json()["incidents"]
    assert any(i["incident_id"] == inc_id for i in alpha_list)
    assert not any(i["incident_id"] == inc_id for i in bravo_list)
    assert client.get(f"/api/incidents/{inc_id}", headers=bravo).status_code == 403
    assert client.patch(f"/api/incidents/{inc_id}/status", json={"status": "Acknowledged"}, headers=bravo).status_code == 403

    # 3. Alpha acknowledges -> In Progress -> Resolved
    ack = client.patch(
        f"/api/incidents/{inc_id}/status",
        json={"status": "Acknowledged", "note": "Alpha en route"},
        headers=alpha,
    )
    assert ack.status_code == 200
    assert ack.json()["incident"]["status"] == "Acknowledged"

    prog = client.patch(
        f"/api/incidents/{inc_id}/status",
        json={"status": "In Progress", "note": "Rescue boat deployed"},
        headers=alpha,
    )
    assert prog.status_code == 200

    res = client.patch(
        f"/api/incidents/{inc_id}/status",
        json={"status": "Resolved", "note": "Residents evacuated safely"},
        headers=alpha,
    )
    assert res.status_code == 200
    assert res.json()["incident"]["status"] == "Resolved"

    # 4. Citizen sees full updated status & timeline
    c_tl = client.get(f"/api/incidents/{inc_id}/timeline", headers=c1)
    assert c_tl.status_code == 200
    statuses = [u["new_status"] for u in c_tl.json()]
    assert statuses == ["Triaged", "In Review", "Team Assigned", "Acknowledged", "In Progress", "Resolved"]


def test_unsafe_svg_photo_upload_rejected(client):
    c1 = _login(client, "citizen@floodiq.demo", "Citizen@123")
    resp = client.post(
        "/api/incidents",
        json={
            "zone_id": "begumpet",
            "description": "Flooding near main junction",
            "location_text": "Begumpet Flyover",
            "reported_category": "Road Blockage",
            "people_affected": 1,
            "photo_data_url": "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
        },
        headers=c1,
    )
    assert resp.status_code == 400
    assert "PNG, JPEG, WEBP, or GIF" in resp.json()["detail"]
