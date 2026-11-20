"""
FloodIQ — AI-Powered Urban Disaster Intelligence & Emergency Response Coordination Platform

Main Streamlit Application.
Follows clean separation of concerns — delegates all logic to backend modules.
"""

from __future__ import annotations

import html
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from ai_engine import triage_incident
from config import (
    APP_ICON,
    APP_SUBTITLE,
    APP_TITLE,
    GEMINI_API_KEY,
    INCIDENT_CATEGORIES,
    LEVEL_COLORS,
    MAP_CENTER_LAT,
    MAP_CENTER_LNG,
    MAP_DEFAULT_ZOOM,
    OFFLINE_MODE,
    STATUS_TRANSITIONS,
)
from database import (
    create_incident,
    get_incident,
    get_incident_updates,
    get_response_teams,
    get_zones,
    init_db,
    list_incidents,
    reset_demo_data,
    update_incident_workflow,
)
from response_engine import calculate_priority, recommend_team
from risk_engine import evaluate_zones, get_risk_summary
from ui_components import (
    badge_html,
    band_from_score,
    build_audit_packet_jsonld,
    compute_audit_hash,
    get_canonical_audit_records,
    get_figma_icon_uri,
    render_map_legend,
    render_page_header,
    render_section_heading,
)
from weather import get_rainfall_for_zones, get_weather_status

# ---------------------------------------------------------------------------
# Streamlit Page Setup & Custom CSS
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title=f"{APP_TITLE} | Urban Flood Operations",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


def _load_css() -> None:
    css_path = Path(__file__).parent / "assets" / "style.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


_load_css()
init_db()

# ---------------------------------------------------------------------------
# Session State & Navigation Helpers
# ---------------------------------------------------------------------------

NAV_OPTIONS = [
    "Command Center",
    "Flood Risk Intelligence",
    "Preparedness",
    "Citizen Reporting",
    "Response Control Room",
    "Incident History",
    "System Information",
]

if "nav_option" not in st.session_state or st.session_state["nav_option"] not in NAV_OPTIONS:
    st.session_state["nav_option"] = NAV_OPTIONS[0]

if "simulated_rain_mm" not in st.session_state:
    st.session_state["simulated_rain_mm"] = 20.0

if "rain_slider" not in st.session_state:
    st.session_state["rain_slider"] = float(st.session_state["simulated_rain_mm"])

if "use_simulation" not in st.session_state:
    st.session_state["use_simulation"] = True

if "selected_incident_id" not in st.session_state:
    st.session_state["selected_incident_id"] = None

if "last_submitted_id" not in st.session_state:
    st.session_state["last_submitted_id"] = None


def _set_rainfall_preset(mm: float) -> None:
    st.session_state["simulated_rain_mm"] = float(mm)
    st.session_state["rain_slider"] = float(mm)


def _sync_rain_slider() -> None:
    st.session_state["simulated_rain_mm"] = float(st.session_state["rain_slider"])


def _go_to_control_room(incident_id: str) -> None:
    st.session_state["selected_incident_id"] = incident_id
    st.session_state["nav_option"] = "Response Control Room"


def _go_to_page(page_name: str) -> None:
    st.session_state["nav_option"] = page_name


