"""
FloodIQ — Database Module

Handles all SQLite database operations: initialization, seeding, CRUD for zones,
incidents, response teams, and incident updates. Uses parameterized queries and
foreign-key constraints throughout. Thread-safe via check_same_thread=False.

All business logic consumers should use the functions exported here rather than
writing raw SQL.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import (
    DATABASE_PATH,
    INCIDENT_STATUSES,
    STATUS_TRANSITIONS,
    ZONES_DATA_PATH,
    SEED_DATA_PATH,
)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return a connection with foreign keys enabled and Row factory."""
    path = db_path or DATABASE_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS zones (
    zone_id      TEXT PRIMARY KEY,
    zone_name    TEXT NOT NULL,
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL,
    drainage_score  INTEGER NOT NULL CHECK(drainage_score BETWEEN 0 AND 100),
    low_lying_score INTEGER NOT NULL CHECK(low_lying_score BETWEEN 0 AND 100),
    description  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS response_teams (
    team_id     TEXT PRIMARY KEY,
    team_name   TEXT NOT NULL,
    specialty   TEXT NOT NULL,
    base_zone   TEXT NOT NULL,
    latitude    REAL NOT NULL,
    longitude   REAL NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Available'
        CHECK(status IN ('Available', 'Assigned', 'Unavailable')),
    current_incident_id TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id         TEXT PRIMARY KEY,
    zone_id             TEXT NOT NULL REFERENCES zones(zone_id),
    description         TEXT NOT NULL,
    location_text       TEXT NOT NULL DEFAULT '',
    reported_category   TEXT NOT NULL DEFAULT 'Other',
    people_affected     INTEGER NOT NULL DEFAULT 0,

    -- AI triage fields
    ai_category         TEXT DEFAULT NULL,
    ai_urgency          TEXT DEFAULT NULL,
    vulnerable_flag     INTEGER DEFAULT 0,
    vulnerable_group    TEXT DEFAULT 'None reported',
    stranded            INTEGER DEFAULT 0,
    unable_to_evacuate  INTEGER DEFAULT 0,
    immediate_hazard    INTEGER DEFAULT 0,
    ai_rationale        TEXT DEFAULT '',
    triage_mode         TEXT DEFAULT NULL CHECK(triage_mode IN ('ai', 'fallback', 'seeded', NULL)),

    -- Priority
    priority_score      REAL DEFAULT 0,
    operator_priority   REAL DEFAULT NULL,

    -- Workflow
    status              TEXT NOT NULL DEFAULT 'New'
        CHECK(status IN ('New', 'Triaged', 'In Review', 'Team Assigned', 'Acknowledged', 'In Progress', 'Resolved')),
    assigned_team_id    TEXT DEFAULT NULL REFERENCES response_teams(team_id),

    -- Multi-role ownership & guest tracking
    created_by_user_id  TEXT DEFAULT NULL,
    reporter_type       TEXT NOT NULL DEFAULT 'guest' CHECK(reporter_type IN ('authenticated', 'guest', 'seeded')),
    tracking_code       TEXT DEFAULT NULL,
    photo_data_url      TEXT DEFAULT NULL,

    -- Timestamps
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    full_name       TEXT NOT NULL,
    role            TEXT NOT NULL CHECK(role IN ('citizen', 'authority', 'response_team')),
    team_id         TEXT DEFAULT NULL REFERENCES response_teams(team_id),
    password_hash   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incident_updates (
    update_id       TEXT PRIMARY KEY,
    incident_id     TEXT NOT NULL REFERENCES incidents(incident_id),
    old_status      TEXT,
    new_status      TEXT,
    assigned_team_id TEXT DEFAULT NULL,
    note            TEXT DEFAULT '',
    updated_at      TEXT NOT NULL
);
"""


def _hash_password_pbkdf2(password: str) -> str:
    salt_hex = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Safely upgrade existing incidents table if missing multi-role columns or Acknowledged status."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='incidents'"
    ).fetchone()
    if not row:
        return
    table_sql = row[0] or ""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(incidents)").fetchall()}
    needs_rebuild = ("created_by_user_id" not in cols) or ("'Acknowledged'" not in table_sql)
    if not needs_rebuild:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        """CREATE TABLE incidents_new (
            incident_id         TEXT PRIMARY KEY,
            zone_id             TEXT NOT NULL REFERENCES zones(zone_id),
            description         TEXT NOT NULL,
            location_text       TEXT NOT NULL DEFAULT '',
            reported_category   TEXT NOT NULL DEFAULT 'Other',
            people_affected     INTEGER NOT NULL DEFAULT 0,
            ai_category         TEXT DEFAULT NULL,
            ai_urgency          TEXT DEFAULT NULL,
            vulnerable_flag     INTEGER DEFAULT 0,
            vulnerable_group    TEXT DEFAULT 'None reported',
            stranded            INTEGER DEFAULT 0,
            unable_to_evacuate  INTEGER DEFAULT 0,
            immediate_hazard    INTEGER DEFAULT 0,
            ai_rationale        TEXT DEFAULT '',
            triage_mode         TEXT DEFAULT NULL CHECK(triage_mode IN ('ai', 'fallback', 'seeded', NULL)),
            priority_score      REAL DEFAULT 0,
            operator_priority   REAL DEFAULT NULL,
            status              TEXT NOT NULL DEFAULT 'New'
                CHECK(status IN ('New', 'Triaged', 'In Review', 'Team Assigned', 'Acknowledged', 'In Progress', 'Resolved')),
            assigned_team_id    TEXT DEFAULT NULL REFERENCES response_teams(team_id),
            created_by_user_id  TEXT DEFAULT NULL,
            reporter_type       TEXT NOT NULL DEFAULT 'guest' CHECK(reporter_type IN ('authenticated', 'guest', 'seeded')),
            tracking_code       TEXT DEFAULT NULL,
            photo_data_url      TEXT DEFAULT NULL,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        )"""
    )
    conn.execute(
        """INSERT INTO incidents_new (
               incident_id, zone_id, description, location_text, reported_category,
               people_affected, ai_category, ai_urgency, vulnerable_flag,
               vulnerable_group, stranded, unable_to_evacuate, immediate_hazard,
               ai_rationale, triage_mode, priority_score, operator_priority,
               status, assigned_team_id, reporter_type, created_at, updated_at
           )
           SELECT
               incident_id, zone_id, description, location_text, reported_category,
               people_affected, ai_category, ai_urgency, vulnerable_flag,
               vulnerable_group, stranded, unable_to_evacuate, immediate_hazard,
               ai_rationale, triage_mode, priority_score, operator_priority,
               status, assigned_team_id, 'seeded', created_at, updated_at
           FROM incidents"""
    )
    conn.execute("DROP TABLE incidents")
    conn.execute("ALTER TABLE incidents_new RENAME TO incidents")
    conn.execute("PRAGMA foreign_keys = ON")


# ---------------------------------------------------------------------------
# Initialization & seeding
# ---------------------------------------------------------------------------

def init_db(db_path: str | None = None) -> None:
    """Create tables (idempotent), migrate existing schema safely, and seed data if empty."""
    conn = _get_connection(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        _migrate_schema(conn)
        _seed_if_empty(conn)
        conn.commit()
    finally:
        conn.close()


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    """Seed zones, teams, and demo incidents only if the tables are empty."""
    # Seed zones
    zone_count = conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0]
    if zone_count == 0:
        zones = _load_json(ZONES_DATA_PATH)
        for z in zones:
            conn.execute(
                """INSERT INTO zones
                   (zone_id, zone_name, latitude, longitude, drainage_score, low_lying_score, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (z["zone_id"], z["zone_name"], z["latitude"], z["longitude"],
                 z["drainage_score"], z["low_lying_score"], z["description"]),
            )

    # Seed response teams
    team_count = conn.execute("SELECT COUNT(*) FROM response_teams").fetchone()[0]
    if team_count == 0:
        seed = _load_json(SEED_DATA_PATH)
        for t in seed["response_teams"]:
            conn.execute(
                """INSERT INTO response_teams
                   (team_id, team_name, specialty, base_zone, latitude, longitude, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (t["team_id"], t["team_name"], t["specialty"], t["base_zone"],
                 t["latitude"], t["longitude"], t["status"]),
            )

    # Seed demo users (idempotent)
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        now_u = _now_iso()
        demo_users = [
            ("usr_cit_01", "citizen@floodiq.demo", "Asha Reddy", "citizen", None, "Citizen@123"),
            ("usr_cit_02", "citizen2@floodiq.demo", "Vikram Rao", "citizen", None, "Citizen@123"),
            ("usr_auth_01", "authority@floodiq.demo", "Duty Officer Verma", "authority", None, "Authority@123"),
            ("usr_team_wrt02", "bravo@floodiq.demo", "Water Rescue Bravo Lead", "response_team", "wrt_02", "Team@123"),
            ("usr_team_wrt01", "alpha@floodiq.demo", "Water Rescue Alpha Lead", "response_team", "wrt_01", "Team@123"),
        ]
        for uid, email, name, role, team_id, pwd in demo_users:
            conn.execute(
                """INSERT INTO users (user_id, email, full_name, role, team_id, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (uid, email, name, role, team_id, _hash_password_pbkdf2(pwd), now_u),
            )

    # Seed demo incidents
    incident_count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    if incident_count == 0:
        seed = _load_json(SEED_DATA_PATH)
        now = _now_iso()
        for idx, inc in enumerate(seed.get("demo_incidents", [])):
            inc_id = _generate_incident_id()
            owner_id = "usr_cit_01" if idx == 0 else "usr_cit_02"
            trk_code = _generate_tracking_code()
            conn.execute(
                """INSERT INTO incidents
                   (incident_id, zone_id, description, location_text, reported_category,
                    people_affected, ai_category, ai_urgency, vulnerable_flag,
                    vulnerable_group, stranded, unable_to_evacuate, immediate_hazard,
                    ai_rationale, triage_mode, priority_score, status,
                    created_by_user_id, reporter_type, tracking_code, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (inc_id, inc["zone_id"], inc["description"], inc["location_text"],
                 inc["reported_category"], inc["people_affected"],
                 inc["ai_category"], inc["ai_urgency"],
                 1 if inc.get("vulnerable_flag") else 0,
                 inc.get("vulnerable_group", "None reported"),
                 1 if inc.get("stranded") else 0,
                 1 if inc.get("unable_to_evacuate") else 0,
                 1 if inc.get("immediate_hazard") else 0,
                 inc.get("ai_rationale", ""),
                 inc.get("triage_mode", "seeded"),
                 inc.get("priority_score", 0),
                 inc.get("status", "Triaged"),
                 owner_id, "seeded", trk_code, now, now),
            )
            # Record initial triage update
            conn.execute(
                """INSERT INTO incident_updates
                   (update_id, incident_id, old_status, new_status, note, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (_generate_update_id(), inc_id, "New", inc.get("status", "Triaged"),
                 "Seeded demo incident — pre-triaged for demonstration", now),
            )


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

def get_zones(db_path: str | None = None) -> list[dict]:
    """Return all zones as a list of dicts."""
    conn = _get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM zones ORDER BY zone_name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

def create_incident(payload: dict, db_path: str | None = None) -> str:
    """
    Insert a new incident. Returns the generated incident_id.

    Required payload keys: zone_id, description
    Optional: location_text, reported_category, people_affected, created_by_user_id,
              reporter_type, tracking_code, photo_data_url, and all AI triage fields.
    """
    conn = _get_connection(db_path)
    inc_id = _generate_incident_id()
    now = _now_iso()
    trk_code = payload.get("tracking_code") or _generate_tracking_code()
    reporter_type = payload.get("reporter_type") or (
        "authenticated" if payload.get("created_by_user_id") else "guest"
    )
    try:
        conn.execute(
            """INSERT INTO incidents
               (incident_id, zone_id, description, location_text, reported_category,
                people_affected, ai_category, ai_urgency, vulnerable_flag,
                vulnerable_group, stranded, unable_to_evacuate, immediate_hazard,
                ai_rationale, triage_mode, priority_score, operator_priority,
                status, assigned_team_id, created_by_user_id, reporter_type,
                tracking_code, photo_data_url, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                inc_id,
                payload["zone_id"],
                payload["description"],
                payload.get("location_text", ""),
                payload.get("reported_category", "Other"),
                payload.get("people_affected", 0),
                payload.get("ai_category"),
                payload.get("ai_urgency"),
                1 if payload.get("vulnerable_flag") else 0,
                payload.get("vulnerable_group", "None reported"),
                1 if payload.get("stranded") else 0,
                1 if payload.get("unable_to_evacuate") else 0,
                1 if payload.get("immediate_hazard") else 0,
                payload.get("ai_rationale", ""),
                payload.get("triage_mode"),
                payload.get("priority_score", 0),
                payload.get("operator_priority"),
                payload.get("status", "New"),
                payload.get("assigned_team_id"),
                payload.get("created_by_user_id"),
                reporter_type,
                trk_code,
                payload.get("photo_data_url"),
                now,
                now,
            ),
        )
        # Record creation update
        conn.execute(
            """INSERT INTO incident_updates
               (update_id, incident_id, old_status, new_status, note, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (_generate_update_id(), inc_id, None, payload.get("status", "New"),
             "Incident created", now),
        )
        conn.commit()
        return inc_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_incidents(filters: dict | None = None, db_path: str | None = None) -> list[dict]:
    """
    List incidents, optionally filtered.

    Supported filters:
      - status (str): exact match
      - zone_id (str): exact match
      - min_priority (float): priority_score >= value

    Results are ordered by priority_score descending (critical first).
    """
    conn = _get_connection(db_path)
    try:
        query = "SELECT * FROM incidents WHERE 1=1"
        params: list[Any] = []

        if filters:
            if "status" in filters:
                query += " AND status = ?"
                params.append(filters["status"])
            if "zone_id" in filters:
                query += " AND zone_id = ?"
                params.append(filters["zone_id"])
            if "min_priority" in filters:
                query += " AND priority_score >= ?"
                params.append(filters["min_priority"])

        query += " ORDER BY priority_score DESC, created_at ASC"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_incident(incident_id: str, db_path: str | None = None) -> Optional[dict]:
    """Return a single incident by ID, or None."""
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_incident_workflow(
    incident_id: str,
    new_status: str,
    assigned_team_id: str | None = None,
    note: str | None = None,
    operator_priority: float | None = None,
    db_path: str | None = None,
) -> dict:
    """
    Advance an incident through the workflow. Returns the updated incident dict.

    Validates:
    - Incident exists.
    - Status transition is allowed.
    - If assigning a team: team must be Available and not assigned elsewhere.
    - Duplicate assignment is prevented via transaction.

    On Team Assigned: marks the team as Assigned.
    On Resolved: releases the assigned team back to Available.
    """
    conn = _get_connection(db_path)
    try:
        # Fetch current incident
        row = conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Incident {incident_id} not found")

        current = dict(row)
        old_status = current["status"]

        # Validate transition
        allowed = STATUS_TRANSITIONS.get(old_status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{old_status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            )

        now = _now_iso()
        update_note = note or f"Status changed: {old_status} → {new_status}"

        # Handle team assignment
        if new_status == "Team Assigned":
            if not assigned_team_id:
                raise ValueError("Team assignment requires assigned_team_id")

            # Check team availability (within the same transaction)
            team = conn.execute(
                "SELECT * FROM response_teams WHERE team_id = ?",
                (assigned_team_id,),
            ).fetchone()

            if not team:
                raise ValueError(f"Team {assigned_team_id} not found")
            if team["status"] != "Available":
                raise ValueError(
                    f"Team '{team['team_name']}' is currently {team['status']} "
                    f"and cannot be assigned"
                )

            # Mark team as assigned
            conn.execute(
                """UPDATE response_teams
                   SET status = 'Assigned', current_incident_id = ?
                   WHERE team_id = ? AND status = 'Available'""",
                (incident_id, assigned_team_id),
            )
            # Verify the update actually happened (race condition guard)
            if conn.execute(
                "SELECT changes()"
            ).fetchone()[0] == 0:
                raise ValueError(
                    f"Team {assigned_team_id} was assigned by another operation"
                )

        # Release team on resolution
        if new_status == "Resolved" and current.get("assigned_team_id"):
            conn.execute(
                """UPDATE response_teams
                   SET status = 'Available', current_incident_id = NULL
                   WHERE team_id = ?""",
                (current["assigned_team_id"],),
            )

        # Release team when moving back to In Review from Team Assigned
        if new_status == "In Review" and old_status == "Team Assigned" and current.get("assigned_team_id"):
            conn.execute(
                """UPDATE response_teams
                   SET status = 'Available', current_incident_id = NULL
                   WHERE team_id = ?""",
                (current["assigned_team_id"],),
            )
            assigned_team_id = None  # Clear assignment on the incident too

        # Build update fields
        update_fields = {
            "status": new_status,
            "updated_at": now,
        }
        if assigned_team_id is not None or new_status == "In Review":
            update_fields["assigned_team_id"] = assigned_team_id
        if operator_priority is not None:
            update_fields["operator_priority"] = operator_priority

        set_clause = ", ".join(f"{k} = ?" for k in update_fields)
        values = list(update_fields.values()) + [incident_id]

        conn.execute(
            f"UPDATE incidents SET {set_clause} WHERE incident_id = ?",
            values,
        )

        # Record the update
        conn.execute(
            """INSERT INTO incident_updates
               (update_id, incident_id, old_status, new_status,
                assigned_team_id, note, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_generate_update_id(), incident_id, old_status, new_status,
             assigned_team_id, update_note, now),
        )

        conn.commit()

        # Return refreshed incident
        return dict(
            conn.execute(
                "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        )

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Response Teams
# ---------------------------------------------------------------------------

def get_response_teams(db_path: str | None = None) -> list[dict]:
    """Return all response teams as a list of dicts."""
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM response_teams ORDER BY team_name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Incident Updates / Timeline
# ---------------------------------------------------------------------------

def get_incident_updates(incident_id: str, db_path: str | None = None) -> list[dict]:
    """Return all updates for an incident, oldest first."""
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM incident_updates
               WHERE incident_id = ?
               ORDER BY updated_at ASC""",
            (incident_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Demo Reset
# ---------------------------------------------------------------------------

def reset_demo_data(db_path: str | None = None) -> None:
    """
    Clear all incidents, updates, and reset teams to Available.
    Re-seed demo data. Used for demonstration resets.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute("DELETE FROM incident_updates")
        conn.execute("DELETE FROM incidents")
        conn.execute(
            "UPDATE response_teams SET status = 'Available', current_incident_id = NULL"
        )
        # Re-seed demo incidents
        seed = _load_json(SEED_DATA_PATH)
        now = _now_iso()
        for idx, inc in enumerate(seed.get("demo_incidents", [])):
            inc_id = _generate_incident_id()
            owner_id = "usr_cit_01" if idx == 0 else "usr_cit_02"
            trk_code = _generate_tracking_code()
            conn.execute(
                """INSERT INTO incidents
                   (incident_id, zone_id, description, location_text, reported_category,
                    people_affected, ai_category, ai_urgency, vulnerable_flag,
                    vulnerable_group, stranded, unable_to_evacuate, immediate_hazard,
                    ai_rationale, triage_mode, priority_score, status,
                    created_by_user_id, reporter_type, tracking_code, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (inc_id, inc["zone_id"], inc["description"], inc["location_text"],
                 inc["reported_category"], inc["people_affected"],
                 inc["ai_category"], inc["ai_urgency"],
                 1 if inc.get("vulnerable_flag") else 0,
                 inc.get("vulnerable_group", "None reported"),
                 1 if inc.get("stranded") else 0,
                 1 if inc.get("unable_to_evacuate") else 0,
                 1 if inc.get("immediate_hazard") else 0,
                 inc.get("ai_rationale", ""),
                 inc.get("triage_mode", "seeded"),
                 inc.get("priority_score", 0),
                 inc.get("status", "Triaged"),
                 owner_id, "seeded", trk_code, now, now),
            )
            conn.execute(
                """INSERT INTO incident_updates
                   (update_id, incident_id, old_status, new_status, note, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (_generate_update_id(), inc_id, "New", inc.get("status", "Triaged"),
                 "Seeded demo incident — pre-triaged for demonstration", now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Users & Role-Scoped Queries
# ---------------------------------------------------------------------------

def get_user_by_email(email: str, db_path: str | None = None) -> Optional[dict]:
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: str, db_path: str | None = None) -> Optional[dict]:
    conn = _get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_incidents_for_citizen(user_id: str, db_path: str | None = None) -> list[dict]:
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE created_by_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_incidents_for_team(team_id: str, db_path: str | None = None) -> list[dict]:
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE assigned_team_id = ? ORDER BY priority_score DESC, created_at ASC",
            (team_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_incident_by_tracking(incident_id: str, tracking_code: str, db_path: str | None = None) -> Optional[dict]:
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ? AND tracking_code = ?",
            (incident_id.strip().upper(), tracking_code.strip().upper()),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _load_json(path: str) -> Any:
    """Load and return parsed JSON from a file path."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _now_iso() -> str:
    """Return current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _generate_incident_id() -> str:
    """Generate a short, human-friendly incident ID."""
    return f"FIQ-{uuid.uuid4().hex[:8].upper()}"


def _generate_tracking_code() -> str:
    """Generate a secure citizen tracking reference."""
    return f"TRK-{secrets.token_hex(4).upper()}"


def _generate_update_id() -> str:
    """Generate a unique update ID."""
    return f"UPD-{uuid.uuid4().hex[:10].upper()}"
