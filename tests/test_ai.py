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
        res = _fallback_triage(desc, "Musi Riverfront", "Near Musi Bridge", people_affected=3)

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
        res = _fallback_triage(desc, "Ameerpet", "Ameerpet Metro", people_affected=0)

        assert res["ai_category"] == "Road Blockage"
        assert res["ai_urgency"] in ("Medium", "Low")
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
            "medical_emergency",
            "rescue_required",
            "recommended_response_category",
            "ai_rationale",
            "triage_mode",
        }
        assert set(res.keys()) == expected_keys
        assert res["ai_category"] in INCIDENT_CATEGORIES
        assert res["ai_urgency"] in URGENCY_LEVELS
        assert res["vulnerable_group"] in VULNERABLE_GROUPS
        assert res["triage_mode"] in ("groq", "rule_based")
        assert isinstance(res["ai_rationale"], str) and len(res["ai_rationale"]) > 0


class TestGroqIntegrationAndFallback:
    def setup_method(self):
        import ai_engine
        ai_engine.reset_ai_state()

    def test_placeholder_key_skips_api_and_uses_fallback(self, monkeypatch):
        import ai_engine
        import config

        monkeypatch.setattr(config, "GROQ_API_KEY", "your_groq_api_key_here")
        monkeypatch.setattr(config, "OFFLINE_MODE", False)
        res = ai_engine.triage_incident("Elderly resident stranded on roof", "Musi Riverfront")
        assert res["triage_mode"] == "rule_based"
        status = ai_engine.get_ai_status()
        assert status["fallback_active"] is True
        assert status["latest_provider_status"] == "not_configured"

    def test_groq_valid_structured_json_parsed_and_cached(self, monkeypatch):
        import json
        from unittest.mock import MagicMock
        import groq
        import ai_engine
        import config

        monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake_test_key_123")
        monkeypatch.setattr(config, "OFFLINE_MODE", False)

        payload = {
            "ai_category": "Water Rescue",
            "ai_urgency": "Critical",
            "people_affected": 4,
            "vulnerable_flag": True,
            "vulnerable_group": "Elderly people",
            "stranded": True,
            "unable_to_evacuate": True,
            "immediate_hazard": True,
            "medical_emergency": False,
            "rescue_required": True,
            "recommended_response_category": "Water Rescue / Boat Unit",
            "ai_rationale": "Four residents including elderly stranded in rising water.",
        }
        mock_msg = MagicMock()
        mock_msg.content = json.dumps(payload)
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        monkeypatch.setattr(groq, "Groq", lambda **kwargs: mock_client)

        res1 = ai_engine.triage_incident("4 people stranded", "Musi Riverfront", people_affected=4)
        assert res1["triage_mode"] == "groq"
        assert res1["ai_category"] == "Water Rescue"
        assert res1["ai_urgency"] == "Critical"
        assert res1["people_affected"] == 4
        assert res1["vulnerable_flag"] is True
        assert mock_client.chat.completions.create.call_count == 1

        # Second call with identical normalized content hits cache without calling Groq
        res2 = ai_engine.triage_incident("  4  people   stranded ", "musi riverfront", people_affected=4)
        assert res2["triage_mode"] == "groq"
        assert mock_client.chat.completions.create.call_count == 1
        assert ai_engine.get_ai_status()["cache_hits"] == 1

    def test_groq_malformed_json_falls_back(self, monkeypatch):
        from unittest.mock import MagicMock
        import groq
        import ai_engine
        import config

        monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake_test_key_123")
        monkeypatch.setattr(config, "OFFLINE_MODE", False)

        mock_msg = MagicMock()
        mock_msg.content = "{not valid json"
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        monkeypatch.setattr(groq, "Groq", lambda **kwargs: mock_client)

        res = ai_engine.triage_incident("Elderly person stranded on roof", "Musi Riverfront")
        assert res["triage_mode"] == "rule_based"
        assert ai_engine.get_ai_status()["latest_provider_status"] == "validation_error"

    def test_groq_timeout_retries_bounded_then_falls_back(self, monkeypatch):
        from unittest.mock import MagicMock
        import httpx
        import groq
        import ai_engine
        import config

        monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake_test_key_123")
        monkeypatch.setattr(config, "OFFLINE_MODE", False)
        monkeypatch.setattr(config, "GROQ_MAX_RETRIES", 1)
        monkeypatch.setattr(ai_engine.time, "sleep", lambda _: None)

        mock_client = MagicMock()
        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        mock_client.chat.completions.create.side_effect = groq.APITimeoutError(request=req)
        monkeypatch.setattr(groq, "Groq", lambda **kwargs: mock_client)

        res = ai_engine.triage_incident("Elderly person stranded on roof", "Musi Riverfront")
        assert res["triage_mode"] == "rule_based"
        assert mock_client.chat.completions.create.call_count == 2
        assert ai_engine.get_ai_status()["latest_provider_status"] == "provider_error"

    def test_groq_rate_limit_429_respects_retry_after_and_cooldown(self, monkeypatch):
        from unittest.mock import MagicMock
        import httpx
        import groq
        import ai_engine
        import config

        monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_fake_test_key_123")
        monkeypatch.setattr(config, "OFFLINE_MODE", False)
        monkeypatch.setattr(config, "GROQ_MAX_RETRIES", 0)

        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        resp = httpx.Response(429, headers={"Retry-After": "45"}, request=req)
        err = groq.RateLimitError("Rate limit exceeded", response=resp, body=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = err
        monkeypatch.setattr(groq, "Groq", lambda **kwargs: mock_client)

        res1 = ai_engine.triage_incident("Water rising near bridge", "Musi Riverfront")
        assert res1["triage_mode"] == "rule_based"
        status = ai_engine.get_ai_status()
        assert status["rate_limited"] is True
        assert status["cooldown_remaining_seconds"] > 0

        # Next distinct incident during active cooldown skips Groq API entirely
        res2 = ai_engine.triage_incident("Road flooded near metro", "Ameerpet")
        assert res2["triage_mode"] == "rule_based"
        assert mock_client.chat.completions.create.call_count == 1


@pytest.mark.skipif(
    not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") == "your_groq_api_key_here",
    reason="GROQ_API_KEY is not configured; skipping real-network Groq integration test.",
)
def test_live_groq_api_integration():
    import ai_engine
    import config

    ai_engine.reset_ai_state()
    res = ai_engine.triage_incident(
        description="Two elderly residents are stranded on the first floor near Chaderghat Bridge as floodwater rises.",
        zone_name="Musi Riverfront",
        location_text="Chaderghat Bridge",
        people_affected=2,
    )
    assert res["triage_mode"] == "groq"
    assert res["ai_category"] in INCIDENT_CATEGORIES
    assert res["ai_urgency"] in URGENCY_LEVELS
    assert res["people_affected"] == 2
    assert res["vulnerable_flag"] is True
    assert ai_engine.get_ai_status()["model"] == config.GROQ_MODEL
