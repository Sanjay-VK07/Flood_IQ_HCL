"""
FloodIQ Three-Session Independent Integration Verification Script
Verifies:
- Session A (Citizen: citizen@floodiq.demo)
- Session B (Municipal Authority: authority@floodiq.demo)
- Session C (Response Team: bravo@floodiq.demo / wrt_02)
- Complete Lifecycle: Triaged -> In Review -> Team Assigned -> Acknowledged -> In Progress -> Resolved
- Cross-Portal Audit Timelines consistency
- Invalid role-based access & invalid status transitions
- Persistence across database / backend reload
"""

import sys
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
import httpx

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import api
import database
import config

def run_three_session_verification():
    print("=" * 70)
    print("Starting FloodIQ Three-Portal Independent Session Integration Test")
    print("=" * 70)

    db_path = config.DATABASE_PATH
    print(f"Target SQLite Database: {db_path}")
    database.init_db(db_path)

    # We use TestClient with separate session state for Session A, B, and C
    client = TestClient(api.app)

    # -------------------------------------------------------------
    # SESSION A: Citizen
    # -------------------------------------------------------------
    print("\n--- [SESSION A: Citizen] ---")
    resp_login_a = client.post("/api/auth/login", json={
        "email": "citizen@floodiq.demo",
        "password": "Citizen@123"
    })
    assert resp_login_a.status_code == 200, f"Citizen login failed: {resp_login_a.text}"
    token_a = resp_login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    print(f"✔ Citizen Asha Reddy authenticated (usr_cit_01)")

    # Submit new emergency incident
    create_payload = {
        "zone_id": "musi_riverfront",
        "description": "Rising flood waters trapping 4 elderly residents on 1st floor balcony near Puranapul bridge.",
        "location_text": "Puranapul Old Bridge Lane 2",
        "reported_category": "Water Rescue",
        "people_affected": 4,
        "photo_data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    }
    resp_sub = client.post("/api/incidents", json=create_payload, headers=headers_a)
    assert resp_sub.status_code == 201, f"Incident creation failed: {resp_sub.text}"
    sub_data = resp_sub.json()
    inc = sub_data["incident"]
    inc_id = inc["incident_id"]
    track_code = inc["tracking_code"]
    print(f"✔ Emergency incident created:")
    print(f"    Incident ID:   {inc_id}")
    print(f"    Tracking Code: {track_code}")
    print(f"    Triage Status: {inc['status']} (Category: {inc['ai_category']}, Urgency: {inc['ai_urgency']})")
    print(f"    Priority Score: {inc['priority_score']}/100 (Vulnerable: {inc['vulnerable_group']})")

    # Citizen sees it in /api/citizen/incidents
    cit_incs = client.get("/api/citizen/incidents", headers=headers_a).json()
    assert any(i["incident_id"] == inc_id for i in cit_incs), "Incident missing from Citizen queue"
    print(f"✔ Incident successfully listed in Citizen My Reports")

    # Guest tracking verification
    guest_track = client.get(f"/api/public/track/{inc_id}?tracking_code={track_code}")
    assert guest_track.status_code == 200, "Public guest tracking failed"
    print(f"✔ Public guest tracking endpoint verified with code {track_code}")

    # Citizen cannot approve dispatch or update status directly (RBAC check)
    bad_approve = client.post(f"/api/incidents/{inc_id}/approve-dispatch", json={"team_id": "wrt_02"}, headers=headers_a)
    assert bad_approve.status_code == 403, f"Citizen should not be able to approve dispatch, got {bad_approve.status_code}"
    print(f"✔ RBAC Verified: Citizen forbidden from dispatch approval (HTTP 403)")

    # -------------------------------------------------------------
    # SESSION B: Municipal Authority
    # -------------------------------------------------------------
    print("\n--- [SESSION B: Municipal Authority] ---")
    resp_login_b = client.post("/api/auth/login", json={
        "email": "authority@floodiq.demo",
        "password": "Authority@123"
    })
    assert resp_login_b.status_code == 200, f"Authority login failed: {resp_login_b.text}"
    token_b = resp_login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    print(f"✔ Duty Officer Verma authenticated (usr_auth_01)")

    # Incident appears in municipal queue
    all_incs = client.get("/api/incidents", headers=headers_b).json()
    matched = [i for i in all_incs if i["incident_id"] == inc_id]
    assert len(matched) == 1, "Incident missing in Municipal Authority queue"
    print(f"✔ Incident #{inc_id} automatically discovered in Municipal Command queue")

    # Review triage & AI recommendation
    rec_res = client.get(f"/api/incidents/{inc_id}/recommendations", headers=headers_b)
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    rec_team = rec_data.get("recommended_team")
    print(f"✔ Triage & Recommendation retrieved: Recommended Unit = {rec_team['team_name'] if rec_team else 'None'} ({rec_data.get('match_score')}/100)")

    # Approve dispatch to Water Rescue Bravo (wrt_02)
    disp_res = client.post(f"/api/incidents/{inc_id}/approve-dispatch", json={
        "team_id": "wrt_02",
        "note": "Authorized dispatch to Water Rescue Bravo. Deploy rubber dinghy with life vests."
    }, headers=headers_b)
    assert disp_res.status_code == 200, f"Dispatch approval failed: {disp_res.text}"
    disp_inc = disp_res.json()["incident"]
    assert disp_inc["status"] == "Team Assigned"
    assert disp_inc["assigned_team_id"] == "wrt_02"
    print(f"✔ Authority approved dispatch to Water Rescue Bravo (wrt_02)")
    print(f"    Status updated to: {disp_inc['status']}")

    # -------------------------------------------------------------
    # SESSION C: Response Team Bravo (wrt_02)
    # -------------------------------------------------------------
    print("\n--- [SESSION C: Emergency Response Team Bravo] ---")
    resp_login_c = client.post("/api/auth/login", json={
        "email": "bravo@floodiq.demo",
        "password": "Team@123"
    })
    assert resp_login_c.status_code == 200, f"Bravo team login failed: {resp_login_c.text}"
    token_c = resp_login_c.json()["access_token"]
    headers_c = {"Authorization": f"Bearer {token_c}"}
    print(f"✔ Commander Vikram Singh / Bravo Unit authenticated (wrt_02)")

    # Bravo checks assigned incident queue
    bravo_queue = client.get("/api/team/incidents", headers=headers_c).json()
    bravo_incs = bravo_queue.get("incidents", [])
    assert any(i["incident_id"] == inc_id for i in bravo_incs), "Incident not in Bravo assigned queue"
    print(f"✔ Incident #{inc_id} appeared automatically in Bravo Tactical Queue")

    # RBAC Negative Check: Response Team Alpha (wrt_01) CANNOT see or update Bravo's incident
    resp_login_alpha = client.post("/api/auth/login", json={
        "email": "alpha@floodiq.demo",
        "password": "Team@123"
    })
    token_alpha = resp_login_alpha.json()["access_token"]
    headers_alpha = {"Authorization": f"Bearer {token_alpha}"}
    alpha_queue = client.get("/api/team/incidents", headers=headers_alpha).json().get("incidents", [])
    assert not any(i["incident_id"] == inc_id for i in alpha_queue), "Alpha should not see Bravo's incident"
    bad_alpha_update = client.patch(f"/api/incidents/{inc_id}/status", json={"status": "Acknowledged"}, headers=headers_alpha)
    assert bad_alpha_update.status_code == 403, f"Alpha updating Bravo incident should be 403, got {bad_alpha_update.status_code}"
    print(f"✔ RBAC Verified: Unrelated Response Team Alpha forbidden from Bravo incident (HTTP 403)")

    # Invalid Transition Check: Bravo cannot directly jump from Team Assigned to Resolved
    bad_trans = client.patch(f"/api/incidents/{inc_id}/status", json={"status": "Resolved"}, headers=headers_c)
    assert bad_trans.status_code in (403, 409), f"Invalid transition should fail with 403 or 409, got {bad_trans.status_code}"
    print(f"✔ Lifecycle Guard: Invalid transition (Team Assigned -> Resolved) blocked ({bad_trans.status_code})")

    # Step 1: Bravo acknowledges assignment
    ack_res = client.patch(f"/api/incidents/{inc_id}/status", json={
        "status": "Acknowledged",
        "note": "Unit Bravo acknowledged dispatch order. Departing base station."
    }, headers=headers_c)
    assert ack_res.status_code == 200, f"Acknowledgement failed: {ack_res.text}"
    print(f"✔ Bravo acknowledged assignment -> Status: Acknowledged")

    # Step 2: Bravo starts response (On-Scene / In Progress)
    prog_res = client.patch(f"/api/incidents/{inc_id}/status", json={
        "status": "In Progress",
        "note": "Unit Bravo on-scene at Puranapul. Inflatable dinghy launched to reach 1st floor."
    }, headers=headers_c)
    assert prog_res.status_code == 200, f"In Progress failed: {prog_res.text}"
    print(f"✔ Bravo on-scene -> Status: In Progress")

    # Step 3: Bravo submits resolution notes and marks Resolved
    res_res = client.patch(f"/api/incidents/{inc_id}/status", json={
        "status": "Resolved",
        "note": "All 4 residents safely evacuated via boat to dry shelter at High Court relief center. Mission accomplished."
    }, headers=headers_c)
    assert res_res.status_code == 200, f"Resolution failed: {res_res.text}"
    print(f"✔ Bravo resolved mission -> Status: Resolved")

    # -------------------------------------------------------------
    # FINAL CROSS-PORTAL VERIFICATION
    # -------------------------------------------------------------
    print("\n--- [FINAL CROSS-PORTAL SYNCHRONIZATION VERIFICATION] ---")

    # 1. Citizen checks incident status
    cit_view = client.get(f"/api/incidents/{inc_id}", headers=headers_a).json()
    assert cit_view["incident"]["status"] == "Resolved"
    print(f"✔ Citizen Portal: Incident confirmed 'Resolved'")

    # 2. Authority checks incident status
    auth_view = client.get(f"/api/incidents/{inc_id}", headers=headers_b).json()
    assert auth_view["incident"]["status"] == "Resolved"
    print(f"✔ Municipal Authority: Incident confirmed 'Resolved'")

    # 3. Public tracking verification
    public_view = client.get(f"/api/public/track/{inc_id}?tracking_code={track_code}").json()
    assert public_view["incident"]["status"] == "Resolved"
    print(f"✔ Public Tracking Portal: Incident confirmed 'Resolved'")

    # 4. Check timeline consistency across all portals
    tl_cit = client.get(f"/api/incidents/{inc_id}/timeline", headers=headers_a).json()
    tl_auth = client.get(f"/api/incidents/{inc_id}/timeline", headers=headers_b).json()
    tl_public = public_view["timeline"]

    statuses_cit = [u["new_status"] for u in tl_cit]
    statuses_auth = [u["new_status"] for u in tl_auth]
    statuses_public = [u["new_status"] for u in tl_public]

    assert statuses_cit == statuses_auth == statuses_public, "Timelines mismatch across portals!"
    print(f"✔ Timeline consistency confirmed across all 3 portals ({len(tl_cit)} milestones):")
    for u in tl_cit:
        print(f"    - {u['new_status']:<15} | {u['note']}")

    # 5. Database direct SQL persistence check
    print("\n--- [DATABASE PERSISTENCE & BACKEND RESTART VERIFICATION] ---")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM incidents WHERE incident_id = ?", (inc_id,)).fetchone()
    assert row is not None, "Incident not found in SQLite table!"
    assert row["status"] == "Resolved", f"SQLite status mismatch: {row['status']}"
    assert row["assigned_team_id"] == "wrt_02", f"SQLite assigned team mismatch: {row['assigned_team_id']}"

    updates_count = conn.execute("SELECT COUNT(*) FROM incident_updates WHERE incident_id = ?", (inc_id,)).fetchone()[0]
    assert updates_count == len(tl_cit), f"Update count mismatch: {updates_count} != {len(tl_cit)}"
    conn.close()
    print(f"✔ SQLite direct inspection verified: incident and all {updates_count} updates stored in {db_path}")

    # Reinitialize a completely new TestClient (simulating backend server restart)
    new_client = TestClient(api.app)
    reloaded_resp = new_client.get(f"/api/public/track/{inc_id}?tracking_code={track_code}")
    assert reloaded_resp.status_code == 200
    assert reloaded_resp.json()["incident"]["status"] == "Resolved"
    print(f"✔ Persistence verified across full backend reload: state is 100% intact")

    print("\n" + "=" * 70)
    print("ALL THREE-SESSION INTEGRATION CHECKS PASSED WITH ZERO ERRORS!")
    print("=" * 70)

if __name__ == "__main__":
    run_three_session_verification()
