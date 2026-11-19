"""
FloodIQ — AI Engine Tests

Tests cover:
  - Fallback triage keyword detection (elderly, children, disabled, stranded, rising water)
  - Schema consistency across AI and fallback triage
  - Safe error handling (no unhandled exceptions)
  - Triage mode flags ("ai" or "fallback")
  - Conservatism and explainable rationale output
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_engine import triage_incident, _fallback_triage
from config import INCIDENT_CATEGORIES, URGENCY_LEVELS, VULNERABLE_GROUPS


class TestFallbackTriageKeywords:
    def test_elderly_vulnerability_detection(self):
        desc = "Elderly grandmother cannot walk down the flooded stairs."
        result = _fallback_triage(desc, "Begumpet")
        assert result["vulnerable_flag"] is True
        assert result["vulnerable_group"] == "Elderly people"

    def test_children_vulnerability_detection(self):
        desc = "Two young children are crying as water entered the house."
        result = _fallback_triage(desc, "Khairatabad")
        assert result["vulnerable_flag"] is True
        assert result["vulnerable_group"] == "Children"

    def test_disability_vulnerability_detection(self):
        desc = "Wheelchair bound person stuck on ground floor."
        result = _fallback_triage(desc, "Ameerpet")
        assert result["vulnerable_flag"] is True
        assert result["vulnerable_group"] == "People with disabilities"

    def test_stranded_detection(self):
        desc = "We are completely stranded on the first floor terrace."
        result = _fallback_triage(desc, "Musi Riverfront")
        assert result["stranded"] is True
        assert result["unable_to_evacuate"] is True

    def test_immediate_hazard_rising_water(self):
        desc = "Water levels are continuing to rise rapidly."
        result = _fallback_triage(desc, "Musi Riverfront")
        assert result["immediate_hazard"] is True

    def test_people_count_extraction(self):
        desc = "Three people are stranded on the first floor."
        result = _fallback_triage(desc, "Musi Riverfront")
        assert result["people_affected"] == 3

    def test_water_rescue_category(self):
        desc = "Three people stranded in water near Musi river, need rescue boat."
        result = _fallback_triage(desc, "Musi Riverfront")
        assert result["ai_category"] == "Water Rescue"
        assert result["ai_urgency"] == "Critical"

    def test_road_blockage_category(self):
        desc = "Waterlogged road near metro station with heavy traffic jam."
        result = _fallback_triage(desc, "Ameerpet")
        assert result["ai_category"] == "Road Blockage"
        assert result["ai_urgency"] == "Medium"
        assert result["vulnerable_flag"] is False


class TestIncidentAAndBScenarios:
    def test_incident_a_triage(self):
        """
        Master prompt Incident A:
        Heavy rain has caused water to enter a residential building near the Musi Riverfront.
        Three people are stranded on the first floor, including an elderly person. Water levels are continuing to rise.
        """
        desc = (
            "Heavy rain has caused water to enter a residential building near the Musi Riverfront. "
            "Three people are stranded on the first floor, including an elderly person. "
            "Water levels are continuing to rise."
        )
        res = triage_incident(desc, "Musi Riverfront", "Near Musi Bridge", people_affected=3)

        assert res["ai_category"] == "Water Rescue"
        assert res["ai_urgency"] == "Critical"
        assert res["stranded"] is True
        assert res["vulnerable_flag"] is True
        assert res["vulnerable_group"] == "Elderly people"
        assert res["immediate_hazard"] is True
        assert res["people_affected"] == 3

    def test_incident_b_triage(self):
        """
        Master prompt Incident B:
        Road near Ameerpet metro station is partially waterlogged after heavy rain.
        Traffic is affected but no vehicles are stuck.
        """
        desc = (
            "Road near Ameerpet metro station is partially waterlogged after heavy rain. "
            "Traffic is affected but no vehicles are stuck."
        )
        res = triage_incident(desc, "Ameerpet", "Ameerpet Metro", people_affected=0)

        assert res["ai_category"] == "Road Blockage"
        assert res["ai_urgency"] == "Medium"
        assert res["stranded"] is False
        assert res["vulnerable_flag"] is False
        assert res["immediate_hazard"] is False


class TestSchemaIntegrity:
    def test_all_keys_present_in_output(self):
        res = triage_incident("Just normal rain outside", "Begumpet")
        expected_keys = {
            "ai_category",
            "ai_urgency",
            "people_affected",
            "vulnerable_flag",
            "vulnerable_group",
            "stranded",
            "unable_to_evacuate",
            "immediate_hazard",
            "ai_rationale",
            "triage_mode",
        }
        assert set(res.keys()) == expected_keys
        assert res["ai_category"] in INCIDENT_CATEGORIES
        assert res["ai_urgency"] in URGENCY_LEVELS
        assert res["vulnerable_group"] in VULNERABLE_GROUPS
        assert res["triage_mode"] in ("ai", "fallback")
        assert isinstance(res["ai_rationale"], str) and len(res["ai_rationale"]) > 0
