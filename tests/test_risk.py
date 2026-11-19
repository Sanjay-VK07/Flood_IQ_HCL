"""
FloodIQ — Risk Engine Tests

Tests cover:
  - Rainfall normalization
  - Risk score calculation and formula correctness
  - Risk level thresholds
  - Score clamping (0–100)
  - Invalid/edge-case inputs
  - Full zone evaluation pipeline
  - Preparedness checklist generation
  - Risk summary aggregation
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from risk_engine import (
    normalize_rainfall,
    classify_risk,
    calculate_risk_score,
    evaluate_zones,
    get_risk_summary,
)
from config import (
    RISK_WEIGHT_RAINFALL,
    RISK_WEIGHT_DRAINAGE,
    RISK_WEIGHT_LOWLYING,
    RAINFALL_NORM_CEILING,
)


# ---------------------------------------------------------------------------
# Sample zones for testing
# ---------------------------------------------------------------------------

SAMPLE_ZONES = [
    {
        "zone_id": "test_zone_a",
        "zone_name": "Test Zone A",
        "latitude": 17.44,
        "longitude": 78.50,
        "drainage_score": 50,
        "low_lying_score": 40,
        "description": "Test zone A",
    },
    {
        "zone_id": "test_zone_b",
        "zone_name": "Test Zone B",
        "latitude": 17.37,
        "longitude": 78.48,
        "drainage_score": 75,
        "low_lying_score": 80,
        "description": "Test zone B — high vulnerability",
    },
]


# ---------------------------------------------------------------------------
# Rainfall Normalization
# ---------------------------------------------------------------------------

class TestRainfallNormalization:
    def test_zero_rainfall(self):
        assert normalize_rainfall(0.0) == 0.0

    def test_ceiling_rainfall(self):
        """Rainfall at ceiling should map to 100."""
        assert normalize_rainfall(RAINFALL_NORM_CEILING) == 100.0

    def test_half_ceiling(self):
        """Rainfall at half the ceiling should be ~50."""
        result = normalize_rainfall(RAINFALL_NORM_CEILING / 2)
        assert abs(result - 50.0) < 0.1

    def test_above_ceiling_capped(self):
        """Rainfall above ceiling should be capped at 100."""
        assert normalize_rainfall(200.0) == 100.0
        assert normalize_rainfall(999.0) == 100.0

    def test_negative_rainfall(self):
        """Negative rainfall should be treated as 0."""
        assert normalize_rainfall(-10.0) == 0.0

    def test_moderate_rainfall(self):
        """50 mm with 150 mm ceiling → 33.33."""
        result = normalize_rainfall(50.0, ceiling=150.0)
        assert abs(result - 33.33) < 0.1

    def test_heavy_rainfall(self):
        """100 mm with 150 mm ceiling → 66.67."""
        result = normalize_rainfall(100.0, ceiling=150.0)
        assert abs(result - 66.67) < 0.1

    def test_custom_ceiling(self):
        """Custom ceiling should work correctly."""
        assert normalize_rainfall(50.0, ceiling=100.0) == 50.0
        assert normalize_rainfall(100.0, ceiling=100.0) == 100.0

    def test_zero_ceiling(self):
        """Zero ceiling should return 100 (avoid division by zero)."""
        assert normalize_rainfall(10.0, ceiling=0.0) == 100.0


# ---------------------------------------------------------------------------
# Risk Level Classification
# ---------------------------------------------------------------------------

class TestRiskClassification:
    def test_low_range(self):
        assert classify_risk(0) == "Low"
        assert classify_risk(15) == "Low"
        assert classify_risk(29) == "Low"

    def test_moderate_range(self):
        assert classify_risk(30) == "Moderate"
        assert classify_risk(40) == "Moderate"
        assert classify_risk(49) == "Moderate"

    def test_high_range(self):
        assert classify_risk(50) == "High"
        assert classify_risk(60) == "High"
        assert classify_risk(74) == "High"

    def test_critical_range(self):
        assert classify_risk(75) == "Critical"
        assert classify_risk(90) == "Critical"
        assert classify_risk(100) == "Critical"

    def test_boundary_low_moderate(self):
        assert classify_risk(29) == "Low"
        assert classify_risk(30) == "Moderate"

    def test_boundary_moderate_high(self):
        assert classify_risk(49) == "Moderate"
        assert classify_risk(50) == "High"

    def test_boundary_high_critical(self):
        assert classify_risk(74) == "High"
        assert classify_risk(75) == "Critical"

    def test_negative_clamped(self):
        """Negative scores should clamp to 0 → Low."""
        assert classify_risk(-5) == "Low"

    def test_above_100_clamped(self):
        """Scores above 100 should clamp to 100 → Critical."""
        assert classify_risk(110) == "Critical"


# ---------------------------------------------------------------------------
# Risk Score Calculation
# ---------------------------------------------------------------------------

class TestRiskScoreCalculation:
    def test_all_zero(self):
        result = calculate_risk_score(0, 0, 0)
        assert result["risk_score"] == 0.0
        assert result["risk_level"] == "Low"

    def test_all_maximum(self):
        result = calculate_risk_score(100, 100, 100)
        assert result["risk_score"] == 100.0
        assert result["risk_level"] == "Critical"

    def test_formula_correctness(self):
        """Verify the formula: R = 0.40P + 0.30D + 0.30L."""
        r, d, l = 60.0, 50.0, 40.0
        expected = RISK_WEIGHT_RAINFALL * r + RISK_WEIGHT_DRAINAGE * d + RISK_WEIGHT_LOWLYING * l
        result = calculate_risk_score(r, d, l)
        assert abs(result["risk_score"] - expected) < 0.01

    def test_score_breakdown_present(self):
        """Breakdown should include all three components."""
        result = calculate_risk_score(50, 50, 50)
        breakdown = result["score_breakdown"]
        assert "rainfall" in breakdown
        assert "drainage" in breakdown
        assert "low_lying" in breakdown

    def test_breakdown_contributions_sum_to_score(self):
        """Sum of contributions should equal the total score."""
        result = calculate_risk_score(70, 55, 60)
        breakdown = result["score_breakdown"]
        total = sum(c["contribution"] for c in breakdown.values())
        assert abs(total - result["risk_score"]) < 0.01

    def test_breakdown_weights_match_config(self):
        result = calculate_risk_score(50, 50, 50)
        breakdown = result["score_breakdown"]
        assert breakdown["rainfall"]["weight"] == RISK_WEIGHT_RAINFALL
        assert breakdown["drainage"]["weight"] == RISK_WEIGHT_DRAINAGE
        assert breakdown["low_lying"]["weight"] == RISK_WEIGHT_LOWLYING

    def test_score_always_between_0_and_100(self):
        """Score should never exceed bounds, even with extreme inputs."""
        result_high = calculate_risk_score(200, 200, 200)
        assert 0 <= result_high["risk_score"] <= 100

        result_low = calculate_risk_score(-50, -50, -50)
        assert 0 <= result_low["risk_score"] <= 100

    def test_reasons_not_empty(self):
        result = calculate_risk_score(50, 50, 50)
        assert len(result["reasons"]) > 0

    def test_rainfall_dominance(self):
        """Rainfall should have the highest weight (40%)."""
        # Same value for all → rainfall contributes most
        result = calculate_risk_score(80, 80, 80)
        breakdown = result["score_breakdown"]
        assert breakdown["rainfall"]["contribution"] >= breakdown["drainage"]["contribution"]
        assert breakdown["rainfall"]["contribution"] >= breakdown["low_lying"]["contribution"]

    def test_scenario_normal_20mm(self):
        """20 mm rain, moderate vulnerability → score ~29.33, should be Low."""
        r_score = normalize_rainfall(20.0)  # ~13.33
        result = calculate_risk_score(r_score, 45, 35)
        # R = 0.40*13.33 + 0.30*45 + 0.30*35 = 29.33 → Low
        assert result["risk_score"] < 30
        assert result["risk_level"] == "Low"

    def test_scenario_heavy_100mm(self):
        """100 mm rain, high vulnerability → should be High or Critical."""
        r_score = normalize_rainfall(100.0)  # ~66.67
        result = calculate_risk_score(r_score, 75, 80)
        assert result["risk_level"] in ("High", "Critical")


# ---------------------------------------------------------------------------
# Rainfall Increase Changes Risk
# ---------------------------------------------------------------------------

class TestRainfallImpact:
    def test_increasing_rainfall_increases_risk(self):
        """Higher rainfall should always produce higher or equal risk scores."""
        low = calculate_risk_score(normalize_rainfall(20), 50, 50)
        mid = calculate_risk_score(normalize_rainfall(50), 50, 50)
        high = calculate_risk_score(normalize_rainfall(100), 50, 50)

        assert low["risk_score"] <= mid["risk_score"]
        assert mid["risk_score"] <= high["risk_score"]

    def test_rainfall_drives_level_change(self):
        """Increasing rainfall from 20mm to 100mm should change risk level."""
        low_rain = calculate_risk_score(normalize_rainfall(20), 60, 55)
        high_rain = calculate_risk_score(normalize_rainfall(100), 60, 55)

        low_levels = {"Low": 0, "Moderate": 1, "High": 2, "Critical": 3}
        assert low_levels[high_rain["risk_level"]] > low_levels[low_rain["risk_level"]]


# ---------------------------------------------------------------------------
# Full Zone Evaluation
# ---------------------------------------------------------------------------

class TestEvaluateZones:
    def test_all_zones_evaluated(self):
        rainfall = {
            "test_zone_a": {"rainfall_mm": 50, "source": "simulated"},
            "test_zone_b": {"rainfall_mm": 50, "source": "simulated"},
        }
        results = evaluate_zones(SAMPLE_ZONES, rainfall)
        assert len(results) == 2

    def test_results_sorted_by_risk_desc(self):
        """Results should be sorted by risk_score descending."""
        rainfall = {
            "test_zone_a": {"rainfall_mm": 20, "source": "simulated"},
            "test_zone_b": {"rainfall_mm": 100, "source": "simulated"},
        }
        results = evaluate_zones(SAMPLE_ZONES, rainfall)
        scores = [r["risk_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_higher_vulnerability_zone_has_higher_risk(self):
        """Zone B (drainage=75, low_lying=80) should score higher than Zone A (50, 40)
        at the same rainfall."""
        rainfall = {
            "test_zone_a": {"rainfall_mm": 60, "source": "simulated"},
            "test_zone_b": {"rainfall_mm": 60, "source": "simulated"},
        }
        results = evaluate_zones(SAMPLE_ZONES, rainfall)
        zone_a = next(r for r in results if r["zone_id"] == "test_zone_a")
        zone_b = next(r for r in results if r["zone_id"] == "test_zone_b")
        assert zone_b["risk_score"] > zone_a["risk_score"]

    def test_rainfall_source_preserved(self):
        rainfall = {
            "test_zone_a": {"rainfall_mm": 10, "source": "live_open_meteo"},
            "test_zone_b": {"rainfall_mm": 10, "source": "simulated"},
        }
        results = evaluate_zones(SAMPLE_ZONES, rainfall)
        zone_a = next(r for r in results if r["zone_id"] == "test_zone_a")
        zone_b = next(r for r in results if r["zone_id"] == "test_zone_b")
        assert zone_a["rainfall_source"] == "live_open_meteo"
        assert zone_b["rainfall_source"] == "simulated"

    def test_missing_rainfall_defaults_to_zero(self):
        """Zone with no rainfall data should get 0 mm and still evaluate."""
        rainfall = {}  # No data for any zone
        results = evaluate_zones(SAMPLE_ZONES, rainfall)
        assert len(results) == 2
        for r in results:
            assert r["rainfall_mm"] == 0.0

    def test_prep_checklist_present(self):
        rainfall = {
            "test_zone_a": {"rainfall_mm": 100, "source": "simulated"},
            "test_zone_b": {"rainfall_mm": 100, "source": "simulated"},
        }
        results = evaluate_zones(SAMPLE_ZONES, rainfall)
        for r in results:
            assert "prep_checklist" in r
            assert len(r["prep_checklist"]) > 0
            # Each checklist item should have action and reason
            for item in r["prep_checklist"]:
                assert "action" in item
                assert "reason" in item

    def test_result_contains_all_expected_fields(self):
        rainfall = {"test_zone_a": {"rainfall_mm": 50, "source": "simulated"}}
        results = evaluate_zones([SAMPLE_ZONES[0]], rainfall)
        result = results[0]
        expected_fields = [
            "zone_id", "zone_name", "latitude", "longitude",
            "rainfall_mm", "rainfall_source", "risk_score", "risk_level",
            "reasons", "score_breakdown", "prep_checklist",
        ]
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Risk Summary
# ---------------------------------------------------------------------------

class TestRiskSummary:
    def test_summary_counts(self):
        evaluated = [
            {"risk_level": "Low"},
            {"risk_level": "Low"},
            {"risk_level": "Moderate"},
            {"risk_level": "High"},
            {"risk_level": "Critical"},
        ]
        summary = get_risk_summary(evaluated)
        assert summary == {"Low": 2, "Moderate": 1, "High": 1, "Critical": 1}

    def test_empty_zones(self):
        summary = get_risk_summary([])
        assert summary == {"Low": 0, "Moderate": 0, "High": 0, "Critical": 0}

    def test_all_critical(self):
        evaluated = [{"risk_level": "Critical"}] * 5
        summary = get_risk_summary(evaluated)
        assert summary["Critical"] == 5
        assert summary["Low"] == 0
