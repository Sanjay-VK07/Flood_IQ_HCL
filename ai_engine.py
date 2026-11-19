"""
FloodIQ — AI Incident Triage Engine

Provides incident triage using either:
1. Google Gemini API (structured JSON output via google-genai SDK)
2. Deterministic keyword-based fallback (offline / API failure safe)

Both modes return the EXACT same dictionary structure:
{
    "ai_category": str,           # Water Rescue, Medical Emergency, Road Blockage, Infrastructure Damage, Flooded Building, Other
    "ai_urgency": str,            # Critical, High, Medium, Low
    "people_affected": int,       # Extracted or validated count
    "vulnerable_flag": bool,      # True if vulnerable people involved
    "vulnerable_group": str,      # Elderly people, Children, People with disabilities, Pregnant women, None reported
    "stranded": bool,             # True if individuals trapped or surrounded by water
    "unable_to_evacuate": bool,   # True if self-evacuation is impossible
    "immediate_hazard": bool,     # True if active rising water, electrical hazard, structural threat
    "ai_rationale": str,          # Brief explainable justification
    "triage_mode": str,           # "ai" or "fallback"
}
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    INCIDENT_CATEGORIES,
    URGENCY_LEVELS,
    VULNERABLE_GROUPS,
    OFFLINE_MODE,
)

logger = logging.getLogger(__name__)

# System instructions to enforce schema and guardrails
_GEMINI_TRIAGE_PROMPT = """You are FloodIQ's AI Emergency Triage specialist analyzing citizen disaster reports in Hyderabad, India.
Analyze the incident report carefully and return a single valid JSON object.

RULES:
1. Never invent missing facts. Distinguish reported facts from inferred information.
2. Return ONLY valid JSON with no markdown wrapping or extra commentary.
3. Classify into exactly one ai_category from: ["Water Rescue", "Medical Emergency", "Road Blockage", "Infrastructure Damage", "Flooded Building", "Other"].
4. Assign ai_urgency from: ["Critical", "High", "Medium", "Low"].
5. Extract or confirm people_affected as an integer.
6. Identify vulnerable_group from: ["Elderly people", "Children", "People with disabilities", "Pregnant women", "None reported"].
7. Set vulnerable_flag to true if a recognized vulnerable group is present.
8. Set stranded to true if people are surrounded by floodwater, stuck on floors/roofs, or cannot move.
9. Set unable_to_evacuate to true if self-evacuation is blocked or unsafe.
10. Set immediate_hazard to true if water is actively rising, live wires are present, or structural collapse is threatened.
11. Provide a concise, professional ai_rationale (1-3 sentences) explaining the classification.
12. Never declare an incident safe or resolved.