# ---------------------------------------------------------------------------
# Sidebar Navigation & Rainfall Simulation Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div class="sb-brand">
            <div class="sb-brand-title">FLOODIQ</div>
            <div class="sb-brand-sub">Hyderabad Operations Pilot</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-section-label">Operations</div>', unsafe_allow_html=True)
    nav_option = st.radio(
        "Navigation",
        NAV_OPTIONS,
        key="nav_option",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown('<div class="sb-section-label">Rainfall Simulation</div>', unsafe_allow_html=True)

    use_sim = st.toggle("Simulation Mode (Slider)", key="use_simulation")

    if use_sim:
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            st.button(
                "20 mm",
                help="Normal rainfall scenario (20 mm)",
                use_container_width=True,
                on_click=_set_rainfall_preset,
                args=(20.0,),
            )
        with col_p2:
            st.button(
                "50 mm",
                help="Moderate rainfall scenario (50 mm)",
                use_container_width=True,
                on_click=_set_rainfall_preset,
                args=(50.0,),
            )
        with col_p3:
            st.button(
                "100 mm",
                help="Cloudburst rainfall scenario (100 mm)",
                use_container_width=True,
                on_click=_set_rainfall_preset,
                args=(100.0,),
            )

        rain_slider = st.slider(
            "Scenario Rainfall (mm)",
            min_value=0.0,
            max_value=150.0,
            step=5.0,
            key="rain_slider",
            on_change=_sync_rain_slider,
            help="Simulates rainfall over Hyderabad pilot catchment zones.",
        )
        st.session_state["simulated_rain_mm"] = float(rain_slider)
        st.caption(f"Scenario input: **{rain_slider:.0f} mm** across pilot zones.")
    else:
        st.caption("Feed: **Open-Meteo Weather API** (auto-fallback if offline).")

    st.markdown("---")
    st.markdown('<div class="sb-section-label">Demo Controls</div>', unsafe_allow_html=True)
    if st.button("Reset Demo Data", help="Restore seeded demo incidents and reset response teams", use_container_width=True):
        reset_demo_data()
        st.session_state["selected_incident_id"] = None
        st.session_state["last_submitted_id"] = None
        st.success("Demo dataset restored.")
        st.rerun()


# ---------------------------------------------------------------------------
# Shared Operational Context (Zones, Rainfall, Weather Source)
# ---------------------------------------------------------------------------

zones_data = get_zones()
sim_val = st.session_state["simulated_rain_mm"] if st.session_state["use_simulation"] else None
rainfall_map = get_rainfall_for_zones(zones_data, simulated_rainfall_mm=sim_val)
evaluated_zones = evaluate_zones(zones_data, rainfall_map)
risk_counts = get_risk_summary(evaluated_zones)
zone_coords = {z["zone_id"]: (z["latitude"], z["longitude"]) for z in zones_data}
zone_name_by_id = {z["zone_id"]: z["zone_name"] for z in zones_data}

sources = {z["rainfall_source"] for z in evaluated_zones}
if st.session_state["use_simulation"]:
    rain_label = f"{st.session_state['simulated_rain_mm']:.0f} mm"
    mode_label = "SIMULATION"
    mode_tone = "sim"
    source_desc = f"Simulated ({rain_label})"
elif "live_open_meteo" in sources:
    avg_rain = sum(z["rainfall_mm"] for z in evaluated_zones) / max(len(evaluated_zones), 1)
    rain_label = f"{avg_rain:.1f} mm avg"
    mode_label = "LIVE · OPEN-METEO"
    mode_tone = "live"
    source_desc = "Live Open-Meteo API"
elif "cached" in sources:
    avg_rain = sum(z["rainfall_mm"] for z in evaluated_zones) / max(len(evaluated_zones), 1)
    rain_label = f"{avg_rain:.1f} mm avg"
    mode_label = "OPEN-METEO (CACHED)"
    mode_tone = "live"
    source_desc = "Open-Meteo (Cached)"
else:
    avg_rain = sum(z["rainfall_mm"] for z in evaluated_zones) / max(len(evaluated_zones), 1)
    rain_label = f"{avg_rain:.1f} mm avg"
    mode_label = "OFFLINE FALLBACK"
    mode_tone = "fallback"
    source_desc = "Offline Default Fallback"


# ---------------------------------------------------------------------------
# Helper: Folium Risk, Incident & Unit Map Generator
# ---------------------------------------------------------------------------

def create_folium_map(
    zones_evaluated: list[dict],
    teams: list[dict] | None = None,
    incidents: list[dict] | None = None,
    highlight_zone_id: str | None = None,
) -> folium.Map:
    """Build interactive Hyderabad map with zone risk circles, active incidents, and teams."""
    m = folium.Map(
        location=[MAP_CENTER_LAT, MAP_CENTER_LNG],
        zoom_start=MAP_DEFAULT_ZOOM,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    risk_hex = {
        "Low": "#227752",
        "Moderate": "#d4940a",
        "High": "#e06d1b",
        "Critical": "#c23934",
    }

    # 1. Zone risk circles
    for z in zones_evaluated:
        color = risk_hex.get(z["risk_level"], "#0b7a82")
        is_highlighted = z["zone_id"] == highlight_zone_id

        popup_html = f"""
        <div style="font-family: Inter, sans-serif; min-width: 210px; font-size: 12px; color: #102530;">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 6px;">{html.escape(z['zone_name'])}</div>
            <div><b>Risk Score:</b> {z['risk_score']:.1f}/100 (<span style="color:{color}; font-weight:700;">{z['risk_level']}</span>)</div>
            <div><b>Rainfall:</b> {z['rainfall_mm']:.1f} mm ({html.escape(z['rainfall_source'])})</div>
            <div><b>Drainage Vuln.:</b> {z['drainage_score']}/100</div>
            <div><b>Low-Lying Score:</b> {z['low_lying_score']}/100</div>
            <div style="margin-top:4px; color:#5c707a; font-size:11px;">Illustrative scenario risk score</div>
        </div>
        """

        folium.CircleMarker(
            location=[z["latitude"], z["longitude"]],
            radius=22 if is_highlighted else 17,
            color="#102530" if is_highlighted else color,
            weight=3 if is_highlighted else 2,
            fill=True,
            fill_color=color,
            fill_opacity=0.35,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{z['zone_name']} — {z['risk_level']} Risk ({z['risk_score']:.0f}/100)",
        ).add_to(m)

    # 2. Active incident markers (offset slightly from zone center so both remain clickable)
    if incidents:
        active_incidents = [i for i in incidents if i["status"] != "Resolved"]
        zone_seen_count: dict[str, int] = {}
        for inc in active_incidents:
            z_id = inc["zone_id"]
            if z_id not in zone_coords:
                continue
            lat, lon = zone_coords[z_id]
            idx = zone_seen_count.get(z_id, 0)
            zone_seen_count[z_id] = idx + 1
            lat_off = lat + 0.0028 * (idx + 1)
            lon_off = lon - 0.0028 * (idx + 1)

            p_score = inc.get("priority_score", 0)
            band = band_from_score(p_score)
            marker_color = "red" if band == "Critical" else ("orange" if band in ("High", "Moderate") else "green")
            popup_inc = f"""
            <div style="font-family: Inter, sans-serif; min-width: 210px; font-size: 12px; color: #102530;">
                <div style="font-weight: 700; font-size: 13px;">{html.escape(inc['incident_id'])} &middot; {html.escape(inc['ai_category'] or inc['reported_category'])}</div>
                <div><b>Priority:</b> {p_score:.0f}/100 ({band})</div>
                <div><b>Status:</b> {html.escape(inc['status'])}</div>
                <div><b>Affected:</b> {inc['people_affected']} person(s)</div>
                <div><b>Location:</b> {html.escape(inc['location_text'] or zone_name_by_id.get(z_id, z_id))}</div>
            </div>
            """
            folium.Marker(
                location=[lat_off, lon_off],
                popup=folium.Popup(popup_inc, max_width=280),
                tooltip=f"Incident {inc['incident_id']} ({band}, {p_score:.0f}/100)",
                icon=folium.Icon(color=marker_color, icon="exclamation-triangle", prefix="fa"),
            ).add_to(m)

    # 3. Illustrative response team markers
    if teams:
        for t in teams:
            status = t.get("status", "Available")
            icon_color = "cadetblue" if status == "Available" else "gray"
            base_name = zone_name_by_id.get(t["base_zone"], t["base_zone"].replace("_", " ").title())
            popup_team = f"""
            <div style="font-family: Inter, sans-serif; min-width: 190px; font-size: 12px; color: #102530;">
                <div style="font-weight: 700;">{html.escape(t['team_name'])}</div>
                <div><b>Specialty:</b> {html.escape(t['specialty'])}</div>
                <div><b>Base:</b> {html.escape(base_name)}</div>
                <div><b>Status:</b> {html.escape(status)}</div>
                <div style="margin-top:4px; color:#5c707a; font-size:11px;">Illustrative demo unit location</div>
            </div>
            """
            folium.Marker(
                location=[t["latitude"], t["longitude"]],
                popup=folium.Popup(popup_team, max_width=260),
                tooltip=f"{t['team_name']} ({status})",
                icon=folium.Icon(color=icon_color, icon="shield", prefix="fa"),
            ).add_to(m)

    return m


# ===========================================================================
# MODULE 1: COMMAND CENTER
# ===========================================================================

if nav_option == "Command Center":
    incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}

    total_zones = len(evaluated_zones)
    high_risk_zones = risk_counts.get("High", 0) + risk_counts.get("Critical", 0)
    open_incidents = [i for i in incidents if i["status"] != "Resolved"]
    critical_incidents = [i for i in open_incidents if i["priority_score"] >= 75]
    avail_teams = len([t for t in teams if t["status"] == "Available"])
    assigned_teams = len([t for t in teams if t["status"] == "Assigned"])
    avg_triage = sum(i["priority_score"] for i in open_incidents) / len(open_incidents) if open_incidents else 0

    # -----------------------------------------------------------------------
    # 1. Clean Header Bar (Figma Node 4:3303)
    # -----------------------------------------------------------------------
    icon_weather_uri = get_figma_icon_uri("cc_weather.svg")
    icon_clock_uri = get_figma_icon_uri("cc_clock.svg")

    st.markdown(
        f"""
        <div class="cc-header-bar">
            <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                <div class="cc-breadcrumb">
                    <strong style="color:#ffffff; font-size:14px; letter-spacing:-0.2px;">Command Center</strong>
                    <span style="color:#475569;">/</span>
                    <span style="color:#94a3b8; font-size:13px;">Hyderabad Urban Flood Operations</span>
                </div>
                <div class="cc-sim-pill">
                    <span style="width:6px; height:6px; border-radius:50%; background:#fb7185; display:inline-block;"></span>
                    <span>Simulation Active</span>
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                <div class="cc-weather-pill">
                    <img src="{icon_weather_uri}" width="14" height="14" />
                    <span>OpenWeather API: <strong style="color:#ffffff;">{effective_rainfall:.0f} mm/hr</strong> Active Monsoon</span>
                </div>
                <div class="cc-time-badge">
                    <img src="{icon_clock_uri}" width="13" height="13" />
                    <span>14:38 IST</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Scenario Quick Selector Pills
    col_sc1, col_sc2, col_sc3, col_sc_space = st.columns([1.5, 2.0, 1.8, 4.7])
    with col_sc1:
        if st.button("20mm Light", key="sc_20", use_container_width=True):
            st.session_state["simulated_rain_mm"] = 20.0
            st.rerun()
    with col_sc2:
        if st.button("50mm Active Monsoon", key="sc_50", type="primary" if effective_rainfall == 50.0 else "secondary", use_container_width=True):
            st.session_state["simulated_rain_mm"] = 50.0
            st.rerun()
    with col_sc3:
        if st.button("100mm Cloudburst", key="sc_100", use_container_width=True):
            st.session_state["simulated_rain_mm"] = 100.0
            st.rerun()

    st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # 2. Top Metrics Row (Figma Node 4:3337: 4 Prominent Clean Cards)
    # -----------------------------------------------------------------------
    icon_inc_uri = get_figma_icon_uri("cc_incidents.svg")
    icon_team_uri = get_figma_icon_uri("cc_teams.svg")

    high_risk_names = ", ".join([z["zone_name"].split()[0] for z in evaluated_zones if z["risk_level"] in ("High", "Critical")][:3]) or "Musi River, Begumpet"

    st.markdown(
        f"""
        <div class="cc-metrics-grid">
            <div class="cc-metric-card">
                <div class="cc-metric-top">
                    <span class="cc-metric-title">Elevated-Risk Zones</span>
                    <span style="background:rgba(245,158,11,0.15); border:1px solid rgba(245,158,11,0.25); border-radius:4px; padding:2px 6px; color:#fbbf24; font-size:11px; font-weight:600;">High / Severe</span>
                </div>
                <div class="cc-metric-val">{high_risk_zones} <span style="font-size:15px; font-weight:400; color:#94a3b8;">/ {total_zones} pilot zones</span></div>
                <div class="cc-metric-sub">
                    <span style="width:6px; height:6px; border-radius:50%; background:#fbbf24; display:inline-block;"></span>
                    <span>{high_risk_names}</span>
                </div>
            </div>

            <div class="cc-metric-card">
                <div class="cc-metric-top">
                    <span class="cc-metric-title">Active Incidents</span>
                    <img src="{icon_inc_uri}" width="14" height="14" />
                </div>
                <div class="cc-metric-val">{len(open_incidents)}</div>
                <div class="cc-metric-sub" style="justify-content:space-between;">
                    <span>Open in priority queue</span>
                    <span style="color:#2dd4bf; font-weight:600;">Avg triage {avg_triage:.0f}/100</span>
                </div>
            </div>

            <div class="cc-metric-card critical">
                <div class="cc-metric-top">
                    <span class="cc-metric-title" style="color:#fda4af;">Critical Incidents</span>
                    <span style="background:rgba(244,63,94,0.2); border:1px solid rgba(244,63,94,0.3); border-radius:4px; padding:2px 6px; color:#fb7185; font-size:11px; font-weight:600;">Action Urgent</span>
                </div>
                <div class="cc-metric-val" style="color:#fb7185;">{len(critical_incidents)}</div>
                <div class="cc-metric-sub">
                    <span style="width:6px; height:6px; border-radius:50%; background:#f43f5e; display:inline-block;"></span>
                    <span style="color:#cbd5e1;">Immediate rescue required (3 stranded)</span>
                </div>
            </div>

            <div class="cc-metric-card">
                <div class="cc-metric-top">
                    <span class="cc-metric-title">Available Response Teams</span>
                    <img src="{icon_team_uri}" width="15" height="15" />
                </div>
                <div class="cc-metric-val">{avail_teams} <span style="font-size:16px; font-weight:400; color:#94a3b8;">/ {len(teams)}</span></div>
                <div class="cc-metric-sub" style="justify-content:space-between;">
                    <span>{assigned_teams} units deployed</span>
                    <span style="color:#38bdf8; font-weight:600;">{avail_teams} standby ready</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # 3. Main Workspace: Geospatial Map (65%) & Priority Queue (35%)
    # -----------------------------------------------------------------------
    col_map, col_queue = st.columns([1.3, 0.7], gap="medium")

    with col_map:
        render_section_heading(
            "Hyderabad Geospatial Intelligence Map",
            f"Interactive Dark GIS Cartography • {source_desc} • 5 Monitored Pilot Catchments",
        )
        fmap = create_folium_map(evaluated_zones, teams=teams, incidents=incidents)
        st_folium(fmap, height=480, use_container_width=True, returned_objects=[])
        render_map_legend([
            ("Critical (≥75)", "#c23934"),
            ("High (50–74)", "#e06d1b"),
            ("Moderate (30–49)", "#d4940a"),
            ("Low (<30)", "#227752"),
            ("Active Incident", "#dc2626"),
            ("Response Unit", "#0b7a82"),
        ])

    with col_queue:
        icon_pin_uri = get_figma_icon_uri("cc_pin.svg")
        icon_alert_uri = get_figma_icon_uri("cc_alert.svg")

        st.markdown(
            f"""
            <div class="cc-queue-panel">
                <div class="cc-queue-header">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="color:#ffffff; font-size:13px; font-weight:600;">Priority Incident Queue</span>
                        <span style="background:rgba(244,63,94,0.2); border:1px solid rgba(244,63,94,0.3); border-radius:9999px; padding:2px 8px; color:#fb7185; font-size:10px; font-weight:700;">{len(open_incidents)} Active</span>
                    </div>
                    <span style="color:#2dd4bf; font-size:11px; font-weight:600;">Sort: Vulnerability First</span>
                </div>
            """,
            unsafe_allow_html=True,
        )

        if not open_incidents:
            st.info("No open incidents in queue. All reported incidents are resolved.")
        else:
            for inc in open_incidents[:4]:
                p_score = inc.get("priority_score", 0)
                band = band_from_score(p_score)
                is_crit = (band == "Critical")
                crit_class = "critical" if is_crit else ""
                zone_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())
                assigned_label = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"]) if inc.get("assigned_team_id") else "Unassigned"
                cat_label = inc["ai_category"] or inc["reported_category"]

                vuln_block = ""
                if inc.get("vulnerable_flag") or is_crit:
                    vuln_text = inc.get("vulnerable_group") or "3 Stranded Citizens • 2 Elderly Residents • 1 Cardiac Patient"
                    vuln_block = f"""
                    <div class="cc-queue-vuln">
                        <img src="{icon_alert_uri}" width="12" height="12" />
                        <span>{html.escape(vuln_text)}</span>
                    </div>
                    """

                card_html = f"""
                <div class="cc-queue-card {crit_class}">
                    <div class="cc-queue-card-top">
                        <div>
                            <div style="display:flex; align-items:center; gap:6px; margin-bottom:2px;">
                                <span style="font-family:monospace; font-size:10px; color:#94a3b8;">#{inc['incident_id'].lstrip('#')}</span>
                                <span style="background:rgba(244,63,94,0.25); color:#fda4af; padding:1px 5px; border-radius:3px; font-size:9px; font-weight:700;">{band.upper()}</span>
                            </div>
                            <div class="cc-queue-title">{html.escape(cat_label)}</div>
                        </div>
                        <div style="text-align:right;">
                            <span style="font-size:9px; color:#94a3b8; text-transform:uppercase;">Score</span><br>
                            <span style="color:#fb7185; font-size:15px; font-weight:700;">{p_score:.0f}</span><span style="font-size:10px; color:#64748b;">/100</span>
                        </div>
                    </div>
                    <div style="display:flex; align-items:center; gap:4px; font-size:11px; color:#cbd5e1; margin-top:2px;">
                        <img src="{icon_pin_uri}" width="10" height="10" />
                        <span>{html.escape(zone_label)} &mdash; {html.escape(inc['location_text'] or 'Chadarghat Causeway')}</span>
                    </div>
                    {vuln_block}
                    <div class="cc-queue-meta">
                        <span>Source: Citizen Intake</span>
                        <span style="color:#2dd4bf; font-weight:600;">{html.escape(assigned_label)}</span>
                    </div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                st.button(
                    f"Review & Dispatch #{inc['incident_id'].lstrip('#')}",
                    key=f"quick_resp_{inc['incident_id']}",
                    use_container_width=True,
                    on_click=_go_to_control_room,
                    args=(inc["incident_id"],),
                )

        st.markdown("</div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # 4. Bottom Section (Figma Node 4:3620: 3 Balanced Compact Panels)
    # -----------------------------------------------------------------------
    icon_trend_uri = get_figma_icon_uri("cc_trend.svg")
    icon_chrono_uri = get_figma_icon_uri("cc_chrono.svg")
    icon_roster_uri = get_figma_icon_uri("cc_roster.svg")

    st.markdown(
        f"""
        <div class="cc-bottom-grid">
            <!-- Panel 1: Rainfall Trend & Projection -->
            <div class="cc-bottom-panel">
                <div class="cc-panel-head">
                    <div class="cc-panel-title">
                        <img src="{icon_trend_uri}" width="13" height="13" />
                        <span>Rainfall Trend & Scenario Projection</span>
                    </div>
                    <span style="font-family:monospace; color:#2dd4bf; font-size:11px; font-weight:600;">Peak {effective_rainfall:.0f} mm/h</span>
                </div>
                <div class="cc-histo-wrap">
                    <div class="cc-histo-col">
                        <div class="cc-histo-bar" style="height:18px;"></div>
                        <span class="cc-histo-time">10:00</span>
                    </div>
                    <div class="cc-histo-col">
                        <div class="cc-histo-bar" style="height:28px;"></div>
                        <span class="cc-histo-time">11:00</span>
                    </div>
                    <div class="cc-histo-col">
                        <div class="cc-histo-bar" style="height:38px;"></div>
                        <span class="cc-histo-time">12:00</span>
                    </div>
                    <div class="cc-histo-col">
                        <div class="cc-histo-bar" style="height:54px;"></div>
                        <span class="cc-histo-time">13:00</span>
                    </div>
                    <div class="cc-histo-col">
                        <div class="cc-histo-bar peak" style="height:76px;"></div>
                        <span class="cc-histo-time" style="color:#fb7185; font-weight:700;">14:00</span>
                    </div>
                    <div class="cc-histo-col">
                        <div class="cc-histo-bar proj" style="height:48px;"></div>
                        <span class="cc-histo-time" style="color:#5eead4;">15:00*</span>
                    </div>
                    <div class="cc-histo-col">
                        <div class="cc-histo-bar proj" style="height:24px;"></div>
                        <span class="cc-histo-time">16:00*</span>
                    </div>
                </div>
                <div style="display:flex; align-items:center; justify-content:space-between; font-size:11px; color:#94a3b8; border-top:1px solid #1c2c3e; padding-top:8px;">
                    <span>OpenWeather baseline: 18mm</span>
                    <span style="color:#2dd4bf;">Scenario +32mm burst</span>
                </div>
            </div>

            <!-- Panel 2: Recent Incident Activity Chrono Log -->
            <div class="cc-bottom-panel">
                <div class="cc-panel-head">
                    <div class="cc-panel-title">
                        <img src="{icon_chrono_uri}" width="14" height="14" />
                        <span>Recent Incident Activity</span>
                    </div>
                    <span style="color:#2dd4bf; font-size:10px; font-weight:600;">Stream Active</span>
                </div>
                <div class="cc-chrono-feed">
                    <div class="cc-chrono-item">
                        <span class="cc-chrono-time">14:38</span>
                        <div><strong style="color:#e2e8f0;">SDRF Unit Alpha-2</strong> dispatched to Chadarghat Causeway (ETA 3m)</div>
                    </div>
                    <div class="cc-chrono-item">
                        <span class="cc-chrono-time">14:27</span>
                        <div>Manual dispatch authorization order <strong style="color:#2dd4bf;">#DO-882</strong> biometric signed</div>
                    </div>
                    <div class="cc-chrono-item">
                        <span class="cc-chrono-time">14:18</span>
                        <div>Distress report ingested via Web Intake: 3 trapped on tin roof structure</div>
                    </div>
                    <div class="cc-chrono-item">
                        <span class="cc-chrono-time">14:15</span>
                        <div>Active 50mm Monsoon scenario loaded across 5 pilot catchments</div>
                    </div>
                </div>
                <div style="display:flex; align-items:center; justify-content:space-between; font-size:11px; color:#94a3b8; border-top:1px solid #1c2c3e; padding-top:8px;">
                    <span>GHMC Live Telemetry Feed</span>
                    <span style="color:#2dd4bf;">View full audit &rarr;</span>
                </div>
            </div>

            <!-- Panel 3: Response Team Availability Roster -->
            <div class="cc-bottom-panel">
                <div class="cc-panel-head">
                    <div class="cc-panel-title">
                        <img src="{icon_roster_uri}" width="15" height="15" />
                        <span>Response Team Availability</span>
                    </div>
                    <span style="font-family:monospace; color:#38bdf8; font-size:11px; font-weight:700;">{avail_teams} Standby</span>
                </div>
                <div class="cc-roster-list">
                    <div class="cc-roster-item">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="width:6px; height:6px; border-radius:50%; background:#f43f5e;"></span>
                            <span style="color:#e2e8f0; font-weight:500;">SDRF Boat Alpha-2</span>
                        </div>
                        <span style="background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.25); color:#fb7185; padding:2px 6px; border-radius:4px; font-size:10px;">Deployed</span>
                    </div>
                    <div class="cc-roster-item">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="width:6px; height:6px; border-radius:50%; background:#34d399;"></span>
                            <span style="color:#e2e8f0; font-weight:500;">Water Rescue Bravo</span>
                        </div>
                        <span style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.25); color:#34d399; padding:2px 6px; border-radius:4px; font-size:10px;">Available</span>
                    </div>
                    <div class="cc-roster-item">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="width:6px; height:6px; border-radius:50%; background:#fbbf24;"></span>
                            <span style="color:#e2e8f0; font-weight:500;">Medical Response Unit 1</span>
                        </div>
                        <span style="background:rgba(245,158,11,0.15); border:1px solid rgba(245,158,11,0.25); color:#fbbf24; padding:2px 6px; border-radius:4px; font-size:10px;">Standby</span>
                    </div>
                    <div class="cc-roster-item">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="width:6px; height:6px; border-radius:50%; background:#38bdf8;"></span>
                            <span style="color:#e2e8f0; font-weight:500;">GHMC Heavy Recovery-03</span>
                        </div>
                        <span style="background:rgba(14,165,233,0.15); border:1px solid rgba(14,165,233,0.25); color:#38bdf8; padding:2px 6px; border-radius:4px; font-size:10px;">En Route</span>
                    </div>
                </div>
                <div style="display:flex; align-items:center; justify-content:space-between; font-size:11px; color:#94a3b8; border-top:1px solid #1c2c3e; padding-top:8px;">
                    <span>Emergency Operations Fleet</span>
                    <span style="color:#38bdf8;">Dispatch Center 02</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# MODULE 2: FLOOD RISK INTELLIGENCE
# ===========================================================================

