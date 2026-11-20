"""
FloodIQ — Shared UI Components & Visual Helpers

Provides consistent headers, KPI strips, status badges, and severity color
mappings across all seven application pages.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
from typing import Any, Iterable, Optional

import streamlit as st

_ICON_CACHE: dict[str, str] = {}


def get_figma_icon_uri(filename: str) -> str:
    """Return a base64 data URI for an SVG in assets/figma_icons/."""
    if filename in _ICON_CACHE:
        return _ICON_CACHE[filename]
    path = os.path.join(os.path.dirname(__file__), "assets", "figma_icons", filename)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
            uri = f"data:image/svg+xml;base64,{b64}"
            _ICON_CACHE[filename] = uri
            return uri
    except Exception:
        return ""


def compute_audit_hash(incident_id: str, events: list[dict[str, Any]]) -> str:
    """Calculate an immutable SHA-256 fingerprint over an incident's event ledger."""
    canonical_payload = {
        "incident_id": incident_id,
        "events": [
            {
                "time": e.get("time", ""),
                "badge": e.get("badge", ""),
                "title": e.get("title", ""),
                "desc": e.get("desc", ""),
            }
            for e in events
        ],
    }
    raw = json.dumps(canonical_payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_audit_packet_jsonld(
    incident: dict[str, Any],
    events: list[dict[str, Any]],
    sha256_hash: str,
) -> str:
    """Build a W3C / schema.org EmergencyService compliant JSON-LD audit packet."""
    packet = {
        "@context": "https://schema.org",
        "@type": "EmergencyService",
        "identifier": f"urn:floodiq:audit:{incident.get('incident_id', 'UNKNOWN').lstrip('#')}",
        "name": "FloodIQ Emergency Incident Audit Ledger",
        "jurisdiction": "GHMC Hyderabad Flood Disaster Coordination Pilot",
        "streamIntegrity": "SECURE_APPEND_ONLY",
        "sha256Hash": sha256_hash,
        "incident": {
            "id": incident.get("incident_id"),
            "location": incident.get("location_text") or incident.get("location_title"),
            "zone": incident.get("zone_label") or incident.get("zone_id"),
            "category": incident.get("ai_category") or incident.get("reported_category"),
            "severity": incident.get("severity", "MODERATE"),
            "priorityScore": incident.get("priority_score", 0),
            "assignedUnit": incident.get("assigned_unit", "None"),
            "reportedTime": incident.get("reported_time", "N/A"),
            "inundationDepthM": incident.get("inundation_m", 1.48),
            "flowVelocityMps": incident.get("flow_velocity", 2.8),
        },
        "chainOfCustody": [
            {
                "@type": "Action",
                "timestamp": e.get("time"),
                "lifecycleStage": e.get("badge"),
                "actionName": e.get("title"),
                "description": e.get("desc"),
                "provenance": e.get("meta", ""),
            }
            for e in events
        ],
        "disclaimer": "Prototype demonstration workflow. All logs reflect mock operational data.",
    }
    return json.dumps(packet, indent=2)


def get_canonical_audit_records() -> list[dict[str, Any]]:
    """Return the Figma Node 1:3 canonical incident archive records."""
    return [
        {
            "incident_id": "#INC-2024-0941",
            "severity": "CRITICAL",
            "severity_class": "critical",
            "zone_id": "musi_riverfront",
            "zone_label": "Zone 1 / Musi Basin",
            "priority_score": 98,
            "location_title": "Chadarghat Causeway",
            "location_text": "Chadarghat Causeway Bridge Deck",
            "gps": "17.3789° N, 78.4901° E",
            "marker": "Musi River Mile Marker 14.8",
            "category_summary": "Water Rescue (3 Trapped on Submerged Tin Sump)",
            "status": "UNDER REVIEW / ASSIGNED",
            "active_time": "T-minus 00:19:58 Active",
            "reported_time": "14:18 IST",
            "priority_tier": "Priority 1",
            "sensor": "MUSI-G04 (+2.1m)",
            "assigned_unit": "SDRF Boat Alpha-2",
            "inundation_m": 1.48,
            "flow_velocity": "2.8 m/sec (Turbulent)",
            "icon_type": "icon_rescue.svg",
            "is_canonical": True,
            "milestones": [
                {
                    "time": "14:18:02 IST",
                    "time_diff": "",
                    "badge": "TELEMETRY INGEST",
                    "badge_style": "background:#212b36; color:#859491;",
                    "node_class": "node-ingest",
                    "icon": "icon_intake.svg",
                    "title": "Citizen Intake Form Submitted",
                    "desc": "Citizen Rajesh Kumar submitted distress call report via FloodIQ Web Intake. 3 individuals reported trapped on corrugated tin roof structure near the eastern approach of Chadarghat bridge. Inflow rising rapidly.",
                    "meta_icon": "icon_pin.svg",
                    "meta": "Intake Source: Mobile Web PWA (Geolocated ±8m accuracy)",
                },
                {
                    "time": "14:18:14 IST",
                    "time_diff": "(+12s)",
                    "badge": "AUTOMATED LLM",
                    "badge_style": "background:rgba(160,201,255,0.2); color:#a0c9ff;",
                    "node_class": "node-llm",
                    "icon": "icon_ai.svg",
                    "title": "Automated AI Triage Assessment Complete",
                    "desc": "DisasterLLM classified scenario as Swiftwater Life-Safety Rescue. Extracted priority parameters: identified 2 elderly residents & 1 cardiac patient. Priority score calculated as 98/100 based on hydrodynamic Musi gauge surge.",
                    "meta_icon": "icon_sparkle.svg",
                    "meta": "Model: DisasterLLM-Hyd-v2.1 • Inference latency: 1.14s • Confidence: 99.4%",
                },
                {
                    "time": "14:21:40 IST",
                    "time_diff": "(+3m 26s)",
                    "badge": "COMMAND OVERSIGHT",
                    "badge_style": "background:rgba(79,227,211,0.2); color:#4fe3d3;",
                    "node_class": "node-command",
                    "icon": "icon_shield.svg",
                    "title": "Duty Commander Review Initiated",
                    "desc": "Cmdr. R. Verma opened incident card in Command Center tactical viewport. Confirmed life-safety priority, validated drone ortho-mosaic feed, and escalated incident priority level to Category 1 Emergency.",
                    "meta_icon": "",
                    "meta": "Station: GHMC Control Room Desk #04 (Duty Officer ID: RV-8910)",
                },
                {
                    "time": "14:24:05 IST",
                    "time_diff": "(+2m 25s)",
                    "badge": "OPTIMIZER ENGINE",
                    "badge_style": "background:#212b36; color:#bbcac6;",
                    "node_class": "node-command",
                    "icon": "icon_engine.svg",
                    "title": "Response Team Matched & Recommended",
                    "desc": "Dispatch engine recommended SDRF Boat Squad Alpha-2 based on swiftwater qualification rating, on-board paramedic gear, motorized zodiac capability, and close 450m proximity at Osmania Staging Point.",
                    "meta_icon": "",
                    "meta": "Match Rating: 98.6% • Proximity: 450m • Paramedic Certified",
                },
                {
                    "time": "14:27:15 IST",
                    "time_diff": "(+3m 10s)",
                    "badge": "EXECUTED DISPATCH",
                    "badge_style": "background:#4fe3d3; color:#003732; font-weight:700;",
                    "node_class": "node-dispatch",
                    "icon": "icon_check.svg",
                    "title": "Manual Dispatch Authorization Executed",
                    "desc": "Cmdr. R. Verma signed manual authorization order #DO-882 via biometric auth token. SDRF Unit Alpha-2 acknowledged receipt via tactical radio dispatch channel 4 (156.800 MHz).",
                    "meta_icon": "icon_radio.svg",
                    "meta": "Comms Status: 2-Way Handshake Verified • Team Leader Sub-Insp. Naidu in Command",
                },
                {
                    "time": "14:38:00 IST",
                    "time_diff": "(CURRENT TIMESTEP)",
                    "badge": "IN TRANSIT",
                    "badge_style": "background:rgba(255,148,152,0.4); color:#ffbdbe; font-weight:700;",
                    "node_class": "node-transit",
                    "icon": "icon_transit.svg",
                    "title": "Unit En Route to Causeway Staging Zone",
                    "desc": "SDRF Alpha-2 moving along elevated approach route toward eastern causeway ramp. Estimated water insertion in 3 minutes. Heavy flotsam warning issued to coxswain.",
                    "meta_icon": "",
                    "meta": "",
                    "progress_eta": "00:03:12",
                    "progress_pct": 72,
                },
            ],
        },
        {
            "incident_id": "#INC-2024-0940",
            "severity": "HIGH",
            "severity_class": "high",
            "zone_id": "shaikpet",
            "zone_label": "Zone 2 / Shaikpet Corridor",
            "priority_score": 84,
            "location_title": "Tolichowki Colony Road",
            "location_text": "Tolichowki Flyover Underpass & Colony Rd",
            "gps": "17.4042° N, 78.4112° E",
            "marker": "Drainage Outfall Marker 08.2",
            "category_summary": "Stalled Emergency 108 Ambulance (Critical Cardiac Patient)",
            "status": "RESOLVED (13:50 IST)",
            "active_time": "Duration: 22m 14s",
            "reported_time": "13:28 IST",
            "priority_tier": "Priority 2",
            "sensor": "TOL-S02 (0.62m)",
            "assigned_unit": "GHMC Heavy Tow-03",
            "inundation_m": 0.62,
            "flow_velocity": "1.2 m/sec",
            "icon_type": "icon_ambulance.svg",
            "is_canonical": True,
            "milestones": [
                {
                    "time": "13:28:10 IST",
                    "time_diff": "",
                    "badge": "TELEMETRY INGEST",
                    "badge_style": "background:#212b36; color:#859491;",
                    "node_class": "node-ingest",
                    "icon": "icon_intake.svg",
                    "title": "108 Emergency Telemetry Trigger",
                    "desc": "Ambulance #TS-09-EA-1088 engine flooded at inundated underpass. Paramedic reported cardiac patient in transit to Care Hospital.",
                    "meta_icon": "icon_pin.svg",
                    "meta": "Source: 108 CAD Integrated Feed",
                },
                {
                    "time": "13:28:30 IST",
                    "time_diff": "(+20s)",
                    "badge": "AUTOMATED LLM",
                    "badge_style": "background:rgba(160,201,255,0.2); color:#a0c9ff;",
                    "node_class": "node-llm",
                    "icon": "icon_ai.svg",
                    "title": "Medical Priority Escalation",
                    "desc": "System prioritized incident with score 84/100 due to active patient health crisis and rising underpass water level.",
                    "meta_icon": "icon_sparkle.svg",
                    "meta": "Category: Medical Emergency / Extraction",
                },
                {
                    "time": "13:30:15 IST",
                    "time_diff": "(+1m 45s)",
                    "badge": "EXECUTED DISPATCH",
                    "badge_style": "background:#4fe3d3; color:#003732; font-weight:700;",
                    "node_class": "node-dispatch",
                    "icon": "icon_check.svg",
                    "title": "Heavy Tow & Secondary Ambulance Dispatched",
                    "desc": "GHMC Heavy Recovery Vehicle-03 and Mobile ICU #4 deployed from Banjara Staging Post.",
                    "meta_icon": "icon_radio.svg",
                    "meta": "Transit Time: 8 minutes",
                },
                {
                    "time": "13:50:24 IST",
                    "time_diff": "(+20m 09s)",
                    "badge": "RESOLVED",
                    "badge_style": "background:#4fe3d3; color:#003732; font-weight:700;",
                    "node_class": "node-dispatch",
                    "icon": "icon_check.svg",
                    "title": "Patient Transferred & Roadway Cleared",
                    "desc": "Intervention: Tow Clearance & Patient Transferred to Mobile ICU. Closed by Duty Supv. K. Rao.",
                    "meta_icon": "",
                    "meta": "Total Duration: 22m 14s • Mission Success",
                },
            ],
        },
        {
            "incident_id": "#INC-2024-0939",
            "severity": "MODERATE",
            "severity_class": "moderate",
            "zone_id": "begumpet",
            "zone_label": "Zone 3 / Rasoolpura Stream",
            "priority_score": 62,
            "location_title": "Begumpet Rasoolpura",
            "location_text": "NH44 Junction & Rasoolpura Culvert Inflow",
            "gps": "17.4440° N, 78.4720° E",
            "marker": "Begumpet Nala Station 03",
            "category_summary": "Culvert Backflow Overflow onto NH44 Junction",
            "status": "RESOLVED (13:15 IST)",
            "active_time": "Duration: 41m 02s",
            "reported_time": "12:34 IST",
            "priority_tier": "Priority 3",
            "sensor": "NALA-B01 (0.45m)",
            "assigned_unit": "GHMC Stormwater Team D",
            "inundation_m": 0.45,
            "flow_velocity": "0.9 m/sec",
            "icon_type": "icon_water_pump.svg",
            "is_canonical": True,
            "milestones": [
                {
                    "time": "12:34:00 IST",
                    "time_diff": "",
                    "badge": "TELEMETRY INGEST",
                    "badge_style": "background:#212b36; color:#859491;",
                    "node_class": "node-ingest",
                    "icon": "icon_intake.svg",
                    "title": "Nala Gauge Telemetry Surge Alert",
                    "desc": "Water level at Begumpet Nala reached 85% cross-sectional capacity. Surface run-off observed on junction lanes.",
                    "meta_icon": "icon_pin.svg",
                    "meta": "Source: Automatic Ultrasonic Level Sensor",
                },
                {
                    "time": "12:37:10 IST",
                    "time_diff": "(+3m 10s)",
                    "badge": "OPTIMIZER ENGINE",
                    "badge_style": "background:#212b36; color:#bbcac6;",
                    "node_class": "node-command",
                    "icon": "icon_engine.svg",
                    "title": "Submersible Dewatering Task Assigned",
                    "desc": "Task generated: Raise Sluice Gate 4 and activate twin 150HP dewatering pumps.",
                    "meta_icon": "",
                    "meta": "GHMC Stormwater Team D assigned",
                },
                {
                    "time": "13:15:02 IST",
                    "time_diff": "(+37m 52s)",
                    "badge": "RESOLVED",
                    "badge_style": "background:#4fe3d3; color:#003732; font-weight:700;",
                    "node_class": "node-dispatch",
                    "icon": "icon_check.svg",
                    "title": "Culvert Backflow Mitigated",
                    "desc": "Intervention: Sluice Gate 4 Raised + 2x 150HP Submersible Pumps Active. Traffic resumed smoothly.",
                    "meta_icon": "",
                    "meta": "Total Duration: 41m 02s • Verified by Traffic Police",
                },
            ],
        },
        {
            "incident_id": "#INC-2024-0938",
            "severity": "MODERATE",
            "severity_class": "moderate",
            "zone_id": "ameerpet",
            "zone_label": "Zone 2 / Metro Corridor",
            "priority_score": 48,
            "location_title": "Ameerpet Metro Junction",
            "location_text": "Main road near Ameerpet Metro Station",
            "gps": "17.4380° N, 78.4500° E",
            "marker": "Metro Corridor Pillar 1042",
            "category_summary": "Road Blockage (Ankle-Deep Surface Inundation)",
            "status": "TRIAGED",
            "active_time": "T-minus 01:10:00 Active",
            "reported_time": "12:15 IST",
            "priority_tier": "Priority 3",
            "sensor": "MET-G01 (+0.2m)",
            "assigned_unit": "Traffic Ward Team 2",
            "inundation_m": 0.20,
            "flow_velocity": "0.3 m/sec",
            "icon_type": "icon_rescue.svg",
            "is_canonical": True,
            "milestones": [
                {
                    "time": "12:15:00 IST",
                    "time_diff": "",
                    "badge": "TELEMETRY INGEST",
                    "badge_style": "background:#212b36; color:#859491;",
                    "node_class": "node-ingest",
                    "icon": "icon_intake.svg",
                    "title": "Citizen Traffic Disruption Report",
                    "desc": "Road near Ameerpet metro station is partially waterlogged after heavy rain. Traffic is slow-moving but no vehicles stranded.",
                    "meta_icon": "icon_pin.svg",
                    "meta": "Intake Source: Public Mobile App",
                },
                {
                    "time": "12:15:15 IST",
                    "time_diff": "(+15s)",
                    "badge": "AUTOMATED LLM",
                    "badge_style": "background:rgba(160,201,255,0.2); color:#a0c9ff;",
                    "node_class": "node-llm",
                    "icon": "icon_ai.svg",
                    "title": "Priority Scoring Completed",
                    "desc": "Calculated Priority 48/100. Non-life-safety classification. Diverted advisory sent to Hyderabad Traffic Police.",
                    "meta_icon": "icon_sparkle.svg",
                    "meta": "Confidence: 98.2%",
                },
            ],
        },
    ]



def band_from_score(score: float) -> str:
    """Map numeric risk or priority score (0-100) to band label."""
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 30:
        return "Moderate"
    return "Low"


def badge_html(label: str, tone: str = "neutral") -> str:
    """Return an inline HTML pill badge with restrained command-center styling."""
    safe_label = html.escape(str(label))
    safe_tone = html.escape(tone.lower())
    return f'<span class="fiq-badge fiq-badge-{safe_tone}">{safe_label}</span>'


def render_page_header(
    title: str,
    subtitle: str,
    mode_label: str,
    mode_tone: str = "sim",
    right_label: Optional[str] = None,
    right_value: Optional[str] = None,
    right_note: Optional[str] = None,
) -> None:
    """Render a compact, high-contrast command-center page header."""
    right_block = ""
    if right_label and right_value is not None:
        note_html = f"<small>{html.escape(right_note)}</small>" if right_note else ""
        right_block = (
            f'<div class="fiq-header-stat">'
            f'<span>{html.escape(right_label)}</span>'
            f'<strong>{html.escape(right_value)}</strong>'
            f'{note_html}'
            f"</div>"
        )

    st.markdown(
        f"""
        <header class="fiq-header">
          <div class="fiq-header-top">
            <span class="fiq-kicker">FLOODIQ &middot; HYDERABAD PILOT</span>
            <span class="fiq-mode-pill fiq-mode-{html.escape(mode_tone)}"><i></i>{html.escape(mode_label)}</span>
          </div>
          <div class="fiq-header-main">
            <div class="fiq-header-copy">
              <h1>{html.escape(title)}</h1>
              <p>{html.escape(subtitle)}</p>
            </div>
            {right_block}
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, caption: Optional[str] = None) -> None:
    """Render a clean section heading with optional muted caption."""
    cap_html = f'<p class="fiq-section-cap">{html.escape(caption)}</p>' if caption else ""
    st.markdown(
        f'<div class="fiq-section-head"><h3>{html.escape(title)}</h3>{cap_html}</div>',
        unsafe_allow_html=True,
    )


def render_map_legend(items: Iterable[tuple[str, str]]) -> None:
    """Render a compact horizontal legend bar below or above a map."""
    pills = "".join(
        f'<span class="fiq-legend-item"><i style="background:{html.escape(color)};"></i>{html.escape(label)}</span>'
        for label, color in items
    )
    st.markdown(f'<div class="fiq-legend">{pills}</div>', unsafe_allow_html=True)