REQUIRED JSON FORMAT:
{
    "ai_category": "Water Rescue",
    "ai_urgency": "Critical",
    "people_affected": 3,
    "vulnerable_flag": true,
    "vulnerable_group": "Elderly people",
    "stranded": true,
    "unable_to_evacuate": true,
    "immediate_hazard": true,
    "ai_rationale": "Explanation here..."
}
"""


# ---------------------------------------------------------------------------
# Deterministic Fallback Rules
# ---------------------------------------------------------------------------

def _fallback_triage(
    description: str,
    zone_name: str,
    location_text: str = "",
    people_affected: int = 0,
) -> Dict[str, Any]:
    """
    Deterministic rule-based triage when Gemini API is unavailable or disabled.
    Guarantees zero crashes and outputs the standard triage schema.
    """
    text = f"{description} {location_text}".lower()

    # 1. Detect vulnerable groups
    vulnerable_group = "None reported"
    vulnerable_flag = False

    if any(k in text for k in ["elderly", "old age", "senior", "grandfather", "grandmother", "aged"]):
        vulnerable_group = "Elderly people"
        vulnerable_flag = True
    elif any(k in text for k in ["child", "children", "baby", "infant", "toddler", "kid"]):
        vulnerable_group = "Children"
        vulnerable_flag = True
    elif any(k in text for k in ["disabled", "handicap", "wheelchair", "bedridden", "blind"]):
        vulnerable_group = "People with disabilities"
        vulnerable_flag = True
    elif any(k in text for k in ["pregnant", "expecting mother"]):
        vulnerable_group = "Pregnant women"
        vulnerable_flag = True

    # 2. Detect stranded / trapped indicators
    # Handle negation first: "no vehicles are stuck", "not trapped", "no one stranded"
    negations = [
        "not stranded", "no one is stranded", "no residents stranded", "no one stranded",
        "not trapped", "no one is trapped", "no trapped", "not stuck", "no vehicles are stuck",
        "no one stuck"
    ]
    is_negated = any(neg in text for neg in negations)

    stranded = False
    if not is_negated:
        stranded = any(k in text for k in [
            "stranded", "trapped", "stuck", "surrounded", "roof", "first floor",
            "second floor", "terrace", "cut off", "marooned", "cannot exit", "can't exit"
        ])

    unable_to_evacuate = stranded or (not is_negated and any(k in text for k in [
        "cannot leave", "unable to leave", "unable to evacuate", "no way out",
        "doors blocked", "stairs submerged", "waist deep", "chest deep"
    ]))

    # 3. Detect immediate hazards
    immediate_hazard = any(k in text for k in [
        "water rising", "rising water", "surging", "water levels are continuing to rise",
        "rapidly rising", "current is strong", "electric", "live wire", "short circuit",
        "wall collapsed", "collapse", "gas leak"
    ])

    # 4. Extract people affected if not provided
    count = people_affected
    if count <= 0:
        match = re.search(r"(\d+)\s*(people|persons|residents|citizens|members|souls)", text)
        if match:
            try:
                count = int(match.group(1))
            except ValueError:
                count = 0
        elif any(k in text for k in ["three people", "three residents"]):
            count = 3
        elif any(k in text for k in ["two people", "two residents"]):
            count = 2
        elif any(k in text for k in ["family"]):
            count = 4

    # 5. Incident Category Classification
    if any(k in text for k in ["rescue", "boat", "drowning", "swept", "stranded in water", "water entered", "residential building"]):
        if stranded or "rescue" in text or "musi" in text:
            ai_category = "Water Rescue"
        else:
            ai_category = "Flooded Building"
    elif any(k in text for k in ["medical", "doctor", "ambulance", "heart", "oxygen", "unconscious", "injury", "injured", "bleeding"]):
        ai_category = "Medical Emergency"
    elif any(k in text for k in ["road", "traffic", "highway", "flyover", "metro", "waterlogged road", "blockage", "jam"]):
        ai_category = "Road Blockage"
    elif any(k in text for k in ["bridge", "pole", "transformer", "wall collapse", "culvert", "drain broken"]):
        ai_category = "Infrastructure Damage"
    elif any(k in text for k in ["building", "apartment", "house", "cellar", "basement", "floor", "parking"]):
        ai_category = "Flooded Building"
    else:
        ai_category = "Other"

    # 6. Urgency Determination
    if stranded and (vulnerable_flag or immediate_hazard or count >= 3):
        ai_urgency = "Critical"
    elif stranded or ai_category == "Medical Emergency" or (immediate_hazard and count > 0):
        ai_urgency = "High"
    elif ai_category in ["Road Blockage", "Flooded Building", "Infrastructure Damage"]:
        ai_urgency = "Medium"
    else:
        ai_urgency = "Low"

    # 7. Explainable rationale
    rationale_parts = []
    if stranded:
        rationale_parts.append("Report indicates individuals stranded or trapped by floodwaters.")
    if vulnerable_flag:
        rationale_parts.append(f"Vulnerable group detected: {vulnerable_group}.")
    if immediate_hazard:
        rationale_parts.append("Active or escalating immediate hazard reported (e.g. rising water).")
    if not rationale_parts:
        rationale_parts.append(f"Report classified as {ai_category} based on situational indicators.")

    rationale_parts.append(f"Assigned urgency: {ai_urgency} (Deterministic Fallback Mode).")

    return {
        "ai_category": ai_category,
        "ai_urgency": ai_urgency,
        "people_affected": count,
        "vulnerable_flag": vulnerable_flag,
        "vulnerable_group": vulnerable_group,
        "stranded": stranded,
        "unable_to_evacuate": unable_to_evacuate,
        "immediate_hazard": immediate_hazard,
        "ai_rationale": " ".join(rationale_parts),
        "triage_mode": "fallback",
    }


# ---------------------------------------------------------------------------
# Gemini AI Triage
# ---------------------------------------------------------------------------

def _gemini_triage(
    description: str,
    zone_name: str,
    location_text: str = "",
    people_affected: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    Attempt triage using the Google Gemini API (google-genai SDK).
    Returns parsed dictionary or None if any failure occurs.
    """
    if not GEMINI_API_KEY or OFFLINE_MODE:
        return None

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        user_content = (
            f"Zone: {zone_name}\n"
            f"Specific Location: {location_text}\n"
            f"Affected Count Reported: {people_affected}\n"
            f"Incident Description:\n{description}"
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                {"role": "user", "parts": [{"text": _GEMINI_TRIAGE_PROMPT + "\n\n" + user_content}]}
            ],
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
            }
        )

        if not response or not response.text:
            return None

        # Clean JSON text if wrapped
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        data = json.loads(raw_text.strip())

        # Validate required schema fields
        cat = data.get("ai_category")
        if cat not in INCIDENT_CATEGORIES:
            cat = "Other"

        urg = data.get("ai_urgency")
        if urg not in URGENCY_LEVELS:
            urg = "Medium"

        vuln_group = data.get("vulnerable_group", "None reported")
        if vuln_group not in VULNERABLE_GROUPS:
            vuln_group = "None reported"

        return {
            "ai_category": cat,
            "ai_urgency": urg,
            "people_affected": int(data.get("people_affected", people_affected)),
            "vulnerable_flag": bool(data.get("vulnerable_flag", False)),
            "vulnerable_group": vuln_group,
            "stranded": bool(data.get("stranded", False)),
            "unable_to_evacuate": bool(data.get("unable_to_evacuate", False)),
            "immediate_hazard": bool(data.get("immediate_hazard", False)),
            "ai_rationale": str(data.get("ai_rationale", "AI triage completed.")),
            "triage_mode": "ai",
        }

    except Exception as e:
        logger.warning("Gemini AI triage failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public Entry Point
# ---------------------------------------------------------------------------

def triage_incident(
    description: str,
    zone_name: str,
    location_text: str = "",
    people_affected: int = 0,
) -> Dict[str, Any]:
    """
    Main triage interface. Tries Gemini AI first; falls back to deterministic rules.
    Never throws an unhandled exception.
    """
    # 1. Attempt Gemini AI
    ai_result = _gemini_triage(
        description=description,
        zone_name=zone_name,
        location_text=location_text,
        people_affected=people_affected,
    )
    if ai_result:
        return ai_result

    # 2. Fallback Deterministic Engine
    return _fallback_triage(
        description=description,
        zone_name=zone_name,
        location_text=location_text,
        people_affected=people_affected,
    )