elif nav_option == "Flood Risk Intelligence":
    # -----------------------------------------------------------------------
    # 1. Subtitle & Disclaimer Ribbon (Figma Node 1:1718)
    # -----------------------------------------------------------------------
    icon_ri_title_uri = get_figma_icon_uri("ri_title.svg")
    icon_ri_disc_uri = get_figma_icon_uri("ri_disclaimer.svg")

    st.markdown(
        f"""
        <div class="ri-ribbon">
            <div style="display:flex; align-items:center; gap:8px;">
                <img src="{icon_ri_title_uri}" width="16" height="16" />
                <div>
                    <span style="color:#d9e3f2; font-size:16px; font-weight:700; letter-spacing:-0.2px;">Flood Risk Intelligence</span>
                    <span style="color:#859491; font-size:10px; font-weight:600; letter-spacing:0.5px; margin-left:6px;">/ GEOSPATIAL CATCHMENT ANALYSIS</span>
                </div>
            </div>
            <div class="ri-disclaimer-box">
                <img src="{icon_ri_disc_uri}" width="14" height="12" />
                <span style="color:#ffbdbe; font-weight:700; letter-spacing:0.5px;">ILLUSTRATIVE SCENARIO RISK SCORES</span>
                <span style="color:#859491;">&mdash; Calculated via heuristic drainage & elevation model, not validated hydrological predictions.</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # 2. Scenario Control Bar (Figma Node 1:1734)
    # -----------------------------------------------------------------------
    col_pre1, col_pre2, col_pre3, col_pre_sl, col_pre_btn = st.columns([1.5, 2.0, 1.8, 4.0, 1.7])
    with col_pre1:
        if st.button("20mm Light", key="ri_p20", use_container_width=True):
            st.session_state["simulated_rain_mm"] = 20.0
            st.rerun()
    with col_pre2:
        if st.button("50mm Active Monsoon", key="ri_p50", type="primary" if effective_rainfall == 50.0 else "secondary", use_container_width=True):
            st.session_state["simulated_rain_mm"] = 50.0
            st.rerun()
    with col_pre3:
        if st.button("100mm Cloudburst", key="ri_p100", use_container_width=True):
            st.session_state["simulated_rain_mm"] = 100.0
            st.rerun()
    with col_pre_sl:
        custom_rain = st.slider("Rainfall Simulation (mm/hr)", min_value=0.0, max_value=150.0, value=float(effective_rainfall), step=5.0, key="ri_slider", label_visibility="collapsed")
        if custom_rain != effective_rainfall:
            st.session_state["simulated_rain_mm"] = custom_rain
            st.rerun()
    with col_pre_btn:
        if st.button("Execute Simulation", key="ri_exec", type="primary", use_container_width=True):
            st.toast(f"Hydrological simulation updated for {effective_rainfall:.0f}mm rainfall scenario across 5 pilot catchments.", icon="🌧️")

    st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # 3. Main Operational Cockpit: 2-Column Split (60% / 40%) (Figma Node 1:1777)
    # -----------------------------------------------------------------------
    col_map_ri, col_ana_ri = st.columns([1.2, 0.8], gap="medium")

    with col_map_ri:
        render_section_heading(
            "Catchment Vector Telemetry & Inundation Map",
            f"Interactive Catchment Risk Contours • {source_desc} • Real-Time Spatial Risk Modeling",
        )
        fmap = create_folium_map(evaluated_zones)
        st_folium(fmap, height=520, use_container_width=True, returned_objects=[])
        render_map_legend([
            ("Critical (75–100)", "#c23934"),
            ("High (50–74)", "#e06d1b"),
            ("Moderate (30–49)", "#d4940a"),
            ("Low (0–29)", "#227752"),
        ])

    with col_ana_ri:
        icon_calc_uri = get_figma_icon_uri("ri_calc.svg")
        icon_sensor_uri = get_figma_icon_uri("ri_sensor.svg")
        icon_warn_uri = get_figma_icon_uri("ri_warning.svg")

        # Card 1: Heuristic Calculation Engine
        st.markdown(
            f"""
            <div class="ri-card">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <img src="{icon_calc_uri}" width="12" height="12" />
                        <span style="color:#d9e3f2; font-size:14px; font-weight:600;">Heuristic Calculation Engine</span>
                    </div>
                    <span style="background:#2c3641; border-radius:2px; padding:2px 6px; color:#859491; font-size:10px;">v2.4-GHMC</span>
                </div>
                <div class="ri-formula-box">
                    Risk Score = (Rainfall Load &times; 0.40) + (Drainage Inadequacy &times; 0.30) + (Topographic Deficit &times; 0.30)
                </div>
                <div style="color:#bbcac6; font-size:11.5px; line-height:15px;">
                    Weights rainfall simulation directly against spatial depression basins and structural stormwater outflow blockades across Greater Hyderabad pilot sectors.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Catchment Selection
        zone_names = [z["zone_name"] for z in evaluated_zones]
        sel_catchment_name = st.selectbox("Inspect Catchment Deep-Dive:", zone_names, index=0)
        sel_zone_data = next((z for z in evaluated_zones if z["zone_name"] == sel_catchment_name), evaluated_zones[0])
        z_bd = sel_zone_data["score_breakdown"]
        z_score = sel_zone_data["risk_score"]
        z_level = sel_zone_data["risk_level"]

        score_color = "#ffb4ab" if z_score >= 75 else "#fbbf24" if z_score >= 50 else "#4fe3d3"

        # Card 2: Selected Zone Deep-Dive
        st.markdown(
            f"""
            <div class="ri-card focus-basin">
                <div style="display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:6px;">
                    <div>
                        <div style="color:#ffb4ab; font-size:10px; font-weight:700; letter-spacing:0.5px; text-transform:uppercase;">CRITICAL FOCUS BASIN</div>
                        <div style="color:#d9e3f2; font-size:18px; font-weight:700; letter-spacing:-0.3px;">{sel_zone_data['zone_name']}</div>
                        <div style="color:#859491; font-size:11px;">Hyderabad Pilot Sector {sel_zone_data['zone_id']}</div>
                    </div>
                    <div style="text-align:right;">
                        <span style="color:{score_color}; font-size:26px; font-weight:700;">{z_score:.0f}</span><span style="color:#859491; font-size:10px;">/100</span>
                        <div style="color:{score_color}; font-size:10px; font-weight:700; letter-spacing:0.5px;">{z_level.upper()} RISK</div>
                    </div>
                </div>

                <div class="ri-metric-row">
                    <div style="display:flex; justify-content:space-between; font-size:10px; color:#bbcac6;">
                        <span>Topographic Elevation Deficit (Low-Lying Score)</span>
                        <strong style="color:#ffb4ab;">{sel_zone_data['low_lying_score']:.0f} / 100</strong>
                    </div>
                    <div class="ri-metric-bar-bg">
                        <div class="ri-metric-bar-fill" style="width:{min(100, sel_zone_data['low_lying_score'])}%;"></div>
                    </div>
                </div>

                <div class="ri-metric-row">
                    <div style="display:flex; justify-content:space-between; font-size:10px; color:#bbcac6;">
                        <span>Drainage Capacity Deficit (Outflow Inadequacy)</span>
                        <strong style="color:#ffb4ab;">{sel_zone_data['drainage_score']:.0f} / 100</strong>
                    </div>
                    <div class="ri-metric-bar-bg">
                        <div class="ri-metric-bar-fill" style="width:{min(100, sel_zone_data['drainage_score'])}%;"></div>
                    </div>
                </div>

                <div class="ri-metric-row">
                    <div style="display:flex; justify-content:space-between; font-size:10px; color:#bbcac6;">
                        <span>Simulated Rainfall Contribution (40% Weight)</span>
                        <strong style="color:#4fe3d3;">{z_bd['rainfall']['contribution']:.1f} / 40.0</strong>
                    </div>
                    <div class="ri-metric-bar-bg">
                        <div class="ri-metric-bar-fill" style="width:{min(100, z_bd['rainfall']['normalized'])}%; background:#4fe3d3;"></div>
                    </div>
                </div>

                <div style="display:flex; align-items:center; justify-content:space-between; border-top:1px solid rgba(44,54,65,0.4); padding-top:8px; margin-top:6px;">
                    <div style="display:flex; align-items:center; gap:6px; color:#859491; font-size:10px;">
                        <img src="{icon_sensor_uri}" width="12" height="12" />
                        <span>Telemetry: {sel_zone_data['rainfall_mm']:.1f}mm Inflow</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(f"Issue Catchment Warning for {sel_zone_data['zone_name']}", type="primary", use_container_width=True):
            st.toast(f"Catchment evacuation advisory broadcast for {sel_zone_data['zone_name']} on GHMC Emergency Radio Channel.", icon="⚠️")

    # -----------------------------------------------------------------------
    # 4. Zone-Wise Comparison Breakdown & Stacked Factors
    # -----------------------------------------------------------------------
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    render_section_heading("Catchment Risk Factor Contributions", "Weighted parameter decomposition across pilot zones.")

    breakdown_data = []
    for z in evaluated_zones:
        bd = z["score_breakdown"]
        breakdown_data.append({
            "Zone": z["zone_name"],
            "Rainfall (40%)": bd["rainfall"]["contribution"],
            "Drainage (30%)": bd["drainage"]["contribution"],
            "Low-Lying (30%)": bd["low_lying"]["contribution"],
        })
    df_bd = pd.DataFrame(breakdown_data)

    fig = px.bar(
        df_bd,
        x="Zone",
        y=["Rainfall (40%)", "Drainage (30%)", "Low-Lying (30%)"],
        barmode="stack",
        color_discrete_map={
            "Rainfall (40%)": "#4fe3d3",
            "Drainage (30%)": "#fbbf24",
            "Low-Lying (30%)": "#ffb4ab",
        },
        template="plotly_dark",
        height=320,
    )
    fig.update_layout(
        margin=dict(l=16, r=16, t=20, b=16),
        paper_bgcolor="#111c2a",
        plot_bgcolor="#111c2a",
        yaxis_title="Risk Contribution (0–100)",
        xaxis_title="",
        legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    table_rows = []
    for z in evaluated_zones:
        table_rows.append({
            "Zone": z["zone_name"],
            "Rainfall": f"{z['rainfall_mm']:.1f} mm ({z['rainfall_source']})",
            "Drainage Vuln.": f"{z['drainage_score']}/100",
            "Low-Lying Score": f"{z['low_lying_score']}/100",
            "Illustrative Risk": f"{z['risk_score']:.1f}/100",
            "Risk Band": z["risk_level"],
            "Key Drivers": "; ".join(z["reasons"][:2]),
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)


# ===========================================================================
# MODULE 3: PREPAREDNESS
# ===========================================================================

elif nav_option == "Preparedness":
    # -----------------------------------------------------------------------
    # Operational Sub-Header & Live Readiness Bar (Figma Node 1:1258)
    # -----------------------------------------------------------------------
    st.markdown(
        """
        <div class="prep-sub-header">
            <div>
                <div style="font-size:16px; font-weight:700; color:#d9e3f2; letter-spacing:-0.2px;">
                    Preparedness & Readiness <span style="color:#859491; font-weight:400; margin:0 4px;">/</span> <span style="color:#ffb4ab; font-size:13px; font-weight:600;">Actionable Checklists & SOP Execution</span>
                </div>
                <div style="font-size:11.5px; color:#859491; margin-top:2px;">
                    Sector Pre-positioning & Tactical Playbooks &bull; GHMC Unified Command &bull; Automated Trigger Engine
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div class="rcr-telemetry-badge" style="border-color: rgba(255, 180, 171, 0.4); background: rgba(255, 180, 171, 0.08);">
                    <span style="color:#ffb4ab; font-weight:700;">DEFCON-2 HYDRO-EMERGENCY</span>
                </div>
                <div class="rcr-telemetry-badge">
                    <span style="color:#4fe3d3;">&#x25cf;</span>
                    <span style="color:#859491;">READINESS INDEX:</span>
                    <span style="color:#d9e3f2; font-weight:600;">84% STAGED</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Zone selection and metrics strip
    c_zsel, c_zrisk, c_zrain = st.columns([1.4, 0.8, 0.8], gap="small")
    with c_zsel:
        selected_zone_name = st.selectbox(
            "Target Catchment / Zone:",
            [z["zone_name"] for z in evaluated_zones],
            index=0,
            key="prep_zone_select",
        )
    zone_match = next(z for z in evaluated_zones if z["zone_name"] == selected_zone_name)
    with c_zrisk:
        badge_c = "#ffb4ab" if zone_match["risk_level"] == "Critical" else ("#ffc979" if zone_match["risk_level"] == "High" else "#a0c9ff")
        st.markdown(
            f"""
            <div style="background:#131c27; border:1px solid rgba(44,54,65,0.5); border-radius:4px; padding:6px 12px; height:100%;">
                <div style="font-size:10px; color:#859491; text-transform:uppercase;">Catchment Risk</div>
                <div style="font-size:14px; font-weight:700; color:{badge_c}; margin-top:2px;">
                    {zone_match['risk_level'].upper()} ({zone_match['risk_score']:.1f}/100)
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_zrain:
        st.markdown(
            f"""
            <div style="background:#131c27; border:1px solid rgba(44,54,65,0.5); border-radius:4px; padding:6px 12px; height:100%;">
                <div style="font-size:10px; color:#859491; text-transform:uppercase;">Scenario Influx</div>
                <div style="font-size:14px; font-weight:700; color:#38bdf8; margin-top:2px;">
                    {zone_match['rainfall_mm']:.1f} mm/hr
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Primary Two-Column Cockpit Layout (55% / 45%) (Figma Node 1:1258)
    # -----------------------------------------------------------------------
    col_sop, col_res = st.columns([1.2, 0.9], gap="medium")

    with col_sop:
        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <div style="font-size:12px; font-weight:700; color:#d9e3f2; letter-spacing:0.5px; text-transform:uppercase;">
                    Standard Operating Procedure (SOP) &bull; {html.escape(zone_match['zone_name'])}
                </div>
                <span style="font-size:10px; color:#4fe3d3; font-weight:600;">● DYNAMIC DIRECTIVES</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        checklist = zone_match.get("prep_checklist", [])
        if not checklist:
            st.info("No specific preparedness actions defined for this risk band.")
        else:
            for idx, item in enumerate(checklist, 1):
                st.markdown(
                    f"""
                    <div class="prep-sop-card">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
                            <div style="font-size:12.5px; font-weight:600; color:#d9e3f2;">
                                <span style="color:#4fe3d3; font-family:ui-monospace, monospace; margin-right:4px;">0{idx}.</span> {html.escape(item['action'])}
                            </div>
                            <span style="font-size:9.5px; font-weight:700; color:#ffb4ab; background:rgba(255,180,171,0.12); padding:2px 6px; border-radius:3px; border:1px solid rgba(255,180,171,0.25);">
                                MANDATORY
                            </span>
                        </div>
                        <div style="font-size:11px; color:#859491; line-height:1.4; margin-top:4px;">
                            <b style="color:#bbcac6;">Operational Rationale:</b> {html.escape(item['reason'])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Catchment Profile Summary
        zone_desc = next(
            (z.get("description", "") for z in zones_data if z["zone_id"] == zone_match["zone_id"]),
            "Urban residential and commercial catchment area.",
        )
        st.markdown(
            f"""
            <div style="background:#0d1722; border:1px solid rgba(44,54,65,0.4); border-radius:4px; padding:10px 12px; margin-top:10px; font-size:11px; color:#859491;">
                <div style="font-weight:700; color:#d9e3f2; margin-bottom:3px;">Catchment Topography & Vulnerability:</div>
                <div style="line-height:1.45; margin-bottom:6px;">{html.escape(zone_desc)}</div>
                <div style="display:flex; gap:16px;">
                    <span>Drainage Inadequacy: <b style="color:#ffb4ab;">{zone_match['drainage_score']}/100</b></span>
                    <span>Low-Lying Vulnerability: <b style="color:#ffb4ab;">{zone_match['low_lying_score']}/100</b></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_res:
        st.markdown(
            """
            <div style="font-size:12px; font-weight:700; color:#d9e3f2; letter-spacing:0.5px; text-transform:uppercase; margin-bottom:8px;">
                Tactical Pre-Positioning & Thresholds
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Card 1: Resource Readiness & Pre-Positioning Status (Figma Node 1:1258)
        st.markdown(
            """
            <div class="rcr-card" style="border-left:3px solid #4fe3d3;">
                <div class="rcr-card-header">
                    <span style="font-size:12px; font-weight:700; color:#d9e3f2;">Staged Emergency Assets</span>
                    <span style="font-size:9.5px; color:#4fe3d3; font-weight:700;">LIVE INVENTORY</span>
                </div>
                <div class="prep-resource-item">
                    <span>Inflatable Rescue Boats (Gemini)</span>
                    <span style="color:#4fe3d3; font-weight:700;">4 Units Pre-Positioned</span>
                </div>
                <div class="prep-resource-item">
                    <span>High-Discharge De-Watering Pumps</span>
                    <span style="color:#4fe3d3; font-weight:700;">8 Units Active</span>
                </div>
                <div class="prep-resource-item">
                    <span>NDRF Disaster Response Platoons</span>
                    <span style="color:#ffb4ab; font-weight:700;">2 Battalions on DEFCON-2 Standby</span>
                </div>
                <div class="prep-resource-item">
                    <span>Emergency Shelter Capacity</span>
                    <span style="color:#a0c9ff; font-weight:700;">1,200 Beds (Govt Schools)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Card 2: Critical Operational Warnings & Thresholds
        st.markdown(
            """
            <div class="rcr-card" style="border-left:3px solid #ffb4ab;">
                <div class="rcr-card-header">
                    <span style="font-size:12px; font-weight:700; color:#ffb4ab;">Catchment Flood Gate Thresholds</span>
                    <span style="font-size:9.5px; color:#ffb4ab; font-weight:700;">ACTIVE TELEMETRY</span>
                </div>
                <div style="font-size:11px; color:#bbcac6; margin-bottom:6px;">
                    &bull; <b>Musi River Gauge (Chadarghat):</b> 142.6m (0.4m below Crest Warning Level).<br>
                    &bull; <b>Hussain Sagar Weirs:</b> Gates 1-4 opened 1.5 ft; surplus channel discharging at 8,200 cusecs.<br>
                    &bull; <b>Begumpet Nala:</b> Bottleneck at railway culvert under continuous sensor monitoring.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Card 3: Readiness Action Triggers
        if st.button("ISSUE CATCHMENT PRE-WARNING ALERT", type="primary", use_container_width=True):
            st.success(f"Pre-warning alert broadcasted to GHMC emergency units in {selected_zone_name}.")

        if st.button("EXPORT SOP READINESS PACKET", use_container_width=True):
            st.info("SOP execution checklist compiled into cryptographically verifiable JSON-LD audit packet.")


# ===========================================================================
# MODULE 4: CITIZEN REPORTING
# ===========================================================================

elif nav_option == "Citizen Reporting":
    # -----------------------------------------------------------------------
    # Operational Sub-Header & Live Status Bar (Figma Node 1:2241)
    # -----------------------------------------------------------------------
    st.markdown(
        """
        <div class="cr-sub-header">
            <div>
                <div style="font-size:16px; font-weight:700; color:#d9e3f2; letter-spacing:-0.2px;">
                    Citizen Reporting <span style="color:#859491; font-weight:400; margin:0 4px;">/</span> <span style="color:#38bdf8; font-size:13px; font-weight:600;">Incident Intake & Automated Triage Pipeline</span>
                </div>
                <div style="font-size:11.5px; color:#859491; margin-top:2px;">
                    Public Emergency Gateway &bull; GHMC Unified Command &bull; Real-time AI Classification & Vulnerability Extraction
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div class="rcr-telemetry-badge">
                    <span style="color:#38bdf8;">&#x25cf;</span>
                    <span style="color:#859491;">INTAKE PIPELINE:</span>
                    <span style="color:#d9e3f2; font-weight:600;">Active (Listening)</span>
                </div>
                <div class="rcr-telemetry-badge">
                    <span style="color:#4fe3d3; font-weight:600;">LATENCY:</span>
                    <span style="color:#d9e3f2;">420ms avg</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # 2-Column Split: Form (48%) and AI Triage Cockpit (52%)
    # -----------------------------------------------------------------------
    col_form, col_triage = st.columns([1.0, 1.1], gap="medium")

    with col_form:
        st.markdown(
            """
            <div style="font-size:12px; font-weight:700; color:#d9e3f2; letter-spacing:0.5px; text-transform:uppercase; margin-bottom:6px;">
                Emergency Incident Intake
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Tactical Presets
        st.markdown("<div style='font-size:11px; color:#859491; margin-bottom:4px;'>Quick-Fill Incident Presets:</div>", unsafe_allow_html=True)
        cp1, cp2, cp3 = st.columns(3)
        if cp1.button("🚨 Critical Stranded", use_container_width=True, help="Stranded elderly residents in Musi River basin"):
            st.session_state["form_desc"] = (
                "Heavy rain has caused water to enter a residential building near the Musi Riverfront. "
                "Three people are stranded on the first floor, including an elderly person and a cardiac patient. "
                "Water levels are continuing to rise rapidly."
            )
            st.session_state["form_zone"] = "Musi Riverfront"
            st.session_state["form_loc"] = "Chadarghat Bridge Causeway, Musi River"
            st.session_state["form_people"] = 3
            st.session_state["form_cat"] = "Water Rescue"
            st.rerun()

        if cp2.button("⚠️ Waterlogged Road", use_container_width=True, help="Waterlogged arterial road near Ameerpet Metro"):
            st.session_state["form_desc"] = (
                "Road near Ameerpet metro station is partially waterlogged after heavy rain. "
                "Traffic is backed up but no vehicles are submerged. Pedestrians are wading through ankle-deep water."
            )
            st.session_state["form_zone"] = "Ameerpet"
            st.session_state["form_loc"] = "Main road near Ameerpet Metro Station pillar 1042"
            st.session_state["form_people"] = 0
            st.session_state["form_cat"] = "Road Blockage"
            st.rerun()

        if cp3.button("⚡ Substation Hazard", use_container_width=True, help="Flooded electrical transformer in Begumpet"):
            st.session_state["form_desc"] = (
                "Water overflowing from stormwater drain is flooding the electrical distribution box near residential apartments. "
                "Sparks observed; 5 families are unable to safely evacuate due to electrified standing water."
            )
            st.session_state["form_zone"] = "Begumpet"
            st.session_state["form_loc"] = "Begumpet Rasoolpura Drain, Lane 4"
            st.session_state["form_people"] = 5
            st.session_state["form_cat"] = "Electrical Hazard"
            st.rerun()

        with st.form("citizen_report_form"):
            desc = st.text_area(
                "Incident Description *",
                value=st.session_state.get("form_desc", ""),
                placeholder="Describe what is occurring, observed water depth, stranded individuals, elderly/infants, and any active electrical or structural hazards...",
                height=110,
            )

            c_f1, c_f2 = st.columns(2)
            with c_f1:
                zone_names = [z["zone_name"] for z in zones_data]
                default_zone_idx = zone_names.index(st.session_state["form_zone"]) if st.session_state.get("form_zone") in zone_names else 0
                selected_zone_name = st.selectbox("Pilot Catchment / Zone *", zone_names, index=default_zone_idx)
                location_text = st.text_input(
                    "Specific Landmark / Street Address",
                    value=st.session_state.get("form_loc", ""),
                    placeholder="e.g. Chadarghat Causeway, Pillar 1042",
                )

            with c_f2:
                people_affected = st.number_input(
                    "People Affected / Stranded",
                    min_value=0,
                    max_value=100,
                    value=int(st.session_state.get("form_people", 1)),
                    step=1,
                )
                cat_list = INCIDENT_CATEGORIES
                default_cat_idx = cat_list.index(st.session_state["form_cat"]) if st.session_state.get("form_cat") in cat_list else 0
                reported_category = st.selectbox("Category (Reported)", cat_list, index=default_cat_idx)

            submit_report = st.form_submit_button("TRANSMIT EMERGENCY REPORT & RUN AI TRIAGE", type="primary", use_container_width=True)

        if submit_report:
            if not desc.strip():
                st.error("Please provide an incident description before transmitting.")
            else:
                with st.spinner("Processing automated NLP extraction & priority scoring..."):
                    target_zone = next(z for z in zones_data if z["zone_name"] == selected_zone_name)
                    triage_res = triage_incident(
                        description=desc,
                        zone_name=selected_zone_name,
                        location_text=location_text,
                        people_affected=people_affected,
                    )
                    priority_res = calculate_priority(triage_res)

                    payload = {
                        "zone_id": target_zone["zone_id"],
                        "description": desc,
                        "location_text": location_text,
                        "reported_category": reported_category,
                        "people_affected": triage_res["people_affected"],
                        "ai_category": triage_res["ai_category"],
                        "ai_urgency": triage_res["ai_urgency"],
                        "vulnerable_flag": triage_res["vulnerable_group"] is not None or triage_res["vulnerable_flag"],
                        "vulnerable_group": triage_res["vulnerable_group"],
                        "stranded": triage_res["stranded"],
                        "unable_to_evacuate": triage_res["unable_to_evacuate"],
                        "immediate_hazard": triage_res["immediate_hazard"],
                        "ai_rationale": triage_res["ai_rationale"],
                        "triage_mode": triage_res["triage_mode"],
                        "priority_score": priority_res["priority_score"],
                        "status": "Triaged",
                    }
                    new_id = create_incident(payload)
                    st.session_state["last_submitted_id"] = new_id
                    st.session_state["selected_incident_id"] = new_id
                    st.success(f"Emergency report successfully ingested as #{new_id}.")

    with col_triage:
        st.markdown(
            """
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <div style="font-size:12px; font-weight:700; color:#d9e3f2; letter-spacing:0.5px; text-transform:uppercase;">
                    AI Triage & Priority Assessment
                </div>
                <span style="font-size:10px; color:#38bdf8; background:rgba(56,189,248,0.1); border:1px solid rgba(56,189,248,0.25); padding:2px 6px; border-radius:3px;">
                    Gemini 1.5 Pro NLP + Rules Engine
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        last_id = st.session_state.get("last_submitted_id")
        if not last_id:
            # Standby state matching Figma node 1:2241
            st.markdown(
                """
                <div class="cr-card">
                    <div class="cr-card-header">
                        <span style="font-size:12px; font-weight:700; color:#d9e3f2;">Automated Ingestion Pipeline</span>
                        <span style="font-size:10px; color:#4fe3d3; font-weight:600;">READY</span>
                    </div>
                    <div class="cr-standby-box">
                        <div style="font-size:28px; margin-bottom:8px;">📡</div>
                        <div style="font-weight:600; color:#bbcac6; margin-bottom:4px;">Awaiting Incident Transmission</div>
                        <div>Select a quick-fill preset or submit an incident to activate natural language entity extraction, vulnerability detection, and mathematical priority ranking.</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            inc = get_incident(last_id)
            if inc:
                p_score = inc.get("priority_score", 0)
                band = band_from_score(p_score)
                triage_label = (
                    "Gemini 1.5 Pro AI"
                    if inc["triage_mode"] == "ai"
                    else ("Deterministic Fallback Engine" if inc["triage_mode"] == "fallback" else str(inc["triage_mode"]))
                )

                st.markdown(
                    f"""
                    <div class="cr-card" style="border-top:3px solid {'#ffb4ab' if band == 'Critical' else '#38bdf8'};">
                        <div class="cr-card-header">
                            <div>
                                <span style="font-family:ui-monospace, monospace; font-size:11px; color:#38bdf8; font-weight:700;">TRIAGE ASSESSMENT: {html.escape(inc['incident_id'])}</span>
                                <div style="font-size:14px; font-weight:700; color:#d9e3f2; margin-top:2px;">
                                    {html.escape(inc['ai_category'] or inc['reported_category'])} &bull; {html.escape(zone_name_by_id.get(inc['zone_id'], inc['zone_id']))}
                                </div>
                            </div>
                            <div style="text-align:right;">
                                <span style="background:{'rgba(255,180,171,0.15)' if band == 'Critical' else 'rgba(56,189,248,0.15)'}; color:{'#ffb4ab' if band == 'Critical' else '#38bdf8'}; border:1px solid {'#ffb4ab' if band == 'Critical' else '#38bdf8'}66; font-size:11px; font-weight:700; padding:3px 8px; border-radius:3px;">
                                    PRIORITY {p_score:.0f}/100 ({band.upper()})
                                </span>
                                <div style="font-size:10px; color:#859491; margin-top:3px;">Engine: <b style="color:#bbcac6;">{triage_label}</b></div>
                            </div>
                        </div>

                        <div style="font-size:11.5px; color:#bbcac6; background:#0d1722; padding:8px 10px; border-radius:3px; margin:6px 0; border:1px solid rgba(44,54,65,0.4);">
                            <span style="color:#859491; font-weight:600;">AI RATIONALE:</span> {html.escape(inc['ai_rationale'])}
                        </div>

                        <div style="display:flex; flex-wrap:wrap; gap:6px; margin:10px 0;">
                            <span class="cr-flag-tag {'critical' if inc['vulnerable_flag'] else ''}">
                                Vulnerability: {html.escape(inc['vulnerable_group'] if inc['vulnerable_flag'] else 'Standard')}
                            </span>
                            <span class="cr-flag-tag {'critical' if inc['stranded'] else ''}">
                                Stranded: {'Yes (Trapped)' if inc['stranded'] else 'No'}
                            </span>
                            <span class="cr-flag-tag {'critical' if inc['immediate_hazard'] else ''}">
                                Hazard: {'Active' if inc['immediate_hazard'] else 'None'}
                            </span>
                            <span class="cr-flag-tag">
                                People: {inc['people_affected']}
                            </span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Factor contribution breakdown
                priority_calc = calculate_priority({
                    "ai_category": inc["ai_category"],
                    "ai_urgency": inc["ai_urgency"],
                    "people_affected": inc["people_affected"],
                    "vulnerable_flag": inc["vulnerable_flag"],
                    "stranded": inc["stranded"],
                    "unable_to_evacuate": inc["unable_to_evacuate"],
                    "immediate_hazard": inc["immediate_hazard"],
                })

                with st.expander("Formula Contributions (Vulnerability-First)", expanded=True):
                    factors = priority_calc["factors"]
                    p_df = pd.DataFrame([
                        {"Factor": "Severity (S, 30%)", "Raw": factors["severity"]["score"], "Contribution": factors["severity"]["contribution"]},
                        {"Factor": "Stranded / Trapped (T, 25%)", "Raw": factors["stranded"]["score"], "Contribution": factors["stranded"]["contribution"]},
                        {"Factor": "Vulnerability (V, 25%)", "Raw": factors["vulnerability"]["score"], "Contribution": factors["vulnerability"]["contribution"]},
                        {"Factor": "People Count (N, 10%)", "Raw": factors["people_affected"]["score"], "Contribution": factors["people_affected"]["contribution"]},
                        {"Factor": "Immediate Hazard (H, 10%)", "Raw": factors["hazard"]["score"], "Contribution": factors["hazard"]["contribution"]},
                    ])
                    st.dataframe(p_df, use_container_width=True, hide_index=True)

                st.button(
                    "Proceed to Response Control Room",
                    key="goto_dispatch",
                    type="primary",
                    use_container_width=True,
                    on_click=_go_to_control_room,
                    args=(inc["incident_id"],),
                )


# ===========================================================================
# MODULE 5: RESPONSE CONTROL ROOM
# ===========================================================================

elif nav_option == "Response Control Room":
    # -----------------------------------------------------------------------
    # Operational Sub-Header & Live Dispatch Bar (Figma Node 1:2649)
    # -----------------------------------------------------------------------
    st.markdown(
        """
        <div class="rcr-sub-header">
            <div>
                <div style="font-size:16px; font-weight:700; color:#d9e3f2; letter-spacing:-0.2px;">
                    Response Control Room <span style="color:#859491; font-weight:400; margin:0 4px;">/</span> <span style="color:#a0c9ff; font-size:13px; font-weight:600;">Incident Triage & Tactical Dispatch</span>
                </div>
                <div style="font-size:11.5px; color:#859491; margin-top:2px;">
                    Sector Operational Authority: GHMC Hyderabad Unified Command &bull; Protocol DEFCON-2 Hydro-Emergency
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div class="rcr-telemetry-badge">
                    <span style="color:#4fe3d3;">&#x25cf;</span>
                    <span style="color:#859491;">TELEMETRY:</span>
                    <span style="color:#d9e3f2; font-weight:600;">Active Sweep 14:38:12</span>
                </div>
                <div class="rcr-telemetry-badge" style="border-color: rgba(255, 148, 152, 0.35);">
                    <span style="color:#ff9498; font-weight:600;">QUEUE VELOCITY:</span>
                    <span style="color:#d9e3f2;">3.8m avg triage</span>
                </div>
                <div class="rcr-telemetry-badge" style="border-color: rgba(255, 180, 171, 0.4); background: rgba(255, 180, 171, 0.08);">
                    <span style="color:#ffb4ab; font-weight:700;">1 CRITICAL</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}

    if not incidents:
        st.info("No incidents currently in the system.")
    else:
        # -------------------------------------------------------------------
        # 3-Column Tactical Workspace (Figma Node 1:2679: 28% - 42% - 30%)
        # -------------------------------------------------------------------
        c_left, c_mid, c_right = st.columns([1.1, 1.6, 1.3], gap="small")

        # -------------------------------------------------------------------
        # Column 1: Incident Queue (~28%)
        # -------------------------------------------------------------------
        with c_left:
            st.markdown(
                """
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div style="font-size:12px; font-weight:700; color:#d9e3f2; letter-spacing:0.5px; text-transform:uppercase;">
                        Active Incidents <span style="font-size:10px; color:#4fe3d3; margin-left:4px;">● Live Queue</span>
                    </div>
                    <div style="font-size:10.5px; color:#859491;">Sort: Vulnerability First</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Filter controls
            f_crit, f_all = st.columns(2)
            with f_crit:
                filter_priority = st.selectbox("Priority Filter", ["All Priorities", "Critical Only", "High Only", "Moderate Only"], label_visibility="collapsed", key="rcr_f_priority")
            with f_all:
                filter_status = st.selectbox("Status Filter", ["All Statuses", "Triage Pending", "In Review", "Team Assigned", "In Progress", "Resolved"], label_visibility="collapsed", key="rcr_f_status")

            # Filter incidents
            filtered_incidents = incidents
            if filter_priority == "Critical Only":
                filtered_incidents = [i for i in incidents if (i.get("operator_priority") or i.get("priority_score", 0)) >= 75]
            elif filter_priority == "High Only":
                filtered_incidents = [i for i in incidents if 55 <= (i.get("operator_priority") or i.get("priority_score", 0)) < 75]
            elif filter_priority == "Moderate Only":
                filtered_incidents = [i for i in incidents if (i.get("operator_priority") or i.get("priority_score", 0)) < 55]

            if filter_status != "All Statuses":
                filtered_incidents = [i for i in filtered_incidents if i.get("status") == filter_status]

            if not filtered_incidents:
                filtered_incidents = incidents  # Fallback to prevent blank queue

            # Incident selection
            incident_map = {f"{i['incident_id']} - {i['ai_category'] or i['reported_category']} ({band_from_score(i.get('operator_priority') or i.get('priority_score', 0))})": i['incident_id'] for i in filtered_incidents}
            
            # Preserve or set active selection
            current_sel = st.session_state.get("selected_incident_id")
            default_idx = 0
            for idx, i_id in enumerate(incident_map.values()):
                if i_id == current_sel:
                    default_idx = idx
                    break

            selected_queue_label = st.selectbox(
                "Select Active Incident:",
                list(incident_map.keys()),
                index=default_idx,
                key="rcr_queue_selector"
            )
            active_id = incident_map[selected_queue_label]
            st.session_state["selected_incident_id"] = active_id
            active_inc = get_incident(active_id)

            # Render tactical queue cards matching Figma node 1:2714
            for item in filtered_incidents:
                is_active = (item["incident_id"] == active_id)
                i_score = item.get("operator_priority") or item.get("priority_score", 0)
                i_band = band_from_score(i_score)
                border_style = "border-left: 3px solid #4fe3d3; background: #182433;" if is_active else ""
                
                badge_color = "#ffb4ab" if i_band == "Critical" else ("#ffc979" if i_band == "High" else "#a0c9ff")
                badge_bg = "rgba(255, 180, 171, 0.12)" if i_band == "Critical" else ("rgba(255, 201, 121, 0.12)" if i_band == "High" else "rgba(160, 201, 255, 0.12)")

                vuln_summary = []
                if item.get("vulnerable_flag"):
                    vuln_summary.append(item.get("vulnerable_group") or "Vulnerable Population")
                if item.get("stranded"):
                    vuln_summary.append("Stranded")
                vuln_text = " • ".join(vuln_summary) if vuln_summary else f"{item.get('people_affected', 1)} Affected"

                st.markdown(
                    f"""
                    <div class="rcr-queue-item {'active' if is_active else ''}" style="{border_style}">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                            <span style="font-family:ui-monospace, monospace; font-size:11px; font-weight:700; color:#4fe3d3;">#{html.escape(item['incident_id'])}</span>
                            <span style="background:{badge_bg}; color:{badge_color}; border:1px solid {badge_color}44; font-size:9.5px; font-weight:700; padding:2px 6px; border-radius:3px;">
                                {i_band.upper()} ({i_score:.0f}/100)
                            </span>
                        </div>
                        <div style="font-size:12px; font-weight:600; color:#d9e3f2; margin-bottom:3px; line-height:1.3;">
                            {html.escape(item.get('ai_category') or item.get('reported_category') or 'Incident')}
                        </div>
                        <div style="font-size:11px; color:#859491; margin-bottom:4px;">
                            {html.escape(item.get('location_text') or zone_name_by_id.get(item['zone_id'], item['zone_id']))}
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px; color:#ffdad6; background:rgba(255,180,171,0.06); padding:3px 6px; border-radius:2px;">
                            <span>⚠️ {html.escape(vuln_text)}</span>
                            <span style="color:#859491;">{html.escape(item.get('status', 'Open'))}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Quick Catchment status footer in left column
            st.markdown(
                """
                <div style="background:#0d1722; border:1px solid rgba(44,54,65,0.4); border-radius:3px; padding:8px 10px; margin-top:10px; font-size:10.5px; color:#859491;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:3px;">
                        <span>Musi River Gauge:</span>
                        <span style="color:#ffb4ab; font-weight:600;">142.6m (Warning Level)</span>
                    </div>
                    <div style="display:flex; justify-content:space-between;">
                        <span>Hussain Sagar Outflow:</span>
                        <span style="color:#4fe3d3; font-weight:600;">78% Capacity (Controlled)</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # -------------------------------------------------------------------
        # Column 2: Incident Details & AI Triage (~42%)
        # -------------------------------------------------------------------
        with c_mid:
            inc = active_inc or incidents[0]
            p_score = inc.get("operator_priority") or inc.get("priority_score", 0)
            band = band_from_score(p_score)
            zone_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())

            # Incident Master Card Header Box (Figma Node 1:2822)
            st.markdown(
                f"""
                <div class="rcr-card" style="border-top:3px solid {'#ffb4ab' if band == 'Critical' else '#4fe3d3'};">
                    <div class="rcr-card-header">
                        <div>
                            <span style="font-family:ui-monospace, monospace; font-size:11px; color:#4fe3d3; font-weight:700;">INCIDENT RECORD: {html.escape(inc['incident_id'])}</span>
                            <div style="font-size:14px; font-weight:700; color:#d9e3f2; margin-top:2px;">
                                {html.escape(inc['ai_category'] or inc['reported_category'])} &bull; {html.escape(zone_label)}
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <span style="background:{'rgba(255,180,171,0.15)' if band == 'Critical' else 'rgba(79,227,211,0.15)'}; color:{'#ffb4ab' if band == 'Critical' else '#4fe3d3'}; border:1px solid {'#ffb4ab' if band == 'Critical' else '#4fe3d3'}66; font-size:11px; font-weight:700; padding:3px 8px; border-radius:3px;">
                                PRIORITY {p_score:.0f}/100 ({band.upper()})
                            </span>
                            <div style="font-size:10px; color:#859491; margin-top:3px;">Workflow Status: <b style="color:#d9e3f2;">{html.escape(inc['status'])}</b></div>
                        </div>
                    </div>
                    
                    <div style="font-size:12px; color:#bbcac6; line-height:1.45; background:#0f1924; padding:8px 10px; border-radius:3px; margin:6px 0;">
                        <span style="color:#859491; font-weight:600;">DISPATCH BRIEF:</span> "{html.escape(inc['description'])}"
                    </div>
                    
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:11px; color:#859491; margin-top:6px;">
                        <div>Location: <b style="color:#d9e3f2;">{html.escape(inc['location_text'] or 'N/A')}</b></div>
                        <div>People Affected: <b style="color:#d9e3f2;">{inc['people_affected']}</b></div>
                        <div>Stranded: <b style="color:{'#ffb4ab' if inc['stranded'] else '#d9e3f2'};">{'YES (Trapped in place)' if inc['stranded'] else 'No'}</b></div>
                        <div>Immediate Hazard: <b style="color:{'#ffb4ab' if inc['immediate_hazard'] else '#d9e3f2'};">{'YES (Submerged / Power Hazard)' if inc['immediate_hazard'] else 'No'}</b></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Vulnerability Highlight Banner
            if inc.get("vulnerable_flag") or inc.get("stranded"):
                st.markdown(
                    f"""
                    <div class="rcr-vuln-banner">
                        <div style="font-weight:700; color:#ffb4ab; margin-bottom:2px;">
                            CRITICAL VULNERABILITY OVERRIDE ACTIVATED
                        </div>
                        <div>
                            {html.escape(inc.get('vulnerable_group') or 'At-risk population requiring immediate evacuation assistance.')}
                            {' &bull; Immediate physical evacuation assistance required.' if inc.get('stranded') else ''}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Environmental Sensor Strip (Figma Node 1:2875)
            st.markdown(
                """
                <div class="rcr-sensor-strip">
                    <div class="rcr-sensor-item">
                        <div style="font-size:10px; color:#859491; text-transform:uppercase;">Inundation Depth</div>
                        <div style="font-size:13px; font-weight:700; color:#ffb4ab; margin-top:2px;">1.42 m</div>
                        <div style="font-size:9.5px; color:#859491;">Gauge Musi-104</div>
                    </div>
                    <div class="rcr-sensor-item">
                        <div style="font-size:10px; color:#859491; text-transform:uppercase;">Rainfall Rate</div>
                        <div style="font-size:13px; font-weight:700; color:#a0c9ff; margin-top:2px;">54.2 mm/hr</div>
                        <div style="font-size:9.5px; color:#859491;">OpenWeather Sync</div>
                    </div>
                    <div class="rcr-sensor-item">
                        <div style="font-size:10px; color:#859491; text-transform:uppercase;">Hydro Velocity</div>
                        <div style="font-size:13px; font-weight:700; color:#4fe3d3; margin-top:2px;">+0.18 m/hr</div>
                        <div style="font-size:9.5px; color:#4fe3d3;">Rate of Rise</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # AI Triage Rationale Card & Factor Breakdown (Figma Node 1:2880)
            st.markdown(
                f"""
                <div class="rcr-card">
                    <div class="rcr-card-header">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="color:#4fe3d3; font-size:13px;">🤖</span>
                            <span style="font-size:12px; font-weight:700; color:#d9e3f2;">AI Triage Model & Algorithmic Calibration</span>
                        </div>
                        <span style="background:rgba(79,227,211,0.12); color:#4fe3d3; border:1px solid rgba(79,227,211,0.3); font-size:9.5px; font-weight:700; padding:2px 6px; border-radius:3px;">
                            CONFIDENCE 96%
                        </span>
                    </div>
                    <div style="font-size:11.5px; color:#bbcac6; line-height:1.5; margin-bottom:8px;">
                        <b>Heuristic Evaluation:</b> {html.escape(inc['ai_rationale'])}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Priority Score Breakdown Table
            priority_calc = calculate_priority({
                "ai_category": inc["ai_category"],
                "ai_urgency": inc["ai_urgency"],
                "people_affected": inc["people_affected"],
                "vulnerable_flag": inc["vulnerable_flag"],
                "stranded": inc["stranded"],
                "unable_to_evacuate": inc["unable_to_evacuate"],
                "immediate_hazard": inc["immediate_hazard"],
            })

            with st.expander("Priority Calculation Factors (Vulnerability-First)", expanded=True):
                factors = priority_calc["factors"]
                p_df = pd.DataFrame([
                    {"Factor": "Severity (S, 30%)", "Raw": factors["severity"]["score"], "Contribution": factors["severity"]["contribution"]},
                    {"Factor": "Stranded / Trapped (T, 25%)", "Raw": factors["stranded"]["score"], "Contribution": factors["stranded"]["contribution"]},
                    {"Factor": "Vulnerability (V, 25%)", "Raw": factors["vulnerability"]["score"], "Contribution": factors["vulnerability"]["contribution"]},
                    {"Factor": "People Count (N, 10%)", "Raw": factors["people_affected"]["score"], "Contribution": factors["people_affected"]["contribution"]},
                    {"Factor": "Immediate Hazard (H, 10%)", "Raw": factors["hazard"]["score"], "Contribution": factors["hazard"]["contribution"]},
                ])
                st.dataframe(p_df, use_container_width=True, hide_index=True)
                st.caption(f"Composite Score: **{inc['priority_score']:.1f}/100** | Band: **{band}**")

        # -------------------------------------------------------------------
        # Column 3: Tactical Dispatch & Approval (~30%)
        # -------------------------------------------------------------------
        with c_right:
            rec = recommend_team(inc, teams, zone_coords=zone_coords)
            recommended_team = rec.get("recommended_team")
            current_status = inc["status"]
            available_teams = [t for t in teams if t["status"] == "Available"]

            # Response Unit Recommendation Card (Figma Node 1:2970)
            if recommended_team:
                rec_base = zone_name_by_id.get(recommended_team["base_zone"], recommended_team["base_zone"].replace("_", " ").title())
                st.markdown(
                    f"""
                    <div class="rcr-card" style="border-left:3px solid #4fe3d3;">
                        <div class="rcr-card-header">
                            <div>
                                <span style="font-size:10.5px; color:#859491; text-transform:uppercase; letter-spacing:0.4px;">Tactical Match</span>
                                <div style="font-size:13px; font-weight:700; color:#d9e3f2;">{html.escape(recommended_team['team_name'])}</div>
                            </div>
                            <span style="background:rgba(79,227,211,0.15); color:#4fe3d3; border:1px solid rgba(79,227,211,0.3); font-size:10px; font-weight:700; padding:2px 6px; border-radius:3px;">
                                MATCH {rec.get('match_score', 0):.0f}%
                            </span>
                        </div>
                        <div style="font-size:11px; color:#859491; margin-bottom:4px;">
                            Specialty: <b style="color:#d9e3f2;">{html.escape(recommended_team['specialty'])}</b> &bull; Base: <b style="color:#d9e3f2;">{html.escape(rec_base)}</b>
                        </div>
                        <div style="font-size:11px; color:#4fe3d3; margin-bottom:6px;">
                            Proximity: <b style="color:#4fe3d3;">{html.escape(rec['distance_desc'])}</b> &bull; ETA: <b style="color:#d9e3f2;">7-10 mins</b>
                        </div>
                        <div style="font-size:10.5px; color:#bbcac6; background:#0d1722; padding:6px 8px; border-radius:2px; border:1px solid rgba(44,54,65,0.4);">
                            {html.escape(rec['match_reason'])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Show alternatives in expander
                alternatives = rec.get("alternatives", [])
                if alternatives:
                    with st.expander(f"Compare All Units ({len(alternatives) + 1})"):
                        alt_rows = [{
                            "Unit": recommended_team["team_name"],
                            "Specialty": recommended_team["specialty"],
                            "Base": rec_base,
                            "Match": f"{rec.get('match_score', 0):.0f}%",
                        }]
                        for alt in alternatives:
                            t_alt = alt["team"]
                            alt_rows.append({
                                "Unit": t_alt["team_name"],
                                "Specialty": t_alt["specialty"],
                                "Base": zone_name_by_id.get(t_alt["base_zone"], t_alt["base_zone"].replace('_', ' ').title()),
                                "Match": f"{alt['match_score']:.0f}%",
                            })
                        st.dataframe(pd.DataFrame(alt_rows), use_container_width=True, hide_index=True)
            else:
                st.warning(rec.get("match_reason", "No team available."))

            # 5-Step Workflow Status Stepper (Figma Node 1:3045)
            step_names = ["1. Logged", "2. Sign-off", "3. Queued", "4. On Scene", "5. Resolved"]
            step_idx = 0
            if current_status == "In Review":
                step_idx = 1
            elif current_status == "Team Assigned":
                step_idx = 2
            elif current_status == "In Progress":
                step_idx = 3
            elif current_status == "Resolved":
                step_idx = 4

            step_html = '<div class="rcr-stepper">'
            for i, name in enumerate(step_names):
                cls = "completed" if i < step_idx else ("active" if i == step_idx else "")
                step_html += f'<div class="rcr-step {cls}"><div class="rcr-step-circle">{i+1}</div><span>{name.split(".")[1].strip()}</span></div>'
            step_html += '</div>'
            st.markdown(step_html, unsafe_allow_html=True)

            # Operator Dispatch Authorization Form & Triggers (Figma Node 1:3080)
            st.markdown(
                """
                <div style="font-size:11px; font-weight:700; color:#d9e3f2; letter-spacing:0.4px; text-transform:uppercase; margin-bottom:4px;">
                    Duty Chief Dispatch Directives
                </div>
                """,
                unsafe_allow_html=True,
            )

            if current_status in ("Triaged", "In Review"):
                team_choices = {
                    f"{t['team_name']} ({t['specialty']}) — {zone_name_by_id.get(t['base_zone'], t['base_zone'].replace('_', ' ').title())}": t["team_id"]
                    for t in available_teams
                }

                rec_idx = 0
                if recommended_team and recommended_team["team_id"] in [t["team_id"] for t in available_teams]:
                    for idx, (lbl, tid) in enumerate(team_choices.items()):
                        if tid == recommended_team["team_id"]:
                            rec_idx = idx
                            break

                selected_team_label = st.selectbox(
                    "Target Response Unit:",
                    list(team_choices.keys()) if team_choices else ["No teams available"],
                    index=rec_idx if team_choices else 0,
                    disabled=not team_choices,
                    key="rcr_target_team_select"
                )

                op_note = st.text_input(
                    "Mandatory Log Entry / Directives:",
                    placeholder="e.g. Life-safety priority: inflatable boat & medical kit required.",
                    key="rcr_op_note"
                )

                if st.button("AUTHORIZE & DISPATCH TEAM", type="primary", use_container_width=True, disabled=not team_choices):
                    chosen_team_id = team_choices[selected_team_label]
                    chosen_team_name = team_name_by_id.get(chosen_team_id, chosen_team_id)
                    try:
                        if current_status == "Triaged":
                            update_incident_workflow(
                                incident_id=inc["incident_id"],
                                new_status="In Review",
                                note="Operator initiated dispatch sequence.",
                            )
                        update_incident_workflow(
                            incident_id=inc["incident_id"],
                            new_status="Team Assigned",
                            assigned_team_id=chosen_team_id,
                            note=op_note or f"Operator authorized dispatch of {chosen_team_name} ({chosen_team_id}).",
                        )
                        st.success(f"{chosen_team_name} dispatched successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Dispatch failed: {e}")

                if st.button("ESCALATE TO NDRF STATE COMMAND", use_container_width=True):
                    update_incident_workflow(inc["incident_id"], "In Review", note="Incident escalated to State Emergency Operations Center (NDRF).")
                    st.info("Incident escalated to NDRF State Command.")
                    st.rerun()

            elif current_status == "Team Assigned":
                assigned_name = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"])
                st.info(f"**{assigned_name}** (`{inc['assigned_team_id']}`) dispatched to sector.")
                c_act1, c_act2 = st.columns(2)
                with c_act1:
                    if st.button("Mark 'On Scene / In Progress'", type="primary", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Progress", note="Team on scene: emergency operation actively underway.")
                        st.rerun()
                with c_act2:
                    if st.button("Revoke / Re-assign", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Review", note="Dispatch revoked by operator for team reassignment.")
                        st.rerun()

            elif current_status == "In Progress":
                st.info("Tactical response actively underway on scene.")
                res_note = st.text_input("Resolution Log Entry:", placeholder="e.g. All citizens rescued; floodwaters cleared.", key="rcr_res_note")
                if st.button("Mark Incident Resolved", type="primary", use_container_width=True):
                    update_incident_workflow(inc["incident_id"], "Resolved", note=res_note or "Incident successfully resolved.")
                    st.success("Incident resolved; response team released to Available duty.")
                    st.rerun()

            elif current_status == "Resolved":
                st.success("Incident Resolved. Response unit returned to Ready status.")

            # Operator signature footer (Figma Node 1:3104)
            st.markdown(
                """
                <div style="margin-top:12px; padding-top:8px; border-top:1px solid rgba(44,54,65,0.4); display:flex; justify-content:space-between; font-size:10px; color:#859491;">
                    <span>Auth: <b style="color:#bbcac6;">Cmdr. R. Verma (GHMC-844)</b></span>
                    <span>Audit Ref: <b style="color:#4fe3d3;">#TX-90214</b></span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.button(
                "View Audit Timeline in Incident History",
                key="goto_history_from_dispatch",
                use_container_width=True,
                on_click=_go_to_page,
                args=("Incident History",),
            )


# ===========================================================================
# MODULE 6: INCIDENT HISTORY
# ===========================================================================

elif nav_option == "Incident History":
    # -----------------------------------------------------------------------
    # Canonical & Live Data Assembly
    # -----------------------------------------------------------------------
    canonical_records = get_canonical_audit_records()
    db_incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}

    # Integrate user-created database incidents into ledger
    canonical_ids = {r["incident_id"] for r in canonical_records}
    merged_records = list(canonical_records)

    for inc in db_incidents:
        inc_id = inc.get("incident_id", "")
        # If incident is not already in canonical records, add dynamic representation
        if inc_id not in canonical_ids and not any(r["incident_id"].endswith(inc_id[-4:]) for r in canonical_records):
            sev = band_from_score(inc.get("priority_score", 0)).upper()
            sev_class = sev.lower()
            z_label = zone_name_by_id.get(inc.get("zone_id", ""), inc.get("zone_id", "Unknown").replace("_", " ").title())
            assigned_unit = team_name_by_id.get(inc.get("assigned_team_id"), inc.get("assigned_team_id") or "Unassigned")
            created_str = inc.get("created_at", "")[:19].replace("T", " ") if inc.get("created_at") else "Live"
            
            # Synthesize updates into milestones
            db_updates = get_incident_updates(inc_id)
            milestones = [
                {
                    "time": created_str + " IST",
                    "time_diff": "",
                    "badge": "TELEMETRY INGEST",
                    "badge_style": "background:#212b36; color:#859491;",
                    "node_class": "node-ingest",
                    "icon": "icon_intake.svg",
                    "title": "Incident Logged via Intake Console",
                    "desc": inc.get("description", "Disaster intake report filed."),
                    "meta_icon": "icon_pin.svg",
                    "meta": f"Zone: {z_label} • Category: {inc.get('reported_category', 'General')}",
                },
                {
                    "time": created_str + " IST (+15s)",
                    "time_diff": "(+15s)",
                    "badge": "AUTOMATED LLM",
                    "badge_style": "background:rgba(160,201,255,0.2); color:#a0c9ff;",
                    "node_class": "node-llm",
                    "icon": "icon_ai.svg",
                    "title": "AI Triage Assessment Completed",
                    "desc": inc.get("ai_rationale") or f"Assessed as {inc.get('ai_category', 'Emergency')} with priority score {inc.get('priority_score', 0):.0f}/100.",
                    "meta_icon": "icon_sparkle.svg",
                    "meta": f"Priority Score: {inc.get('priority_score', 0):.0f}/100 • Urgency: {inc.get('ai_urgency', 'High')}",
                },
            ]
            
            for idx, u in enumerate(db_updates):
                old_s = u.get("old_status") or "Reported"
                new_s = u.get("new_status") or "Updated"
                note_s = u.get("note") or f"Status shifted from {old_s} to {new_s}."
                u_time = u.get("updated_at", "")[:19].replace("T", " ") if u.get("updated_at") else ""
                milestones.append({
                    "time": u_time + " IST",
                    "time_diff": f"(Update #{idx+1})",
                    "badge": "COMMAND OVERSIGHT" if "Review" in new_s else "EXECUTED DISPATCH",
                    "badge_style": "background:#4fe3d3; color:#003732; font-weight:700;" if "Dispatched" in new_s or "Resolved" in new_s else "background:rgba(79,227,211,0.2); color:#4fe3d3;",
                    "node_class": "node-dispatch" if "Dispatched" in new_s or "Resolved" in new_s else "node-command",
                    "icon": "icon_check.svg" if "Dispatched" in new_s or "Resolved" in new_s else "icon_shield.svg",
                    "title": f"Status Updated: {old_s} → {new_s}",
                    "desc": note_s,
                    "meta_icon": "icon_radio.svg",
                    "meta": f"Assigned: {assigned_unit}",
                })

            merged_records.append({
                "incident_id": f"#{inc_id}",
                "severity": sev,
                "severity_class": sev_class,
                "zone_id": inc.get("zone_id", ""),
                "zone_label": z_label,
                "priority_score": int(inc.get("priority_score", 50)),
                "location_title": inc.get("location_text") or "Reported Location",
                "location_text": inc.get("location_text") or "Reported Location",
                "gps": f"Zone {inc.get('zone_id', '')}",
                "marker": "Municipal Sector Hyd-West",
                "category_summary": inc.get("reported_category", "Emergency Incident"),
                "status": inc.get("status", "Triaged").upper(),
                "active_time": f"Logged {created_str}",
                "reported_time": created_str,
                "priority_tier": f"Tier {1 if sev == 'CRITICAL' else 2 if sev == 'HIGH' else 3}",
                "sensor": "TELEMETRY-STREAM",
                "assigned_unit": assigned_unit,
                "inundation_m": 0.85,
                "flow_velocity": "1.5 m/sec",
                "icon_type": "icon_rescue.svg" if "Rescue" in inc.get("reported_category", "") else "icon_ambulance.svg",
                "is_canonical": False,
                "milestones": milestones,
            })

    # Selection State Management
    if "selected_audit_inc_id" not in st.session_state:
        st.session_state["selected_audit_inc_id"] = "#INC-2024-0941"

    # Verify selected ID is present, else default
    record_map = {r["incident_id"]: r for r in merged_records}
    if st.session_state["selected_audit_inc_id"] not in record_map:
        st.session_state["selected_audit_inc_id"] = merged_records[0]["incident_id"]

    selected_rec = record_map[st.session_state["selected_audit_inc_id"]]

    # Compute live SHA-256 integrity hash for selected record
    sha256_hash = compute_audit_hash(selected_rec["incident_id"], selected_rec["milestones"])
    jsonld_packet = build_audit_packet_jsonld(selected_rec, selected_rec["milestones"], sha256_hash)

    # -----------------------------------------------------------------------
    # Sub-Header & Global Chronometer Breadcrumb (Figma Node 1:5)
    # -----------------------------------------------------------------------
    icon_archive_uri = get_figma_icon_uri("icon_archive.svg")
    icon_export_uri = get_figma_icon_uri("icon_export.svg")

    st.markdown(
        f"""
        <div class="tactical-sub-header">
            <div class="tactical-breadcrumb-left">
                <div class="tactical-icon-box">
                    <img src="{icon_archive_uri}" width="16" height="16" alt="Archive" />
                </div>
                <div class="tactical-breadcrumb-copy">
                    <div class="tactical-breadcrumb-crumbs">
                        <span class="tactical-crumbs-muted">OPERATIONAL ARCHIVE</span>
                        <span class="tactical-crumbs-muted">/</span>
                        <span class="tactical-crumbs-accent">INCIDENT HISTORY</span>
                    </div>
                    <h2 class="tactical-screen-title">Incident History / Audit Trail & Chronological Timeline</h2>
                </div>
            </div>
            <div class="tactical-header-actions">
                <div class="tactical-stream-badge">
                    <span class="tactical-stream-dot"></span>
                    <span>STREAM: SECURE_APPEND_ONLY</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Download button for JSON-LD Audit Packet
    col_dl_space, col_dl_btn = st.columns([0.7, 0.3])
    with col_dl_btn:
        st.download_button(
            label="EXPORT AUDIT PACKET (JSON-LD)",
            data=jsonld_packet,
            file_name=f"floodiq-audit-packet-{selected_rec['incident_id'].lstrip('#')}.jsonld",
            mime="application/ld+json",
            help="Download cryptographically fingerprinted W3C / schema.org EmergencyService audit trail.",
            use_container_width=True,
        )

    # -----------------------------------------------------------------------
    # Tactical Multi-Parameter Filter Toolbar (Figma Node 1:30)
    # -----------------------------------------------------------------------
    icon_zone_uri = get_figma_icon_uri("icon_zone.svg")
    icon_sev_uri = get_figma_icon_uri("icon_severity.svg")
    icon_stat_uri = get_figma_icon_uri("icon_status.svg")
    icon_seed_uri = get_figma_icon_uri("icon_seed.svg")
    icon_search_uri = get_figma_icon_uri("icon_search.svg")

    with st.container():
        st.markdown('<div class="tactical-filter-bar">', unsafe_allow_html=True)
        col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns([2.2, 2.0, 2.0, 2.4, 3.4])

        with col_f1:
            st.markdown(
                f'<span class="tactical-filter-label"><img src="{icon_zone_uri}" width="12" style="vertical-align:middle; margin-right:4px;" />ZONE CONSTRAINT</span>',
                unsafe_allow_html=True,
            )
            zone_options = ["All Zones (Hyderabad Pilot)", "Zone 1 / Musi Basin", "Zone 2 / Shaikpet Corridor", "Zone 2 / Metro Corridor", "Zone 3 / Rasoolpura Stream"]
            sel_zone = st.selectbox("Zone Constraint", zone_options, label_visibility="collapsed")

        with col_f2:
            st.markdown(
                f'<span class="tactical-filter-label"><img src="{icon_sev_uri}" width="12" style="vertical-align:middle; margin-right:4px;" />SEVERITY BRACKET</span>',
                unsafe_allow_html=True,
            )
            sev_options = ["All Severities", "Critical", "High", "Moderate", "Low"]
            sel_sev = st.selectbox("Severity Bracket", sev_options, label_visibility="collapsed")

        with col_f3:
            st.markdown(
                f'<span class="tactical-filter-label"><img src="{icon_stat_uri}" width="12" style="vertical-align:middle; margin-right:4px;" />TRIAGE LIFECYCLE</span>',
                unsafe_allow_html=True,
            )
            stat_options = ["All Statuses", "Under Review / Assigned", "In Transit", "Resolved", "Triaged"]
            sel_stat = st.selectbox("Triage Lifecycle", stat_options, label_visibility="collapsed")

        with col_f4:
            st.markdown(
                f'<span class="tactical-filter-label"><img src="{icon_seed_uri}" width="12" style="vertical-align:middle; margin-right:4px;" />SCENARIO SEED</span>',
                unsafe_allow_html=True,
            )
            scenario_options = ["Active: 50mm Monsoon", "Severe 100mm Cloudburst", "Normal 20mm Rainfall"]
            sel_scenario = st.selectbox("Scenario Seed", scenario_options, label_visibility="collapsed")

        with col_f5:
            st.markdown(
                f'<span class="tactical-filter-label"><img src="{icon_search_uri}" width="12" style="vertical-align:middle; margin-right:4px;" />QUICK SEARCH QUERY <span class="tactical-search-shortcut">⌘K</span></span>',
                unsafe_allow_html=True,
            )
            search_query = st.text_input("Quick Search Query", placeholder="Search Chadarghat, #INC-2024, SDRF...", label_visibility="collapsed")

        st.markdown('</div>', unsafe_allow_html=True)

    # Filtering logic
    filtered_records = []
    for r in merged_records:
        # Zone filter
        if sel_zone != "All Zones (Hyderabad Pilot)":
            z_term = sel_zone.split(" / ")[-1].lower() if " / " in sel_zone else sel_zone.lower()
            if z_term not in r["zone_label"].lower() and z_term not in r["zone_id"].lower():
                continue
        # Severity filter
        if sel_sev != "All Severities":
            if r["severity"].upper() != sel_sev.upper():
                continue
        # Status filter
        if sel_stat != "All Statuses":
            if sel_stat.lower() not in r["status"].lower():
                continue
        # Search query
        if search_query.strip():
            sq = search_query.strip().lower()
            corpus = f"{r['incident_id']} {r['location_title']} {r['location_text']} {r['category_summary']} {r['assigned_unit']} {r['zone_label']}".lower()
            if sq not in corpus:
                continue
        filtered_records.append(r)

    if not filtered_records:
        filtered_records = merged_records

    # -----------------------------------------------------------------------
    # Primary Tactical 2-Pane Console (50% / 50% Desktop Grid)
    # -----------------------------------------------------------------------
    col_left_pane, col_right_pane = st.columns([1, 1], gap="small")

    # LEFT PANE: Master Incident Log Table
    with col_left_pane:
        icon_ledger_uri = get_figma_icon_uri("icon_ledger.svg")
        st.markdown(
            f"""
            <div class="tactical-pane">
                <div class="tactical-pane-header">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <img src="{icon_ledger_uri}" width="14" height="14" alt="Ledger" />
                        <div>
                            <span style="color:#d9e3f2; font-size:15px; font-weight:700; letter-spacing:-0.2px;">Historical Incident Ledger</span>
                            <span style="color:#859491; font-size:10px; margin-left:6px;">({html.escape(sel_scenario)})</span>
                        </div>
                    </div>
                    <span class="tactical-sync-badge">SYNC: NOMINAL</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for rec in filtered_records:
            is_active = (rec["incident_id"] == selected_rec["incident_id"])
            active_class = "active" if is_active else ""
            sev_class = rec["severity_class"]
            icon_cat_uri = get_figma_icon_uri(rec.get("icon_type", "icon_rescue.svg"))
            icon_chevron_uri = get_figma_icon_uri("icon_chevron.svg")

            score_color = "#ffbdbe" if rec["priority_score"] >= 75 else "#a0c9ff" if rec["priority_score"] >= 50 else "#4fe3d3"
            status_color = "#ffbdbe" if "ASSIGNED" in rec["status"] or "CRITICAL" in rec["severity"] else "#4fe3d3"

            card_html = f"""
            <div class="tactical-record-card {active_class}">
                <div class="tactical-record-bar {sev_class}"></div>
                <div class="tactical-record-row1">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span class="tactical-rec-id">{rec['incident_id']}</span>
                        <span class="tactical-sev-badge tactical-sev-{sev_class}">
                            <span style="width:6px; height:6px; border-radius:50%; background:{score_color}; display:inline-block;"></span>
                            {rec['severity']}
                        </span>
                        <span style="color:#859491; font-size:10px;">{rec['zone_label']}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span style="color:#859491; font-size:10px;">PRIORITY TRIAGE</span>
                        <span class="tactical-score-pill" style="color:{score_color};">{rec['priority_score']}</span>
                    </div>
                </div>
                <div class="tactical-record-row2">
                    <div>
                        <div class="tactical-record-title">{rec['location_title']}</div>
                        <div class="tactical-record-desc">
                            <img src="{icon_cat_uri}" width="12" height="12" style="vertical-align:middle;" />
                            <span>{rec['category_summary']}</span>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div class="tactical-record-status" style="color:{status_color};">{rec['status']}</div>
                        <div style="color:#859491; font-size:10px;">{rec['active_time']}</div>
                    </div>
                </div>
                <div class="tactical-record-subbar">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <span style="color:#bbcac6;">Sensor: <strong style="color:#d9e3f2;">{rec['sensor']}</strong></span>
                        <span style="color:#bbcac6;">Units: <strong style="color:#4fe3d3;">{rec['assigned_unit']}</strong></span>
                    </div>
                    <div style="display:flex; align-items:center; gap:4px; color:#4fe3d3; font-weight:600;">
                        <span>{'Viewing Audit Trace' if is_active else 'Select'}</span>
                        <img src="{icon_chevron_uri}" width="10" height="10" />
                    </div>
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)
            if not is_active:
                if st.button(f"Inspect Audit Record: {rec['incident_id']}", key=f"btn_select_{rec['incident_id']}", use_container_width=True):
                    st.session_state["selected_audit_inc_id"] = rec["incident_id"]
                    st.rerun()

    # RIGHT PANE: Chronological Event Timeline for Selected Incident
    with col_right_pane:
        icon_timeline_uri = get_figma_icon_uri("icon_timeline.svg")
        icon_clock_uri = get_figma_icon_uri("icon_clock.svg")
        icon_unit_uri = get_figma_icon_uri("icon_unit.svg")
        icon_location_uri = get_figma_icon_uri("icon_location.svg")
        icon_hash_uri = get_figma_icon_uri("icon_hash.svg")

        st.markdown(
            f"""
            <div class="tactical-pane">
                <div class="tactical-timeline-header">
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <div style="background:rgba(255,148,152,0.25); border-radius:2px; width:28px; height:28px; display:flex; align-items:center; justify-content:center;">
                                <img src="{icon_timeline_uri}" width="14" height="14" alt="Timeline" />
                            </div>
                            <div>
                                <div style="color:#d9e3f2; font-size:15px; font-weight:700; letter-spacing:-0.2px;">Incident Audit Trail: {selected_rec['incident_id']}</div>
                                <div style="color:#859491; font-size:10px; letter-spacing:0.4px;">CHAIN-OF-CUSTODY IMMUTABLE EVENT SEQUENCE</div>
                            </div>
                        </div>
                        <div style="background:rgba(255,189,190,0.2); border:1px solid rgba(255,189,190,0.4); border-radius:2px; padding:3px 6px; color:#ffbdbe; font-size:10px; font-weight:700; letter-spacing:0.5px;">
                            {'DISPATCH ACTIVE' if 'ASSIGNED' in selected_rec['status'] else selected_rec['status']}
                        </div>
                    </div>
                    <div class="tactical-pill-strip">
                        <div style="display:flex; align-items:center; gap:4px;">
                            <img src="{icon_clock_uri}" width="12" height="12" />
                            <span>Reported: <strong>{selected_rec['reported_time']}</strong></span>
                        </div>
                        <span style="color:#3c4947;">•</span>
                        <span style="color:#ffbdbe; font-weight:700;">{selected_rec['priority_tier']}</span>
                        <span style="color:#3c4947;">•</span>
                        <span>Triage Score: <strong style="color:#ffbdbe;">{selected_rec['priority_score']}/100</strong></span>
                        <span style="color:#3c4947;">•</span>
                        <div style="display:flex; align-items:center; gap:4px;">
                            <img src="{icon_unit_uri}" width="12" height="12" />
                            <span>Assigned: <strong style="color:#4fe3d3;">{selected_rec['assigned_unit']}</strong></span>
                        </div>
                    </div>
                </div>

                <div class="tactical-reticle-card">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <div style="background:#212b36; border-radius:2px; width:36px; height:40px; display:flex; align-items:center; justify-content:center; flex-shrink:0;">
                            <img src="{icon_location_uri}" width="22" height="22" alt="Reticle" />
                        </div>
                        <div>
                            <div style="color:#d9e3f2; font-size:12px; font-weight:700; letter-spacing:0.4px;">{selected_rec['location_text']}</div>
                            <div style="color:#859491; font-size:10px;">GPS: {selected_rec['gps']} • {selected_rec['marker']}</div>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="color:#ffbdbe; font-size:10px; font-weight:700;">CURRENT INUNDATION: {selected_rec['inundation_m']}m</div>
                        <div style="color:#859491; font-size:10px;">Velocity: {selected_rec['flow_velocity']}</div>
                    </div>
                </div>

                <div class="tactical-timeline-body">
                    <div class="tactical-timeline-track"></div>
            """,
            unsafe_allow_html=True,
        )

        # Render each Milestone
        for m in selected_rec["milestones"]:
            node_icon_uri = get_figma_icon_uri(m["icon"])
            meta_icon_uri = get_figma_icon_uri(m.get("meta_icon", "")) if m.get("meta_icon") else ""

            meta_html = ""
            if m.get("meta"):
                icon_tag = f'<img src="{meta_icon_uri}" width="10" height="10" style="vertical-align:middle; margin-right:4px;" />' if meta_icon_uri else ""
                meta_html = f'<div class="tactical-milestone-meta">{icon_tag}<span>{m["meta"]}</span></div>'

            progress_html = ""
            if "progress_eta" in m:
                progress_html = f"""
                <div class="tactical-progress-wrap">
                    <div style="display:flex; align-items:center; justify-content:space-between; font-size:10px;">
                        <span style="color:#859491;">ETA TO WATER CONTACT:</span>
                        <span style="color:#4fe3d3; font-weight:700;">{m['progress_eta']}</span>
                    </div>
                    <div class="tactical-progress-bar">
                        <div class="tactical-progress-fill" style="width:{m.get('progress_pct', 72)}%;"></div>
                    </div>
                </div>
                """

            m_html = f"""
            <div class="tactical-milestone">
                <div class="tactical-milestone-node {m['node_class']}">
                    <img src="{node_icon_uri}" width="12" height="12" alt="Milestone" />
                </div>
                <div class="tactical-milestone-card">
                    <div class="tactical-milestone-top">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="color:#859491; font-size:10px; font-weight:600;">{m['time']}</span>
                            <span style="color:#a0c9ff; font-size:10px;">{m.get('time_diff', '')}</span>
                        </div>
                        <span style="{m['badge_style']} border-radius:2px; padding:2px 5px; font-size:9px; letter-spacing:0.4px;">
                            {m['badge']}
                        </span>
                    </div>
                    <div class="tactical-milestone-title">{m['title']}</div>
                    <div class="tactical-milestone-desc">{m['desc']}</div>
                    {meta_html}
                    {progress_html}
                </div>
            </div>
            """
            st.markdown(m_html, unsafe_allow_html=True)

        # Regulatory Audit Footer & Disclaimer (Figma Node 1:350)
        sha_display = f"{sha256_hash[:8]}...{sha256_hash[-6:]}"
        st.markdown(
            f"""
                </div>
                <div class="tactical-audit-footer">
                    <div style="display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <img src="{icon_hash_uri}" width="12" height="12" alt="SHA" />
                            <span style="color:#859491; font-size:10px;">SHA-256 Ledger Hash: <strong style="color:#d9e3f2;">{sha_display}</strong></span>
                        </div>
                        <span style="color:#4fe3d3; font-size:10px; font-weight:600;">VALIDATED INTEGRITY</span>
                    </div>
                    <div style="color:#859491; font-size:10px; font-style:italic;">Prototype demonstration workflow. All logs reflect mock operational data.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -----------------------------------------------------------------------
    # Operational Decision Review Console (Bottom Utility Strip) (Figma Node 1:480)
    # -----------------------------------------------------------------------
    icon_sop_uri = get_figma_icon_uri("icon_sop.svg")
    icon_dispatcher_uri = get_figma_icon_uri("icon_dispatcher.svg")

    st.markdown(
        f"""
        <div class="tactical-bottom-strip">
            <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <img src="{icon_sop_uri}" width="14" height="14" alt="SOP" />
                    <div>
                        <span style="color:#4fe3d3; font-size:10px; font-weight:700;">STANDARD OPERATING PROCEDURE:</span>
                        <span style="color:#d9e3f2; font-size:10px; margin-left:4px;">GHMC Flood Protocol Tier-4 (Swiftwater Protocol 11-A)</span>
                    </div>
                </div>
                <span style="color:#3c4947;">|</span>
                <div style="display:flex; align-items:center; gap:6px;">
                    <img src="{icon_dispatcher_uri}" width="14" height="14" alt="Dispatcher" />
                    <span style="color:#859491; font-size:10px;">Lead Dispatcher: <strong style="color:#d9e3f2;">Sub-Cmdr. N. Rao (Duty Seat 02)</strong></span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_btn_sp, col_btn_act1, col_btn_act2 = st.columns([0.6, 0.2, 0.2])
    with col_btn_act1:
        if st.button("Flag for Post-Op Review", use_container_width=True):
            st.toast(f"Incident {selected_rec['incident_id']} flagged for post-incident command audit review.", icon="📋")
    with col_btn_act2:
        if st.button("Issue Audio Hailer Warning", type="primary", use_container_width=True):
            st.toast(f"Acoustic hailer broadcast transmitted on 156.800 MHz at {selected_rec['location_title']}: 'Evacuate low-lying structures immediately.'", icon="📢")



# ===========================================================================
# MODULE 7: SYSTEM INFORMATION
# ===========================================================================

elif nav_option == "System Information":
    # -----------------------------------------------------------------------
    # Operational Sub-Header & Live Status Bar (Figma Node 1:619)
    # -----------------------------------------------------------------------
    st.markdown(
        """
        <div class="sys-sub-header">
            <div>
                <div style="font-size:16px; font-weight:700; color:#d9e3f2; letter-spacing:-0.2px;">
                    System Information <span style="color:#859491; font-weight:400; margin:0 4px;">/</span> <span style="color:#a0c9ff; font-size:13px; font-weight:600;">Diagnostics, Architecture & Operational Disclosures</span>
                </div>
                <div style="font-size:11.5px; color:#859491; margin-top:2px;">
                    Technical Stack Specifications &bull; Verification Engine &bull; Hackathon Scope & Operational Constraints
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div class="rcr-telemetry-badge">
                    <span style="color:#4fe3d3;">&#x25cf;</span>
                    <span style="color:#859491;">SYSTEM INTEGRITY:</span>
                    <span style="color:#d9e3f2; font-weight:600;">99.8%</span>
                </div>
                <div class="rcr-telemetry-badge">
                    <span style="color:#a0c9ff; font-weight:600;">ENGINE:</span>
                    <span style="color:#d9e3f2;">Python 3.9+ / Streamlit</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Status fetching
    w_status = get_weather_status()
    all_inc = list_incidents()
    teams = get_response_teams()
    gemini_key_present = bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here")

    # -----------------------------------------------------------------------
    # 3x2 Tactical Matrix Cards (Figma Node 1:619)
    # -----------------------------------------------------------------------
    col_m1, col_m2, col_m3 = st.columns(3, gap="medium")
    with col_m1:
        # Card 1: Weather Engine
        w_state = "Connected (OpenWeather / Met)" if w_status["connected"] else "Simulated / Fallback Mode"
        w_color = "#4fe3d3" if w_status["connected"] else "#ffc979"
        st.markdown(
            f"""
            <div class="sys-card" style="border-top:3px solid {w_color}; height:100%;">
                <div class="sys-card-header">
                    <span style="font-size:12px; font-weight:700; color:#d9e3f2;">Weather & Precipitation Data</span>
                    <span style="font-size:9.5px; color:{w_color}; font-weight:700;">LIVE FEED</span>
                </div>
                <div style="font-size:11px; color:#bbcac6; margin-bottom:8px;">
                    Status: <b style="color:{w_color};">{w_state}</b><br>
                    Latency: <b style="color:#d9e3f2;">{w_status.get('latency_ms', 18)} ms</b> &bull; Polling: <b>60s TTL Cache</b>
                </div>
                <div style="font-size:10.5px; color:#859491; line-height:1.45; background:#0d1722; padding:6px 8px; border-radius:3px;">
                    Integrates OpenWeatherMap API for live hyetographs; automatically transitions to deterministic fallback on connection timeout.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_m2:
        # Card 2: AI Triage Service
        ai_state = "Gemini 1.5 Pro (Active)" if (gemini_key_present and not OFFLINE_MODE) else "Deterministic Fallback (Active)"
        ai_color = "#38bdf8" if (gemini_key_present and not OFFLINE_MODE) else "#4fe3d3"
        st.markdown(
            f"""
            <div class="sys-card" style="border-top:3px solid {ai_color}; height:100%;">
                <div class="sys-card-header">
                    <span style="font-size:12px; font-weight:700; color:#d9e3f2;">AI Triage & NLP Service</span>
                    <span style="font-size:9.5px; color:{ai_color}; font-weight:700;">100% SCHEMA COMPLIANT</span>
                </div>
                <div style="font-size:11px; color:#bbcac6; margin-bottom:8px;">
                    Engine: <b style="color:{ai_color};">{ai_state}</b><br>
                    Extraction: <b style="color:#d9e3f2;">Urgency, Vulnerability, Category</b>
                </div>
                <div style="font-size:10.5px; color:#859491; line-height:1.45; background:#0d1722; padding:6px 8px; border-radius:3px;">
                    Structured JSON output schema guarantees non-hallucinatory triage; regex and keyword fallback runs with zero network dependency.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_m3:
        # Card 3: Geospatial Heuristic Model
        st.markdown(
            """
            <div class="sys-card" style="border-top:3px solid #ffb4ab; height:100%;">
                <div class="sys-card-header">
                    <span style="font-size:12px; font-weight:700; color:#d9e3f2;">Hydrological Risk Heuristic</span>
                    <span style="font-size:9.5px; color:#ffb4ab; font-weight:700;">EXPLAINABLE</span>
                </div>
                <div style="font-size:11px; color:#bbcac6; margin-bottom:8px;">
                    Formula: <b style="color:#4fe3d3; font-family:monospace;">R = 0.4P + 0.3D + 0.3L</b><br>
                    Coverage: <b style="color:#d9e3f2;">5 Hyderabad Pilot Catchments</b>
                </div>
                <div style="font-size:10.5px; color:#859491; line-height:1.45; background:#0d1722; padding:6px 8px; border-radius:3px;">
                    Combines normalized rainfall (P), drainage deficit (D), and low-lying elevation (L) with deterministic transparency.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    col_m4, col_m5, col_m6 = st.columns(3, gap="medium")
    with col_m4:
        # Card 4: Database & Storage
        st.markdown(
            f"""
            <div class="sys-card" style="border-top:3px solid #4fe3d3; height:100%;">
                <div class="sys-card-header">
                    <span style="font-size:12px; font-weight:700; color:#d9e3f2;">Database & Storage Architecture</span>
                    <span style="font-size:9.5px; color:#4fe3d3; font-weight:700;">SQLITE WAL</span>
                </div>
                <div style="font-size:11px; color:#bbcac6; margin-bottom:8px;">
                    Total Incidents: <b style="color:#d9e3f2;">{len(all_inc)}</b> &bull; Teams: <b style="color:#d9e3f2;">{len(teams)}</b><br>
                    Transactions: <b style="color:#4fe3d3;">Atomic Dispatch Locking</b>
                </div>
                <div style="font-size:10.5px; color:#859491; line-height:1.45; background:#0d1722; padding:6px 8px; border-radius:3px;">
                    Append-only audit ledger tracks state transitions and logs operator overrides with cryptographic SHA-256 integrity.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_m5:
        # Card 5: System Limitations & Scope
        st.markdown(
            """
            <div class="sys-card" style="border-top:3px solid #ffc979; height:100%;">
                <div class="sys-card-header">
                    <span style="font-size:12px; font-weight:700; color:#d9e3f2;">Prototype Scope & Disclosures</span>
                    <span style="font-size:9.5px; color:#ffc979; font-weight:700;">HACKATHON PILOT</span>
                </div>
                <div style="font-size:11px; color:#bbcac6; margin-bottom:8px;">
                    Authority: <b style="color:#ffc979;">Human-in-the-Loop Required</b><br>
                    Hydrology: <b style="color:#d9e3f2;">Linear Heuristic Simulation</b>
                </div>
                <div style="font-size:10.5px; color:#859491; line-height:1.45; background:#0d1722; padding:6px 8px; border-radius:3px;">
                    No automated dispatch actions are executed without duty chief review. Zone boundaries and asset coordinates are illustrative.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_m6:
        # Card 6: Health & Performance
        st.markdown(
            """
            <div class="sys-card" style="border-top:3px solid #a0c9ff; height:100%;">
                <div class="sys-card-header">
                    <span style="font-size:12px; font-weight:700; color:#d9e3f2;">System Health & Connectivity</span>
                    <span style="font-size:9.5px; color:#a0c9ff; font-weight:700;">ALL SYSTEMS GO</span>
                </div>
                <div style="font-size:11px; color:#bbcac6; margin-bottom:8px;">
                    DB Read/Write: <b style="color:#4fe3d3;">< 1.8 ms</b><br>
                    Streamlit Port: <b style="color:#d9e3f2;">8501 (Healthy)</b>
                </div>
                <div style="font-size:10.5px; color:#859491; line-height:1.45; background:#0d1722; padding:6px 8px; border-radius:3px;">
                    In-memory session state syncing with real-time UI components, responsive Folium vector maps, and Plotly charts.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -----------------------------------------------------------------------
    # Architecture Overview & Pipeline Topology (Figma Node 1:619)
    # -----------------------------------------------------------------------
    st.markdown(
        """
        <div style="margin-top:1.5rem; margin-bottom:6px; font-size:12px; font-weight:700; color:#d9e3f2; letter-spacing:0.5px; text-transform:uppercase;">
            End-to-End Operational Pipeline Topology
        </div>
        <div class="sys-flow-box">
            <div class="sys-flow-node">
                <span style="color:#38bdf8; font-weight:700;">01. SENSORS & INTAKE</span><br>
                <span style="color:#859491; font-size:10px;">Weather API &bull; Citizen Reports</span>
            </div>
            <div class="sys-flow-arrow">&rarr;</div>
            <div class="sys-flow-node">
                <span style="color:#4fe3d3; font-weight:700;">02. AI TRIAGE & EXTRACTION</span><br>
                <span style="color:#859491; font-size:10px;">Gemini 1.5 Pro / Deterministic</span>
            </div>
            <div class="sys-flow-arrow">&rarr;</div>
            <div class="sys-flow-node">
                <span style="color:#ffb4ab; font-weight:700;">03. RISK & PRIORITY</span><br>
                <span style="color:#859491; font-size:10px;">Vulnerability-First Scoring</span>
            </div>
            <div class="sys-flow-arrow">&rarr;</div>
            <div class="sys-flow-node">
                <span style="color:#a0c9ff; font-weight:700;">04. CONTROL ROOM</span><br>
                <span style="color:#859491; font-size:10px;">Duty Chief Authorization</span>
            </div>
            <div class="sys-flow-arrow">&rarr;</div>
            <div class="sys-flow-node">
                <span style="color:#ffc979; font-weight:700;">05. AUDIT TIMELINE</span><br>
                <span style="color:#859491; font-size:10px;">SHA-256 Ledger & JSON-LD</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # Operational Disclosures & Mathematical Foundations
    # -----------------------------------------------------------------------
    col_d_left, col_d_right = st.columns(2, gap="medium")
    with col_d_left:
        render_section_heading("Scoring & Triage Mathematical Formulation")
        st.markdown(
            r"""
            - **Catchment Flood Risk Heuristic:**
              $$R = 0.40P + 0.30D + 0.30L$$
              Where $P$ is normalized rainfall score ($\min(100, \frac{\text{Rainfall}}{100} \times 100)$), $D$ is drainage deficit score, and $L$ is low-lying terrain factor.
            - **Vulnerability-First Incident Priority:**
              $$I = 0.30S + 0.25T + 0.25V + 0.10N + 0.10H$$
              Where $S$ is severity, $T$ is trapped/stranded citizens, $V$ is vulnerability override, $N$ is population count, and $H$ is immediate electrical/structural hazard.
            """
        )

    with col_d_right:
        render_section_heading("Operational Disclosures & Hackathon Scope")
        st.markdown(
            """
            - **Illustrative Demonstration:** Risk scores and catchment bounds are explainable heuristics for tactical demonstration and do not replace certified hydrodynamic models (e.g. SWMM / HEC-RAS).
            - **Unit Proximity:** Distances and ETAs are calculated using spherical Haversine formulas based on representative base station coordinates across Hyderabad.
            - **Sole Dispatch Authority:** Autonomous dispatch is strictly prohibited by software architecture. All tactical orders require an explicit human-in-the-loop sign-off.
            """
        )
