"""
FloodIQ — AI Incident Triage Engine (Groq + Deterministic Fallback)

Provides incident triage using either:
1. Groq API (official `groq` Python SDK with Structured Outputs / JSON Schema)
2. Deterministic rule-based fallback (`rule_based`, offline / quota-safe)

Explicit provider labels:
- "groq"       : Validated structured output from Groq
- "rule_based" : Deterministic local keyword/rule engine
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

import config
from config import INCIDENT_CATEGORIES, URGENCY_LEVELS, VULNERABLE_GROUPS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Schema for Validated Triage Output
# ---------------------------------------------------------------------------

class TriageAssessment(BaseModel):
    ai_category: Literal[
        "Water Rescue",
        "Medical Emergency",
        "Road Blockage",
        "Infrastructure Damage",
        "Flooded Building",
        "Other",
    ]
    ai_urgency: Literal["Critical", "High", "Medium", "Low"]
    people_affected: int = Field(ge=0, le=10000)
    vulnerable_flag: bool
    vulnerable_group: Literal[
        "Elderly people",
        "Children",
        "People with disabilities",
        "Pregnant women",
        "None reported",
    ]
    stranded: bool
    unable_to_evacuate: bool
    immediate_hazard: bool
    medical_emergency: bool = False
    rescue_required: bool = False
    recommended_response_category: str = Field(min_length=2, max_length=80)
    ai_rationale: str = Field(min_length=5, max_length=600)


_TRIAGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ai_category": {
            "type": "string",
            "enum": INCIDENT_CATEGORIES,
        },
        "ai_urgency": {
            "type": "string",
            "enum": URGENCY_LEVELS,
        },
        "people_affected": {"type": "integer", "minimum": 0, "maximum": 10000},
        "vulnerable_flag": {"type": "boolean"},
        "vulnerable_group": {
            "type": "string",
            "enum": VULNERABLE_GROUPS,
        },
        "stranded": {"type": "boolean"},
        "unable_to_evacuate": {"type": "boolean"},
        "immediate_hazard": {"type": "boolean"},
        "medical_emergency": {"type": "boolean"},
        "rescue_required": {"type": "boolean"},
        "recommended_response_category": {"type": "string"},
        "ai_rationale": {"type": "string"},
    },
    "required": [
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
    ],
    "additionalProperties": False,
}

_GROQ_SYSTEM_PROMPT = """You are FloodIQ's Emergency Incident Triage assistant for Hyderabad, India.
Return ONLY a JSON object matching the required schema.

