"""
FloodIQ — Response Engine Tests

Tests cover:
  - Priority calculation formula correctness and bounds
  - Calibrated demonstration scenarios:
      * Incident A target: ~92 (Critical)
      * Incident B target: ~48 (Moderate)
  - Factor breakdown accuracy
  - Haversine distance calculation
  - Response team recommendation based on specialty and proximity
  - Exclusion of unavailable response teams
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_engine import (
    calculate_priority,
    classify_priority,
    haversine_distance,
    recommend_team,
)


class TestPriorityCalculation:
    def test_incident_a_target_92(self):
        """
        Incident A: 3 residents stranded on first floor, elderly person, water continues to rise.
        Target priority: ~92 / 100 (Critical)
        """
        triage_a = {
            "ai_category": "Water Rescue",
            "ai_urgency": "Critical",
            "people_affected": 3,
            "vulnerable_flag": True,
            "vulnerable_group": "Elderly people",
            "stranded": True,
            "unable_to_evacuate": True,
            "immediate_hazard": True,
        }
        res = calculate_priority(triage_a)
        score = res["priority_score"]

        # Assert target within 1 point of 92
        assert abs(score - 92.0) <= 1.0, f"Expected ~92, got {score}"
        assert res["priority_band"] == "Critical"
        assert res["factors"]["vulnerability"]["contribution"] == 25.0
        assert res["factors"]["stranded"]["contribution"] == 25.0

    def test_incident_b_target_48(self):
        """
        Incident B: Road partially waterlogged, traffic affected, no trapped residents.
        Target priority: ~48 / 100 (Moderate)
        """
        triage_b = {
            "ai_category": "Road Blockage",
            "ai_urgency": "Medium",
            "people_affected": 0,
            "vulnerable_flag": False,
            "vulnerable_group": "None reported",
            "stranded": False,
            "unable_to_evacuate": False,
            "immediate_hazard": False,
        }
        res = calculate_priority(triage_b)
        score = res["priority_score"]

        # Assert target within 1 point of 48
        assert abs(score - 48.0) <= 1.0, f"Expected ~48, got {score}"
        assert res["priority_band"] == "Moderate"

    def test_priority_score_bounds(self):
        """Score must always be strictly between 0 and 100."""
        min_triage = {
            "ai_category": "Other",
            "ai_urgency": "Low",
            "people_affected": 0,
            "vulnerable_flag": False,
            "stranded": False,
            "immediate_hazard": False,
        }
        res_min = calculate_priority(min_triage)
        assert 0.0 <= res_min["priority_score"] <= 100.0

        max_triage = {
            "ai_category": "Water Rescue",
            "ai_urgency": "Critical",
            "people_affected": 50,
            "vulnerable_flag": True,
            "stranded": True,
            "immediate_hazard": True,
        }
        res_max = calculate_priority(max_triage)
        assert 0.0 <= res_max["priority_score"] <= 100.0

    def test_factor_contributions_sum_to_total(self):
        triage = {
            "ai_category": "Flooded Building",
            "ai_urgency": "High",
            "people_affected": 5,
            "vulnerable_flag": True,
            "stranded": True,
            "immediate_hazard": False,
        }
        res = calculate_priority(triage)
        factors = res["factors"]
        total_factors = sum(f["contribution"] for f in factors.values())
        assert abs(total_factors - res["priority_score"]) <= 0.2


class TestHaversineDistance:
    def test_same_coordinates(self):
        assert haversine_distance(17.385, 78.4867, 17.385, 78.4867) == 0.0

    def test_known_hyderabad_distance(self):
        # Begumpet (17.44, 78.498) to Musi Riverfront (17.37, 78.480)
        # Expected distance roughly 7.5 to 8.5 km
        d = haversine_distance(17.4400, 78.4983, 17.3700, 78.4800)
        assert 7.0 < d < 9.0


class TestTeamRecommendation:
    @pytest.fixture
    def mock_teams(self):
        return [
            {
                "team_id": "wrt_01",
                "team_name": "Water Rescue Alpha",
                "specialty": "Water Rescue",
                "base_zone": "khairatabad",
                "latitude": 17.4100,
                "longitude": 78.4700,
                "status": "Available",
            },
            {
                "team_id": "mrt_01",
                "team_name": "Medical Response Unit 1",
                "specialty": "Medical Emergency",
                "base_zone": "begumpet",
                "latitude": 17.4420,
                "longitude": 78.5000,
                "status": "Available",
            },
            {
                "team_id": "get_01",
                "team_name": "General Emergency Team 1",
                "specialty": "General Emergency",
                "base_zone": "ameerpet",
                "latitude": 17.4380,
                "longitude": 78.4500,
                "status": "Available",
            },
        ]

    def test_water_rescue_recommends_water_team(self, mock_teams):
        incident = {
            "ai_category": "Water Rescue",
            "zone_id": "khairatabad",
            "latitude": 17.4062,
            "longitude": 78.4691,
        }
        res = recommend_team(incident, mock_teams)
        assert res["recommended_team"] is not None
        assert res["recommended_team"]["team_id"] == "wrt_01"
        assert res["recommended_team"]["specialty"] == "Water Rescue"
        assert "Water Rescue Alpha" in res["match_reason"]

    def test_medical_emergency_recommends_medical_team(self, mock_teams):
        incident = {
            "ai_category": "Medical Emergency",
            "zone_id": "begumpet",
            "latitude": 17.4400,
            "longitude": 78.4983,
        }
        res = recommend_team(incident, mock_teams)
        assert res["recommended_team"] is not None
        assert res["recommended_team"]["team_id"] == "mrt_01"
        assert res["recommended_team"]["specialty"] == "Medical Emergency"

    def test_road_blockage_recommends_general_team(self, mock_teams):
        incident = {
            "ai_category": "Road Blockage",
            "zone_id": "ameerpet",
            "latitude": 17.4375,
            "longitude": 78.4483,
        }
        res = recommend_team(incident, mock_teams)
        assert res["recommended_team"] is not None
        assert res["recommended_team"]["team_id"] == "get_01"

    def test_unavailable_teams_are_excluded(self, mock_teams):
        # Mark water team as Assigned
        mock_teams[0]["status"] = "Assigned"

        incident = {
            "ai_category": "Water Rescue",
            "zone_id": "khairatabad",
            "latitude": 17.4100,
            "longitude": 78.4700,
        }
        res = recommend_team(incident, mock_teams)
        # Should fallback to an available team (General Emergency)
        assert res["recommended_team"]["team_id"] != "wrt_01"
        assert res["recommended_team"]["status"] == "Available"

    def test_all_unavailable_teams(self, mock_teams):
        for t in mock_teams:
            t["status"] = "Unavailable"

        incident = {"ai_category": "Water Rescue", "zone_id": "begumpet"}
        res = recommend_team(incident, mock_teams)
        assert res["recommended_team"] is None
        assert res["available_team_count"] == 0
        assert "No response teams are currently Available" in res["match_reason"]
