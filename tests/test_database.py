"""
FloodIQ — Database Tests

Uses a temporary SQLite database for each test to avoid modifying the demo database.
Tests cover initialization, seeding, CRUD, workflow transitions, and transaction safety.
"""

import os
import sys
import tempfile
import pytest

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import (
    init_db,
    get_zones,
    create_incident,
    list_incidents,
    get_incident,
    get_response_teams,
    update_incident_workflow,
    get_incident_updates,
    reset_demo_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database path and initialize it."""
    path = str(tmp_path / "test_floodiq.db")
    init_db(path)
    return path


# ---------------------------------------------------------------------------
# Initialization & Seeding
# ---------------------------------------------------------------------------

class TestInitialization:
    def test_database_initializes(self, db_path):
        """Database should initialize without errors."""
        # init_db already called by fixture; just verify no exception
        assert os.path.exists(db_path)

    def test_zones_are_seeded(self, db_path):
        """Zones table should contain the 5 Hyderabad pilot zones."""
        zones = get_zones(db_path)
        assert len(zones) == 5
        zone_ids = {z["zone_id"] for z in zones}
        assert "begumpet" in zone_ids
        assert "musi_riverfront" in zone_ids

    def test_response_teams_are_seeded(self, db_path):
        """Response teams should be seeded."""
        teams = get_response_teams(db_path)
        assert len(teams) == 5
        specialties = {t["specialty"] for t in teams}
        assert "Water Rescue" in specialties
        assert "Medical Emergency" in specialties

    def test_demo_incidents_are_seeded(self, db_path):
        """Two demo incidents should be seeded."""
        incidents = list_incidents(db_path=db_path)
        assert len(incidents) == 2

    def test_no_duplicate_seeding(self, db_path):
        """Calling init_db again should not duplicate data."""
        init_db(db_path)
        zones = get_zones(db_path)
        assert len(zones) == 5
        teams = get_response_teams(db_path)
        assert len(teams) == 5

    def test_zone_fields(self, db_path):
        """Each zone should have all required fields."""
        zones = get_zones(db_path)
        for z in zones:
            assert "zone_id" in z
            assert "zone_name" in z
            assert "latitude" in z
            assert "longitude" in z
            assert 0 <= z["drainage_score"] <= 100
            assert 0 <= z["low_lying_score"] <= 100
            assert len(z["description"]) > 0


# ---------------------------------------------------------------------------
# Incident CRUD
# ---------------------------------------------------------------------------

class TestIncidentCRUD:
    def test_create_incident(self, db_path):
        """Should create an incident and return an ID."""
        inc_id = create_incident(
            {
                "zone_id": "begumpet",
                "description": "Test incident — water on road",
                "location_text": "Near Begumpet airport",
                "reported_category": "Road Blockage",
                "people_affected": 2,
            },
            db_path=db_path,
        )
        assert inc_id.startswith("FIQ-")
        assert len(inc_id) == 12  # FIQ- + 8 hex chars

    def test_get_created_incident(self, db_path):
        """Should retrieve a created incident by ID."""
        inc_id = create_incident(
            {
                "zone_id": "ameerpet",
                "description": "Flooded basement",
                "people_affected": 5,
            },
            db_path=db_path,
        )
        inc = get_incident(inc_id, db_path)
        assert inc is not None
        assert inc["zone_id"] == "ameerpet"
        assert inc["description"] == "Flooded basement"
        assert inc["people_affected"] == 5
        assert inc["status"] == "New"

    def test_get_nonexistent_incident(self, db_path):
        """Should return None for a nonexistent ID."""
        inc = get_incident("FIQ-DOESNOTEXIST", db_path)
        assert inc is None

    def test_list_incidents_ordered_by_priority(self, db_path):
        """Incidents should be ordered by priority_score descending."""
        incidents = list_incidents(db_path=db_path)
        scores = [inc["priority_score"] for inc in incidents]
        assert scores == sorted(scores, reverse=True)

    def test_list_incidents_filter_by_status(self, db_path):
        """Should filter incidents by status."""
        # Create a New incident
        create_incident(
            {"zone_id": "begumpet", "description": "New incident"},
            db_path=db_path,
        )
        new_incidents = list_incidents({"status": "New"}, db_path)
        assert all(inc["status"] == "New" for inc in new_incidents)
        assert len(new_incidents) >= 1

    def test_list_incidents_filter_by_zone(self, db_path):
        """Should filter incidents by zone_id."""
        create_incident(
            {"zone_id": "kukatpally", "description": "Kukatpally test"},
            db_path=db_path,
        )
        filtered = list_incidents({"zone_id": "kukatpally"}, db_path)
        assert all(inc["zone_id"] == "kukatpally" for inc in filtered)

    def test_incident_creation_records_update(self, db_path):
        """Creating an incident should record an initial update."""
        inc_id = create_incident(
            {"zone_id": "begumpet", "description": "Timeline test"},
            db_path=db_path,
        )
        updates = get_incident_updates(inc_id, db_path)
        assert len(updates) == 1
        assert updates[0]["new_status"] == "New"


# ---------------------------------------------------------------------------
# Workflow Transitions
# ---------------------------------------------------------------------------

class TestWorkflowTransitions:
    def _create_new_incident(self, db_path) -> str:
        return create_incident(
            {
                "zone_id": "begumpet",
                "description": "Workflow test incident",
                "people_affected": 1,
            },
            db_path=db_path,
        )

    def test_valid_transition_new_to_triaged(self, db_path):
        inc_id = self._create_new_incident(db_path)
        result = update_incident_workflow(inc_id, "Triaged", db_path=db_path)
        assert result["status"] == "Triaged"

    def test_valid_transition_triaged_to_in_review(self, db_path):
        inc_id = self._create_new_incident(db_path)
        update_incident_workflow(inc_id, "Triaged", db_path=db_path)
        result = update_incident_workflow(inc_id, "In Review", db_path=db_path)
        assert result["status"] == "In Review"

    def test_invalid_transition_new_to_resolved(self, db_path):
        """Should reject invalid status transitions."""
        inc_id = self._create_new_incident(db_path)
        with pytest.raises(ValueError, match="Cannot transition"):
            update_incident_workflow(inc_id, "Resolved", db_path=db_path)

    def test_invalid_transition_new_to_in_progress(self, db_path):
        inc_id = self._create_new_incident(db_path)
        with pytest.raises(ValueError, match="Cannot transition"):
            update_incident_workflow(inc_id, "In Progress", db_path=db_path)

    def test_nonexistent_incident_raises(self, db_path):
        with pytest.raises(ValueError, match="not found"):
            update_incident_workflow("FIQ-NOPE0000", "Triaged", db_path=db_path)

    def test_status_history_is_recorded(self, db_path):
        """Every transition should add an update record."""
        inc_id = self._create_new_incident(db_path)
        update_incident_workflow(inc_id, "Triaged", db_path=db_path)
        update_incident_workflow(inc_id, "In Review", db_path=db_path)

        updates = get_incident_updates(inc_id, db_path)
        # 1 creation + 2 transitions
        assert len(updates) == 3
        statuses = [(u["old_status"], u["new_status"]) for u in updates]
        assert (None, "New") in statuses
        assert ("New", "Triaged") in statuses
        assert ("Triaged", "In Review") in statuses

    def test_operator_note_recorded(self, db_path):
        inc_id = self._create_new_incident(db_path)
        update_incident_workflow(
            inc_id, "Triaged", note="Operator reviewed", db_path=db_path
        )
        updates = get_incident_updates(inc_id, db_path)
        assert any("Operator reviewed" in u["note"] for u in updates)


# ---------------------------------------------------------------------------
# Team Assignment & Duplicate Prevention
# ---------------------------------------------------------------------------

class TestTeamAssignment:
    def _create_reviewed_incident(self, db_path) -> str:
        inc_id = create_incident(
            {"zone_id": "musi_riverfront", "description": "Rescue needed"},
            db_path=db_path,
        )
        update_incident_workflow(inc_id, "Triaged", db_path=db_path)
        update_incident_workflow(inc_id, "In Review", db_path=db_path)
        return inc_id

    def test_assign_team(self, db_path):
        inc_id = self._create_reviewed_incident(db_path)
        teams = get_response_teams(db_path)
        team_id = teams[0]["team_id"]

        result = update_incident_workflow(
            inc_id, "Team Assigned", assigned_team_id=team_id, db_path=db_path
        )
        assert result["status"] == "Team Assigned"
        assert result["assigned_team_id"] == team_id

        # Team should now be Assigned
        updated_teams = get_response_teams(db_path)
        team = next(t for t in updated_teams if t["team_id"] == team_id)
        assert team["status"] == "Assigned"

    def test_duplicate_team_assignment_prevented(self, db_path):
        """The same team cannot be assigned to two active incidents."""
        inc1 = self._create_reviewed_incident(db_path)
        inc2 = self._create_reviewed_incident(db_path)

        teams = get_response_teams(db_path)
        team_id = teams[0]["team_id"]

        # Assign to first incident
        update_incident_workflow(
            inc1, "Team Assigned", assigned_team_id=team_id, db_path=db_path
        )

        # Attempt to assign the same team to second incident
        with pytest.raises(ValueError, match="currently Assigned"):
            update_incident_workflow(
                inc2, "Team Assigned", assigned_team_id=team_id, db_path=db_path
            )

    def test_team_assignment_requires_team_id(self, db_path):
        inc_id = self._create_reviewed_incident(db_path)
        with pytest.raises(ValueError, match="requires assigned_team_id"):
            update_incident_workflow(inc_id, "Team Assigned", db_path=db_path)

    def test_team_released_on_resolution(self, db_path):
        """Resolving an incident should release the assigned team."""
        inc_id = self._create_reviewed_incident(db_path)
        teams = get_response_teams(db_path)
        team_id = teams[0]["team_id"]

        update_incident_workflow(
            inc_id, "Team Assigned", assigned_team_id=team_id, db_path=db_path
        )
        update_incident_workflow(inc_id, "In Progress", db_path=db_path)
        update_incident_workflow(inc_id, "Resolved", db_path=db_path)

        # Team should be Available again
        updated_teams = get_response_teams(db_path)
        team = next(t for t in updated_teams if t["team_id"] == team_id)
        assert team["status"] == "Available"

    def test_nonexistent_team_raises(self, db_path):
        inc_id = self._create_reviewed_incident(db_path)
        with pytest.raises(ValueError, match="not found"):
            update_incident_workflow(
                inc_id, "Team Assigned",
                assigned_team_id="FAKE_TEAM", db_path=db_path
            )


# ---------------------------------------------------------------------------
# Demo Reset
# ---------------------------------------------------------------------------

class TestDemoReset:
    def test_reset_clears_and_reseeds(self, db_path):
        """Reset should clear user incidents and re-seed demo data."""
        # Create a custom incident
        create_incident(
            {"zone_id": "begumpet", "description": "User incident"},
            db_path=db_path,
        )
        incidents_before = list_incidents(db_path=db_path)
        assert len(incidents_before) == 3  # 2 seeded + 1 user

        reset_demo_data(db_path)

        incidents_after = list_incidents(db_path=db_path)
        assert len(incidents_after) == 2  # only seeded

        # Teams should all be Available
        teams = get_response_teams(db_path)
        assert all(t["status"] == "Available" for t in teams)

    def test_reset_preserves_zones(self, db_path):
        """Reset should not affect zone data."""
        reset_demo_data(db_path)
        zones = get_zones(db_path)
        assert len(zones) == 5


# ---------------------------------------------------------------------------
# Operator Priority Override
# ---------------------------------------------------------------------------

class TestOperatorPriority:
    def test_operator_priority_override(self, db_path):
        inc_id = create_incident(
            {"zone_id": "begumpet", "description": "Override test"},
            db_path=db_path,
        )
        update_incident_workflow(
            inc_id, "Triaged", operator_priority=85.0, db_path=db_path
        )
        inc = get_incident(inc_id, db_path)
        assert inc["operator_priority"] == 85.0