STRICT CONSTRAINTS:
1. Never invent the number of affected people. Use the reported count or an explicit count stated in the description; otherwise 0.
2. Never invent medical conditions or vulnerabilities not supported by the report.
3. Do not treat uncertain information as verified.
4. Never claim a rescue has been initiated, never approve dispatch, and never assign emergency teams.
5. Keep ai_rationale concise (1-2 sentences) citing only reported facts."""


# ---------------------------------------------------------------------------
# Caching, Rate-Limit Cooldown & Provider Telemetry State
# ---------------------------------------------------------------------------

_TRIAGE_CACHE: dict[str, Dict[str, Any]] = {}
_CACHE_HITS: int = 0
_COOLDOWN_UNTIL: float = 0.0
_LATEST_PROVIDER_STATUS: str = "not_configured"
_LAST_SUCCESS_AT: Optional[str] = None
_LAST_ERROR_SUMMARY: Optional[str] = None


def reset_ai_state() -> None:
    """Reset in-memory triage cache and rate-limit state (for tests)."""
    global _CACHE_HITS, _COOLDOWN_UNTIL, _LATEST_PROVIDER_STATUS, _LAST_SUCCESS_AT, _LAST_ERROR_SUMMARY
    _TRIAGE_CACHE.clear()
    _CACHE_HITS = 0
    _COOLDOWN_UNTIL = 0.0
    _LATEST_PROVIDER_STATUS = "not_configured"
    _LAST_SUCCESS_AT = None
    _LAST_ERROR_SUMMARY = None


def _is_groq_configured() -> bool:
    key = (config.GROQ_API_KEY or "").strip()
    return bool(key and key != "your_groq_api_key_here")


def _compute_content_hash(
    description: str,
    zone_name: str,
    location_text: str,
    people_affected: int,
) -> str:
    normalized = "|".join([
        re.sub(r"\s+", " ", description.strip().lower()),
        re.sub(r"\s+", " ", zone_name.strip().lower()),
        re.sub(r"\s+", " ", location_text.strip().lower()),
        str(max(0, int(people_affected))),
    ])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_retry_after_seconds(headers: Any, default_seconds: int) -> float:
    if not headers:
        return float(default_seconds)
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is not None:
        try:
            return max(1.0, min(float(raw), 300.0))
        except (TypeError, ValueError):
            pass
    reset_req = headers.get("x-ratelimit-reset-requests") or headers.get("x-ratelimit-reset-tokens")
    if isinstance(reset_req, str):
        m = re.search(r"(\d+(?:\.\d+)?)", reset_req)
        if m:
            try:
                return max(1.0, min(float(m.group(1)), 300.0))
            except ValueError:
                pass
    return float(default_seconds)


def get_ai_status() -> Dict[str, Any]:
    """Return safe operational telemetry for System Information without exposing secrets."""
    configured = _is_groq_configured()
    now = time.time()
    cooldown_remaining = max(0, int(round(_COOLDOWN_UNTIL - now)))
    rate_limited = cooldown_remaining > 0 or _LATEST_PROVIDER_STATUS in ("rate_limited", "quota_exhausted")

    if config.OFFLINE_MODE:
        status_label = "offline_mode"
        active_mode = "rule_based"
    elif not configured:
        status_label = "not_configured"
        active_mode = "rule_based"
    elif cooldown_remaining > 0:
        status_label = _LATEST_PROVIDER_STATUS if _LATEST_PROVIDER_STATUS in ("rate_limited", "quota_exhausted") else "rate_limited"
        active_mode = "rule_based"
    elif _LATEST_PROVIDER_STATUS in ("provider_error", "validation_error", "invalid_api_key"):
        status_label = _LATEST_PROVIDER_STATUS
        active_mode = "rule_based"
    elif _LATEST_PROVIDER_STATUS == "ok":
        status_label = "ok"
        active_mode = "groq"
    else:
        status_label = "ready"
        active_mode = "groq"

    return {
        "provider": active_mode,
        "mode": active_mode,
        "model": config.GROQ_MODEL,
        "groq_configured": configured,
        "offline_mode": config.OFFLINE_MODE,
        "fallback_active": active_mode == "rule_based",
        "latest_provider_status": status_label,
        "rate_limited": rate_limited,
        "cooldown_remaining_seconds": cooldown_remaining,
        "last_success_at": _LAST_SUCCESS_AT,
        "last_error": _LAST_ERROR_SUMMARY,
        "cache_entries": len(_TRIAGE_CACHE),
        "cache_hits": _CACHE_HITS,
    }


# ---------------------------------------------------------------------------
# Deterministic Rule-Based Fallback
# ---------------------------------------------------------------------------

def _fallback_triage(
    description: str,
    zone_name: str,
    location_text: str = "",
    people_affected: int = 0,
) -> Dict[str, Any]:
    """
    Deterministic rule-based triage when Groq API is unavailable, unconfigured, or rate-limited.
    """
    text = f"{description} {location_text}".lower()

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

    negations = [
        "not stranded", "no one is stranded", "no residents stranded", "no one stranded",
        "not trapped", "no one is trapped", "no trapped", "not stuck", "no vehicles are stuck",
        "no one stuck",
    ]
    is_negated = any(neg in text for neg in negations)

    stranded = False
    if not is_negated:
        stranded = any(k in text for k in [
            "stranded", "trapped", "stuck", "surrounded", "roof", "first floor",
            "second floor", "terrace", "cut off", "marooned", "cannot exit", "can't exit",
        ])

    unable_to_evacuate = stranded or (not is_negated and any(k in text for k in [
        "cannot leave", "unable to leave", "unable to evacuate", "no way out",
        "doors blocked", "stairs submerged", "waist deep", "chest deep",
    ]))

    immediate_hazard = any(k in text for k in [
        "water rising", "rising water", "surging", "water levels are continuing to rise",
        "rapidly rising", "current is strong", "electric", "live wire", "short circuit",
        "wall collapsed", "collapse", "gas leak",
    ])

    count = max(0, int(people_affected))
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
        elif "family" in text:
            count = 4

    medical_emergency = any(k in text for k in [
        "medical", "doctor", "ambulance", "heart", "oxygen", "unconscious", "injury", "injured", "bleeding",
    ])

    if any(k in text for k in ["rescue", "boat", "drowning", "swept", "stranded in water", "water entered", "residential building"]):
        if stranded or "rescue" in text or "musi" in text:
            ai_category = "Water Rescue"
        else:
            ai_category = "Flooded Building"
    elif medical_emergency:
        ai_category = "Medical Emergency"
    elif any(k in text for k in ["road", "traffic", "highway", "flyover", "metro", "waterlogged road", "blockage", "jam"]):
        ai_category = "Road Blockage"
    elif any(k in text for k in ["bridge", "pole", "transformer", "wall collapse", "culvert", "drain broken"]):
        ai_category = "Infrastructure Damage"
    elif any(k in text for k in ["building", "apartment", "house", "cellar", "basement", "floor", "parking"]):
        ai_category = "Flooded Building"
    else:
        ai_category = "Other"

    if stranded and (vulnerable_flag or immediate_hazard or count >= 3):
        ai_urgency = "Critical"
    elif stranded or ai_category == "Medical Emergency" or (immediate_hazard and count > 0):
        ai_urgency = "High"
    elif ai_category in ["Road Blockage", "Flooded Building", "Infrastructure Damage"]:
        ai_urgency = "Medium"
    else:
        ai_urgency = "Low"

    rescue_required = bool(stranded or ai_category == "Water Rescue")
    rec_map = {
        "Water Rescue": "Water Rescue / Boat Unit",
        "Medical Emergency": "Medical Response / Ambulance",
        "Road Blockage": "Traffic & Road Clearance",
        "Infrastructure Damage": "Municipal Engineering / Utility",
        "Flooded Building": "Drainage & Evacuation Support",
        "Other": "General Assessment Team",
    }

    rationale_parts = []
    if stranded:
        rationale_parts.append("Report indicates individuals stranded or trapped by floodwaters.")
    if vulnerable_flag:
        rationale_parts.append(f"Vulnerable group detected: {vulnerable_group}.")
    if immediate_hazard:
        rationale_parts.append("Active or escalating immediate hazard reported (e.g. rising water).")
    if not rationale_parts:
        rationale_parts.append(f"Report classified as {ai_category} based on situational indicators.")
    rationale_parts.append(f"Assigned urgency: {ai_urgency} (Deterministic Rule-Based Fallback).")

    return {
        "ai_category": ai_category,
        "ai_urgency": ai_urgency,
        "people_affected": count,
        "vulnerable_flag": vulnerable_flag,
        "vulnerable_group": vulnerable_group,
        "stranded": stranded,
        "unable_to_evacuate": unable_to_evacuate,
        "immediate_hazard": immediate_hazard,
        "medical_emergency": medical_emergency,
        "rescue_required": rescue_required,
        "recommended_response_category": rec_map.get(ai_category, "General Assessment Team"),
        "ai_rationale": " ".join(rationale_parts),
        "triage_mode": "rule_based",
    }


# ---------------------------------------------------------------------------
# Groq Hosted AI Triage
# ---------------------------------------------------------------------------

def _groq_triage(
    description: str,
    zone_name: str,
    location_text: str = "",
    people_affected: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    Attempt triage using the official `groq` Python SDK with Structured Outputs.
    Respects active rate-limit cooldown, Retry-After headers, and bounded exponential backoff.
    Returns validated dict with triage_mode="groq", or None on failure/cooldown.
    """
    global _COOLDOWN_UNTIL, _LATEST_PROVIDER_STATUS, _LAST_SUCCESS_AT, _LAST_ERROR_SUMMARY

    if config.OFFLINE_MODE:
        _LATEST_PROVIDER_STATUS = "offline_mode"
        return None
    if not _is_groq_configured():
        _LATEST_PROVIDER_STATUS = "not_configured"
        return None

    now = time.time()
    if now < _COOLDOWN_UNTIL:
        return None

    from groq import APIConnectionError, APIStatusError, APITimeoutError, Groq, RateLimitError

    client = Groq(api_key=config.GROQ_API_KEY, timeout=15.0, max_retries=0)
    user_prompt = (
        f"Zone: {zone_name}\n"
        f"Landmark: {location_text or 'Not specified'}\n"
        f"Reported People Affected: {max(0, int(people_affected))}\n"
        f"Report: {description.strip()}"
    )

    max_attempts = max(1, int(config.GROQ_MAX_RETRIES) + 1)
    for attempt in range(max_attempts):
        try:
            completion = client.chat.completions.create(
                model=config.GROQ_MODEL,
                temperature=0.1,
                max_completion_tokens=1500,
                messages=[
                    {"role": "system", "content": _GROQ_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "floodiq_incident_triage",
                        "strict": True,
                        "schema": _TRIAGE_JSON_SCHEMA,
                    },
                },
            )
            content = completion.choices[0].message.content if completion.choices else None
            if not content:
                _LATEST_PROVIDER_STATUS = "provider_error"
                _LAST_ERROR_SUMMARY = "Empty response content from Groq."
                return None

            raw_data = json.loads(content.strip())
            validated = TriageAssessment.model_validate(raw_data)
            result = validated.model_dump()
            result["triage_mode"] = "groq"

            _LATEST_PROVIDER_STATUS = "ok"
            _LAST_ERROR_SUMMARY = None
            _LAST_SUCCESS_AT = datetime.now(timezone.utc).isoformat()
            return result

        except RateLimitError as exc:
            headers = getattr(getattr(exc, "response", None), "headers", None)
            msg = str(exc).lower()
            is_quota = "quota" in msg or "exceeded" in msg or "limit" in msg and "tokens per day" in msg
            cooldown = _parse_retry_after_seconds(headers, config.GROQ_COOLDOWN_SECONDS)

            if is_quota or attempt >= max_attempts - 1:
                _COOLDOWN_UNTIL = time.time() + cooldown
                _LATEST_PROVIDER_STATUS = "quota_exhausted" if is_quota else "rate_limited"
                _LAST_ERROR_SUMMARY = "Groq rate limit / quota reached; deterministic fallback active."
                logger.warning("Groq rate-limited (%s). Cooldown %ss.", _LATEST_PROVIDER_STATUS, cooldown)
                return None

            backoff = min(2 ** attempt, cooldown, 4.0)
            time.sleep(backoff)

        except (APITimeoutError, APIConnectionError) as exc:
            if attempt < max_attempts - 1:
                time.sleep(min(2 ** attempt, 2.0))
                continue
            _LATEST_PROVIDER_STATUS = "provider_error"
            _LAST_ERROR_SUMMARY = f"Groq network/timeout error: {type(exc).__name__}"
            logger.warning("Groq timeout/connection error: %s", exc)
            return None

        except APIStatusError as exc:
            status_code = getattr(exc, "status_code", 500)
            if status_code >= 500 and attempt < max_attempts - 1:
                time.sleep(min(2 ** attempt, 2.0))
                continue
            _LATEST_PROVIDER_STATUS = "invalid_api_key" if status_code == 401 else "provider_error"
            _LAST_ERROR_SUMMARY = f"Groq API returned HTTP {status_code}."
            logger.warning("Groq APIStatusError %s: %s", status_code, exc)
            return None

        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            _LATEST_PROVIDER_STATUS = "validation_error"
            _LAST_ERROR_SUMMARY = f"Groq output validation failed: {type(exc).__name__}"
            logger.warning("Groq output failed schema validation: %s", exc)
            return None

        except Exception as exc:
            _LATEST_PROVIDER_STATUS = "provider_error"
            _LAST_ERROR_SUMMARY = f"Unexpected Groq client error: {type(exc).__name__}"
            logger.warning("Unexpected Groq triage error: %s", exc)
            return None

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
    Main triage interface.
    1. Checks normalized incident-content hash cache to avoid duplicate Groq calls.
    2. Calls Groq Structured Outputs when configured and not in cooldown.
    3. Falls back deterministically to `rule_based` engine on any failure or quota exhaustion.
    """
    global _CACHE_HITS

    content_hash = _compute_content_hash(description, zone_name, location_text, people_affected)
    cached = _TRIAGE_CACHE.get(content_hash)
    if cached is not None:
        _CACHE_HITS += 1
        return dict(cached)

    groq_result = _groq_triage(
        description=description,
        zone_name=zone_name,
        location_text=location_text,
        people_affected=people_affected,
    )
    if groq_result:
        _TRIAGE_CACHE[content_hash] = dict(groq_result)
        return groq_result

    fallback_result = _fallback_triage(
        description=description,
        zone_name=zone_name,
        location_text=location_text,
        people_affected=people_affected,
    )
    # Cache fallback only when Groq isn't expected to recover, or avoid polluting cache during transient cooldown?
    # Wait: if Groq is unconfigured/offline, caching fallback is fine; if transient rate limit, keeping fallback out
    # of cache lets future submissions retry Groq once cooldown expires.
    if not _is_groq_configured() or config.OFFLINE_MODE:
        _TRIAGE_CACHE[content_hash] = dict(fallback_result)
    return fallback_result
