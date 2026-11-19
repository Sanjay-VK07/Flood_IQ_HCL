"""
FloodIQ — Risk Engine

Calculates explainable flood risk scores for urban zones using the formula:

    R = 0.40 × P + 0.30 × D + 0.30 × L

Where:
    P = Normalized rainfall score (0–100)
    D = Drainage vulnerability score (0–100, from zone data)
    L = Low-lying vulnerability score (0–100, from zone data)

Risk levels:
    0–29  : Low
    30–49 : Moderate
    50–74 : High
    75–100: Critical

PROTOTYPE DISCLAIMER: This is an explainable heuristic for demonstration purposes.
It is NOT a validated hydrological prediction model, flood probability model, or
custom machine-learning model.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from config import (
    RISK_WEIGHT_RAINFALL,
    RISK_WEIGHT_DRAINAGE,
    RISK_WEIGHT_LOWLYING,
    RAINFALL_NORM_CEILING,
    RISK_THRESHOLDS,
    PREP_PLAYBOOKS_PATH,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Preparedness playbooks (loaded once)
# ---------------------------------------------------------------------------
_playbooks: Optional[Dict[str, Any]] = None


def _load_playbooks() -> Dict[str, Any]:
    """Load preparedness playbooks from JSON (cached after first load)."""
    global _playbooks
    if _playbooks is None:
        try:
            with open(PREP_PLAYBOOKS_PATH, "r", encoding="utf-8") as f:
                _playbooks = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Could not load prep playbooks: %s", e)
            _playbooks = {}
    return _playbooks


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_rainfall(rainfall_mm: float, ceiling: float = RAINFALL_NORM_CEILING) -> float:
    """
    Normalize rainfall to a 0–100 score.

    0 mm  → 0
    ceiling mm (default 150) → 100
    Values above ceiling are capped at 100.
    Negative values are treated as 0.
    """
    if rainfall_mm <= 0:
        return 0.0
    if ceiling <= 0:
        return 100.0
    score = (rainfall_mm / ceiling) * 100.0
    return min(round(score, 2), 100.0)


# ---------------------------------------------------------------------------
# Risk level classification
# ---------------------------------------------------------------------------

def classify_risk(score: float) -> str:
    """
    Map a numeric risk score (0–100) to a risk level string.

    Uses continuous thresholds:
      0–29.99   → Low
      30–49.99  → Moderate
      50–74.99  → High
      75–100    → Critical
    """
    score = max(0.0, min(100.0, score))
    if score < 30:
        return "Low"
    elif score < 50:
        return "Moderate"
    elif score < 75:
        return "High"
    else:
        return "Critical"


# ---------------------------------------------------------------------------
# Risk score calculation
# ---------------------------------------------------------------------------

def calculate_risk_score(
    rainfall_score: float,
    drainage_score: float,
    low_lying_score: float,
) -> Dict[str, Any]:
    """
    Calculate the composite risk score with full breakdown.

    Args:
        rainfall_score: Normalized rainfall (0–100)
        drainage_score: Drainage vulnerability (0–100)
        low_lying_score: Low-lying vulnerability (0–100)

    Returns:
        {
            "risk_score": float (0–100),
            "risk_level": str,
            "score_breakdown": {
                "rainfall": {"raw": float, "weight": float, "contribution": float},
                "drainage": {"raw": float, "weight": float, "contribution": float},
                "low_lying": {"raw": float, "weight": float, "contribution": float},
            },
            "reasons": [str, ...],
        }
    """
    # Clamp inputs
    r = max(0.0, min(100.0, rainfall_score))
    d = max(0.0, min(100.0, drainage_score))
    l = max(0.0, min(100.0, low_lying_score))

    # Weighted contributions
    r_contrib = RISK_WEIGHT_RAINFALL * r
    d_contrib = RISK_WEIGHT_DRAINAGE * d
    l_contrib = RISK_WEIGHT_LOWLYING * l

    risk_score = round(r_contrib + d_contrib + l_contrib, 2)
    risk_score = max(0.0, min(100.0, risk_score))
    risk_level = classify_risk(risk_score)

    # Build human-readable reasons
    reasons = _build_reasons(r, d, l, risk_score, risk_level)

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "score_breakdown": {
            "rainfall": {
                "raw": round(r, 2),
                "weight": RISK_WEIGHT_RAINFALL,
                "contribution": round(r_contrib, 2),
            },
            "drainage": {
                "raw": round(d, 2),
                "weight": RISK_WEIGHT_DRAINAGE,
                "contribution": round(d_contrib, 2),
            },
            "low_lying": {
                "raw": round(l, 2),
                "weight": RISK_WEIGHT_LOWLYING,
                "contribution": round(l_contrib, 2),
            },
        },
        "reasons": reasons,
    }


def _build_reasons(
    rainfall: float,
    drainage: float,
    low_lying: float,
    score: float,
    level: str,
) -> List[str]:
    """Generate human-readable explanations for the risk score."""
    reasons = []

    # Rainfall assessment
    if rainfall >= 75:
        reasons.append(f"Very heavy rainfall (score {rainfall:.0f}/100) is the dominant risk factor")
    elif rainfall >= 50:
        reasons.append(f"Heavy rainfall (score {rainfall:.0f}/100) significantly elevates flood risk")
    elif rainfall >= 30:
        reasons.append(f"Moderate rainfall (score {rainfall:.0f}/100) contributes to elevated risk")
    else:
        reasons.append(f"Rainfall is within normal range (score {rainfall:.0f}/100)")

    # Drainage assessment
    if drainage >= 60:
        reasons.append(f"Poor drainage infrastructure (score {drainage:.0f}/100) limits water clearance")
    elif drainage >= 40:
        reasons.append(f"Moderate drainage constraints (score {drainage:.0f}/100) may slow water clearance")

    # Low-lying assessment
    if low_lying >= 60:
        reasons.append(f"Low-lying terrain (score {low_lying:.0f}/100) increases water accumulation risk")
    elif low_lying >= 40:
        reasons.append(f"Moderately low terrain (score {low_lying:.0f}/100) has some accumulation risk")

    # Overall summary
    if level == "Critical":
        reasons.append("⚠️ Combined factors indicate critical flood risk — immediate attention recommended")
    elif level == "High":
        reasons.append("Combined factors indicate high flood risk — active monitoring recommended")

    return reasons


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate_zones(
    zones: List[Dict[str, Any]],
    rainfall_by_zone: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Evaluate risk for all zones given their rainfall data.

    Args:
        zones: List of zone dicts with zone_id, drainage_score, low_lying_score, etc.
        rainfall_by_zone: Dict from weather.get_rainfall_for_zones() keyed by zone_id.

    Returns:
        List of dicts, one per zone:
        [
            {
                "zone_id": str,
                "zone_name": str,
                "latitude": float,
                "longitude": float,
                "rainfall_mm": float,
                "rainfall_source": str,
                "risk_score": float,
                "risk_level": str,
                "reasons": [str],
                "score_breakdown": {...},
                "prep_checklist": [{"action": str, "reason": str}, ...],
            }
        ]
    """
    results = []
    playbooks = _load_playbooks()

    for zone in zones:
        zone_id = zone["zone_id"]

        # Get rainfall for this zone
        weather = rainfall_by_zone.get(zone_id, {})
        rainfall_mm = weather.get("rainfall_mm", 0.0)
        rainfall_source = weather.get("source", "unknown")

        # Normalize rainfall to 0–100
        rainfall_score = normalize_rainfall(rainfall_mm)

        # Calculate risk
        risk = calculate_risk_score(
            rainfall_score=rainfall_score,
            drainage_score=zone.get("drainage_score", 0),
            low_lying_score=zone.get("low_lying_score", 0),
        )

        # Get preparedness checklist for this risk level
        prep_data = playbooks.get(risk["risk_level"], {})
        prep_checklist = prep_data.get("actions", [])

        results.append({
            "zone_id": zone_id,
            "zone_name": zone.get("zone_name", zone_id),
            "latitude": zone.get("latitude", 0),
            "longitude": zone.get("longitude", 0),
            "drainage_score": zone.get("drainage_score", 0),
            "low_lying_score": zone.get("low_lying_score", 0),
            "rainfall_mm": rainfall_mm,
            "rainfall_source": rainfall_source,
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "reasons": risk["reasons"],
            "score_breakdown": risk["score_breakdown"],
            "prep_checklist": prep_checklist,
        })

    # Sort by risk score descending
    results.sort(key=lambda x: x["risk_score"], reverse=True)

    return results


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def get_risk_summary(evaluated_zones: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Summarize zone counts by risk level.

    Returns: {"Low": 2, "Moderate": 1, "High": 1, "Critical": 1}
    """
    summary = {"Low": 0, "Moderate": 0, "High": 0, "Critical": 0}
    for zone in evaluated_zones:
        level = zone.get("risk_level", "Low")
        if level in summary:
            summary[level] += 1
    return summary
