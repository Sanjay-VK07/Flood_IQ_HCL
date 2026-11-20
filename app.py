"""
FloodIQ — AI-Powered Urban Disaster Intelligence & Emergency Response Coordination Platform

Main Streamlit Application.
Implements the FloodIQ Command System dark tactical UI while preserving all
SQLite, Open-Meteo, risk engine, AI triage/fallback, and dispatch logic.
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
    APP_TITLE,
    GEMINI_API_KEY,
    INCIDENT_CATEGORIES,
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
    render_kpi_card,
    render_map_legend,
    render_page_header,
    render_section_heading,
    render_topbar,
)
from weather import get_rainfall_for_zones, get_weather_status

# ---------------------------------------------------------------------------
# Streamlit Page Setup & Custom CSS
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title=f"{APP_TITLE} | Tactical Flood Operations",
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


def _select_incident(incident_id: str) -> None:
    st.session_state["selected_incident_id"] = incident_id


def _go_to_page(page_name: str) -> None:
    st.session_state["nav_option"] = page_name


# ---------------------------------------------------------------------------
# Sidebar Navigation Rail & Rainfall Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div class="sb-brand">
            <div class="sb-brand-left">
                <div class="sb-brand-title">FloodIQ</div>
                <div class="sb-brand-sub">Tactical GIS</div>
            </div>
            <div class="sb-brand-tags">
                <span class="sb-tag">OPS</span>
                <span class="sb-tag">HYD</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-section-label">Tactical Command Units</div>', unsafe_allow_html=True)
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
                help="Moderate monsoon scenario (50 mm)",
                use_container_width=True,
                on_click=_set_rainfall_preset,
                args=(50.0,),
            )
        with col_p3:
            st.button(
                "100 mm",
                help="Cloudburst scenario (100 mm)",
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

    st.markdown(
        """
        <div class="sb-footer-card">
            <div class="sb-footer-row"><span><b>Hyderabad Pilot</b></span><span style="color:#21C7B7;">5 Zones</span></div>
            <div class="sb-footer-row"><span>Dispatch Gate</span><span style="color:#E8C45A;">Human Approval</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Shared Operational Context
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
    mode_label = "SIMULATION ACTIVE"
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
# Helper: Dark Tactical Folium Map Generator
# ---------------------------------------------------------------------------

def create_folium_map(
    zones_evaluated: list[dict],
    teams: list[dict] | None = None,
    incidents: list[dict] | None = None,
    highlight_zone_id: str | None = None,
) -> folium.Map:
    """Build dark-styled Hyderabad OpenStreetMap with zone circles, incidents, and teams."""
    m = folium.Map(
        location=[MAP_CENTER_LAT, MAP_CENTER_LNG],
        zoom_start=MAP_DEFAULT_ZOOM,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Apply dark-tactical invert filter solely to OSM tile layer (keeps markers/popups crisp)
    dark_css = folium.Element(
        """
        <style>
        .leaflet-container { background: #09131D !important; }
        .leaflet-tile-pane {
            filter: invert(100%) hue-rotate(180deg) brightness(88%) contrast(94%) saturate(65%);
        }
        </style>
        """
    )
    m.get_root().html.add_child(dark_css)

    risk_hex = {
        "Low": "#37C98A",
        "Moderate": "#E8C45A",
        "High": "#FF9B48",
        "Critical": "#FF5364",
    }

    # 1. Zone risk circles
    for z in zones_evaluated:
        color = risk_hex.get(z["risk_level"], "#21C7B7")
        is_highlighted = z["zone_id"] == highlight_zone_id

        popup_html = f"""
        <div style="font-family: Inter, sans-serif; min-width: 210px; font-size: 12px; color: #102530;">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 4px;">{html.escape(z['zone_name'])}</div>
            <div><b>Risk Score:</b> {z['risk_score']:.1f}/100 ({html.escape(z['risk_level'])})</div>
            <div><b>Rainfall:</b> {z['rainfall_mm']:.1f} mm ({html.escape(z['rainfall_source'])})</div>
            <div><b>Drainage Vuln.:</b> {z['drainage_score']}/100</div>
            <div><b>Low-Lying Score:</b> {z['low_lying_score']}/100</div>
            <div style="margin-top:4px; color:#5c707a; font-size:11px;">Illustrative scenario risk score</div>
        </div>
        """

        folium.CircleMarker(
            location=[z["latitude"], z["longitude"]],
            radius=22 if is_highlighted else 17,
            color="#FFFFFF" if is_highlighted else color,
            weight=3 if is_highlighted else 2,
            fill=True,
            fill_color=color,
            fill_opacity=0.38,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{z['zone_name']} — {z['risk_level']} ({z['risk_score']:.0f}/100)",
        ).add_to(m)

    # 2. Active incident markers
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


# Persistent Top Operational Bar
render_topbar(mode_label=mode_label, mode_tone=mode_tone, source_desc=source_desc, rain_label=rain_label)


# ===========================================================================
# PHASE 2: COMMAND CENTER
# ===========================================================================

if nav_option == "Command Center":
    incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}

    total_zones = len(evaluated_zones)
    elevated_zones = [z for z in evaluated_zones if z["risk_level"] in ("High", "Critical")]
    elevated_names = ", ".join(z["zone_name"] for z in elevated_zones[:3]) or "All zones nominal"
    open_incidents = [i for i in incidents if i["status"] != "Resolved"]
    critical_incidents = [i for i in open_incidents if i["priority_score"] >= 75]
    avg_priority = sum(i.get("priority_score", 0) for i in open_incidents) / max(len(open_incidents), 1)
    avail_teams = len([t for t in teams if t["status"] == "Available"])
    assigned_teams = len([t for t in teams if t["status"] == "Assigned"])

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card(
            label="Elevated-Risk Zones",
            value=f"{len(elevated_zones)}",
            suffix=f" / {total_zones} pilot zones",
            badge=("High / Critical", "high" if elevated_zones else "low"),
            foot=elevated_names,
        )
    with k2:
        render_kpi_card(
            label="Active Incidents",
            value=f"{len(open_incidents)}",
            badge=(f"{len(incidents) - len(open_incidents)} Resolved", "teal"),
            foot=f"Avg priority {avg_priority:.0f}/100" if open_incidents else "Queue clear",
        )
    with k3:
        top_crit_loc = (
            zone_name_by_id.get(critical_incidents[0]["zone_id"], critical_incidents[0]["zone_id"])
            if critical_incidents
            else "No critical alerts"
        )
        render_kpi_card(
            label="Critical Incidents",
            value=f"{len(critical_incidents)}",
            badge=("Action Urgent", "critical") if critical_incidents else ("Clear", "low"),
            foot=f"Priority sector: {top_crit_loc}",
            critical=bool(critical_incidents),
        )
    with k4:
        render_kpi_card(
            label="Available Response Teams",
            value=f"{avail_teams}",
            suffix=f" / {len(teams)}",
            badge=(f"{avail_teams} Standby", "low" if avail_teams else "critical"),
            foot=f"{assigned_teams} deployed (illustrative demo data)",
        )

    st.markdown("<div style='height:0.55rem'></div>", unsafe_allow_html=True)

    col_map, col_queue = st.columns([1.22, 0.78], gap="medium")

    with col_map:
        render_section_heading("Hyderabad Urban Catchment", f"5 Monitored Pilot Sectors · {source_desc}")
        fmap = create_folium_map(evaluated_zones, teams=teams, incidents=incidents)
        st_folium(fmap, height=430, use_container_width=True, returned_objects=[])
        render_map_legend([
            ("Critical (>=75)", "#FF5364"),
            ("High (50-74)", "#FF9B48"),
            ("Moderate (30-49)", "#E8C45A"),
            ("Low (<30)", "#37C98A"),
            ("Active Incident", "#ef4444"),
            ("Response Unit", "#21C7B7"),
        ])

    with col_queue:
        render_section_heading("Priority Incident Queue", f"{len(open_incidents)} Active · Vulnerability First")

        if not open_incidents:
            st.info("No active incidents in queue. All reports resolved.")
        else:
            for inc in open_incidents[:4]:
                p_score = inc.get("priority_score", 0)
                band = band_from_score(p_score)
                zone_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())
                assigned_label = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"]) if inc.get("assigned_team_id") else "Unassigned"
                cat_label = inc["ai_category"] or inc["reported_category"]

                vuln_strip = ""
                if inc.get("vulnerable_flag") or inc.get("stranded"):
                    parts = []
                    if inc.get("stranded"):
                        parts.append(f"{inc['people_affected']} Stranded")
                    if inc.get("vulnerable_flag"):
                        parts.append(f"Vulnerable: {inc.get('vulnerable_group', 'Reported')}")
                    vuln_strip = f'<div class="fiq-vuln-strip">{" · ".join(html.escape(p) for p in parts)}</div>'

                card_html = (
                    f'<div class="fiq-card fiq-card-{band.lower()}">'
                    f'<div class="fiq-card-top">'
                    f'<span class="fiq-card-id">#{html.escape(inc["incident_id"])} &nbsp; {badge_html(band, band.lower())}</span>'
                    f'<span style="font-size:0.84rem; font-weight:700; color:#F0F5F8;">{p_score:.0f}<span style="color:#6A8294; font-size:0.72rem;">/100</span></span>'
                    f'</div>'
                    f'<div class="fiq-card-title">{html.escape(cat_label)}</div>'
                    f'<div class="fiq-card-loc">{html.escape(zone_label)} &mdash; {html.escape(inc["location_text"] or "Location in report")}</div>'
                    f'{vuln_strip}'
                    f'<div class="fiq-card-meta">'
                    f'<span>Status: <b>{html.escape(inc["status"])}</b></span>'
                    f'<span>Unit: <b>{html.escape(assigned_label)}</b></span>'
                    f'</div>'
                    f'</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)
                st.button(
                    f"Review & Dispatch · {inc['incident_id']}",
                    key=f"quick_resp_{inc['incident_id']}",
                    type="primary" if band == "Critical" else "secondary",
                    use_container_width=True,
                    on_click=_go_to_control_room,
                    args=(inc["incident_id"],),
                )

    st.markdown("<div style='height:0.55rem'></div>", unsafe_allow_html=True)
    col_act, col_teams = st.columns([1.1, 0.9], gap="medium")

    with col_act:
        render_section_heading("Recent Incident Activity", "Chronological updates from SQLite audit log")
        recent_events = []
        for inc in incidents:
            for u in get_incident_updates(inc["incident_id"]):
                recent_events.append((u["updated_at"], inc["incident_id"], u["new_status"], u["note"]))
        recent_events.sort(key=lambda x: x[0], reverse=True)
        for ts, inc_id, status_s, note_s in recent_events[:4]:
            ts_short = ts[:19].replace("T", " ") + " UTC" if ts else ""
            st.markdown(
                f"""
                <div class="timeline-item">
                    <span class="timeline-time">{html.escape(ts_short)} &middot; {html.escape(inc_id)}</span><br>
                    <b style="color:#F0F5F8; font-size:0.8rem;">{html.escape(status_s or '')}</b>
                    <span style="color:#91A5B3; font-size:0.76rem;"> &mdash; {html.escape(note_s or '')}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_teams:
        render_section_heading("Response Team Availability", "Illustrative demonstration units")
        for t in teams:
            t_status = t.get("status", "Available")
            t_tone = "low" if t_status == "Available" else "critical"
            base_lbl = zone_name_by_id.get(t["base_zone"], t["base_zone"].replace("_", " ").title())
            st.markdown(
                f"""
                <div class="fiq-card" style="padding:0.48rem 0.72rem; margin-bottom:0.35rem;">
                    <div class="fiq-card-top">
                        <span style="font-size:0.8rem; font-weight:600; color:#F0F5F8;">{html.escape(t['team_name'])}</span>
                        {badge_html(t_status, t_tone)}
                    </div>
                    <div class="fiq-card-meta" style="margin-top:0.18rem;">
                        <span>{html.escape(t['specialty'])}</span>
                        <span>Base: <b>{html.escape(base_lbl)}</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ===========================================================================
# PHASE 3: FLOOD RISK INTELLIGENCE
# ===========================================================================

elif nav_option == "Flood Risk Intelligence":
    render_page_header(
        kicker="GEOSPATIAL CATCHMENT ANALYSIS",
        title="Flood Risk Intelligence",
        subtitle="Illustrative scenario risk scores combining rainfall input, drainage capacity, and terrain elevation — not a validated hydrological model.",
        right_badge=("ILLUSTRATIVE SCENARIO RISK SCORES", "moderate"),
    )

    col_m, col_r = st.columns([1.1, 0.9], gap="medium")

    with col_m:
        render_section_heading("Vector Catchment Risk Nodes", f"Source: {source_desc}")
        fmap = create_folium_map(evaluated_zones)
        st_folium(fmap, height=430, use_container_width=True, returned_objects=[])
        render_map_legend([
            ("Critical (>=75)", "#FF5364"),
            ("High (50-74)", "#FF9B48"),
            ("Moderate (30-49)", "#E8C45A"),
            ("Low (<30)", "#37C98A"),
        ])

    with col_r:
        render_section_heading("Heuristic Calculation Engine", "R = 0.40P + 0.30D + 0.30L")
        st.markdown(
            """
            <div class="fiq-card" style="border-left-color: var(--teal); padding:0.65rem 0.85rem;">
                <div style="font-size:0.78rem; color:#21C7B7; font-weight:600;">
                    Risk Score = (Rainfall &times; 0.40) + (Drainage Vuln. &times; 0.30) + (Low-Lying &times; 0.30)
                </div>
                <div style="font-size:0.73rem; color:#91A5B3; margin-top:0.25rem;">
                    Rainfall normalized to 150 mm ceiling. Bands: 0–29 Low, 30–49 Moderate, 50–74 High, 75–100 Critical.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        focus_zone = evaluated_zones[0]
        f_bd = focus_zone["score_breakdown"]
        f_band = focus_zone["risk_level"]
        render_section_heading("Highest-Risk Sector Breakdown", focus_zone["zone_name"])
        st.markdown(
            f"""
            <div class="fiq-card fiq-card-{f_band.lower()}">
                <div class="fiq-card-top">
                    <span class="fiq-card-title">{html.escape(focus_zone['zone_name'])}</span>
                    <span style="font-size:1.1rem; font-weight:700; color:#F0F5F8;">{focus_zone['risk_score']:.1f}<span style="font-size:0.75rem; color:#6A8294;">/100</span> &nbsp; {badge_html(f_band, f_band.lower())}</span>
                </div>
                <div class="fiq-card-meta" style="margin-top:0.35rem;">
                    <span>Rainfall (40%): <b>+{f_bd['rainfall']['contribution']:.1f}</b></span>
                    <span>Drainage (30%): <b>+{f_bd['drainage']['contribution']:.1f}</b></span>
                    <span>Low-Lying (30%): <b>+{f_bd['low_lying']['contribution']:.1f}</b></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
                "Rainfall (40%)": "#21C7B7",
                "Drainage (30%)": "#FF9B48",
                "Low-Lying (30%)": "#55A8FF",
            },
            template="plotly_dark",
            height=255,
        )
        fig.update_layout(
            margin=dict(l=12, r=12, t=36, b=10),
            paper_bgcolor="#122431",
            plot_bgcolor="#09131D",
            yaxis_title="Contribution",
            xaxis_title="",
            legend_title_text="",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    render_section_heading("5-Zone Comparison Matrix", "Sorted highest illustrative risk score first")
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
# PHASE 4: PREPAREDNESS
# ===========================================================================

elif nav_option == "Preparedness":
    render_page_header(
        kicker="READINESS & SOP ACTIVATION",
        title="Preparedness & Readiness",
        subtitle="Risk-driven operational checklists updated dynamically by each zone's simulated or weather-feed risk band.",
        right_badge=(f"ACTIVE INPUT: {rain_label}", "teal"),
    )

    selected_zone_name = st.selectbox(
        "Select Pilot GIS Sub-Zone:",
        [z["zone_name"] for z in evaluated_zones],
        index=0,
    )
    zone_match = next(z for z in evaluated_zones if z["zone_name"] == selected_zone_name)
    z_band = zone_match["risk_level"]

    z_col1, z_col2, z_col3 = st.columns(3)
    with z_col1:
        render_kpi_card("Illustrative Risk Score", f"{zone_match['risk_score']:.1f}", "/100", badge=(z_band, z_band.lower()), foot=zone_match["zone_name"])
    with z_col2:
        render_kpi_card("Scenario Rainfall", f"{zone_match['rainfall_mm']:.1f}", " mm", badge=(zone_match["rainfall_source"], "teal"), foot="Updates checklist dynamically")
    with z_col3:
        teams = get_response_teams()
        avail_count = len([t for t in teams if t["status"] == "Available"])
        render_kpi_card("Available Demo Units", f"{avail_count}", f" / {len(teams)}", badge=("Standby", "low" if avail_count else "critical"), foot="Illustrative response fleet")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    col_list, col_prof = st.columns([1.35, 0.65], gap="medium")

    with col_list:
        render_section_heading(f"Zone Emergency Action Checklist — {zone_match['zone_name']}", f"{z_band} Readiness Tier")
        checklist = zone_match.get("prep_checklist", [])
        if not checklist:
            st.info("No specific preparedness actions defined for this risk level.")
        else:
            action_badge_tone = "critical" if z_band == "Critical" else ("high" if z_band == "High" else "teal")
            for idx, item in enumerate(checklist, 1):
                st.markdown(
                    f"""
                    <div class="prep-action-card">
                        <div class="fiq-card-top">
                            <span class="prep-action-title">{idx}. {html.escape(item['action'])}</span>
                            {badge_html("Action Required" if z_band in ("High", "Critical") else "Recommended", action_badge_tone)}
                        </div>
                        <div class="prep-action-reason"><b>Directive Rationale:</b> {html.escape(item['reason'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with col_prof:
        render_section_heading("Zone Vulnerability Profile", "Catchment characteristics")
        zone_desc = next(
            (z.get("description", "") for z in zones_data if z["zone_id"] == zone_match["zone_id"]),
            "Urban residential and commercial catchment area.",
        )
        st.markdown(
            f"""
            <div class="fiq-card fiq-card-{z_band.lower()}">
                <div class="fiq-card-top">
                    <span class="fiq-card-title">{html.escape(zone_match['zone_name'])}</span>
                    {badge_html(z_band, z_band.lower())}
                </div>
                <div class="fiq-card-loc" style="margin-top:0.45rem; line-height:1.45;">{html.escape(zone_desc)}</div>
                <div class="fiq-card-meta" style="margin-top:0.55rem;">
                    <span>Drainage Vuln.: <b>{zone_match['drainage_score']}/100</b></span>
                    <span>Low-Lying Score: <b>{zone_match['low_lying_score']}/100</b></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_section_heading("Available Demo Units", "Illustrative fleet status")
        for t in teams:
            t_st = t["status"]
            st.markdown(
                f"""
                <div class="fiq-card" style="padding:0.45rem 0.7rem; margin-bottom:0.32rem;">
                    <div class="fiq-card-top">
                        <span style="font-size:0.78rem; font-weight:600; color:#F0F5F8;">{html.escape(t['team_name'])}</span>
                        {badge_html(t_st, "low" if t_st == "Available" else "critical")}
                    </div>
                    <div class="fiq-card-meta" style="margin-top:0.15rem;">
                        <span>{html.escape(t['specialty'])}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ===========================================================================
# PHASE 5: CITIZEN REPORTING
# ===========================================================================

elif nav_option == "Citizen Reporting":
    ai_active = bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here" and not OFFLINE_MODE)
    render_page_header(
        kicker="TACTICAL INTAKE & AI TRIAGE",
        title="Citizen Reporting / Emergency Intake & AI Triage",
        subtitle="Structured citizen report intake with Gemini AI triage and automatic deterministic local fallback.",
        right_badge=("TRIAGE: GEMINI AI" if ai_active else "TRIAGE: DETERMINISTIC FALLBACK", "teal" if ai_active else "blue"),
    )

    col_form, col_result = st.columns([1.08, 0.92], gap="medium")

    with col_form:
        render_section_heading("Submit Emergency Report", "Demo presets available for contrast")
        col_d1, col_d2 = st.columns(2)

        if col_d1.button("Preset A: Stranded Elderly (Critical)", use_container_width=True):
            st.session_state["form_desc"] = (
                "Heavy rain has caused water to enter a residential building near the Musi Riverfront. "
                "Three people are stranded on the first floor, including an elderly person. "
                "Water levels are continuing to rise."
            )
            st.session_state["form_zone"] = "Musi Riverfront"
            st.session_state["form_loc"] = "Residential colony near Musi River bridge, Chaderghat"
            st.session_state["form_people"] = 3
            st.session_state["form_cat"] = "Water Rescue"
            st.rerun()

        if col_d2.button("Preset B: Waterlogged Road (Moderate)", use_container_width=True):
            st.session_state["form_desc"] = (
                "Road near Ameerpet metro station is partially waterlogged after heavy rain. "
                "Traffic is affected but no vehicles are stuck. Some pedestrians are wading through ankle-deep water."
            )
            st.session_state["form_zone"] = "Ameerpet"
            st.session_state["form_loc"] = "Main road near Ameerpet Metro Station pillar 1042"
            st.session_state["form_people"] = 0
            st.session_state["form_cat"] = "Road Blockage"
            st.rerun()

        with st.form("citizen_report_form"):
            c_f1, c_f2 = st.columns(2)
            with c_f1:
                cat_list = INCIDENT_CATEGORIES
                default_cat_idx = cat_list.index(st.session_state["form_cat"]) if st.session_state.get("form_cat") in cat_list else 0
                reported_category = st.selectbox("Incident Category (Optional)", cat_list, index=default_cat_idx)
                location_text = st.text_input(
                    "Specific Location / Landmark",
                    value=st.session_state.get("form_loc", ""),
                    placeholder="e.g. Near Community Hall, Pillar 45",
                )
            with c_f2:
                zone_names = [z["zone_name"] for z in zones_data]
                default_zone_idx = zone_names.index(st.session_state["form_zone"]) if st.session_state.get("form_zone") in zone_names else 0
                selected_zone_name = st.selectbox("Hyderabad Pilot Zone *", zone_names, index=default_zone_idx)
                people_affected = st.number_input(
                    "Affected People (if known)",
                    min_value=0,
                    max_value=100,
                    value=int(st.session_state.get("form_people", 1)),
                    step=1,
                )

            desc = st.text_area(
                "Incident Description (Citizen Text) *",
                value=st.session_state.get("form_desc", ""),
                placeholder="Describe water levels, stranded individuals, vulnerable residents, or immediate hazards...",
                height=120,
            )

            submit_report = st.form_submit_button("Submit Report & Run AI Triage", type="primary", use_container_width=True)

        if submit_report:
            if not desc.strip():
                st.error("Please provide an incident description before submitting.")
            else:
                with st.spinner("Running triage and vulnerability-first scoring..."):
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
                        "vulnerable_flag": triage_res["vulnerable_flag"],
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
                    st.success(f"Report logged as **{new_id}**.")

    with col_result:
        render_section_heading("AI Triage Assessment", "Requires human verification in Control Room")
        last_id = st.session_state.get("last_submitted_id")
        inc = get_incident(last_id) if last_id else None

        if not inc:
            st.info("Submit a report or load a demo preset on the left to inspect extracted triage fields and priority scoring.")
        else:
            p_score = inc.get("priority_score", 0)
            band = band_from_score(p_score)
            triage_label = (
                "Gemini AI"
                if inc["triage_mode"] == "ai"
                else ("Deterministic Fallback" if inc["triage_mode"] == "fallback" else str(inc["triage_mode"]))
            )

            st.markdown(
                f"""
                <div class="fiq-card fiq-card-{band.lower()}">
                    <div class="fiq-card-top">
                        <span class="fiq-card-id">ANALYSIS ID: {html.escape(inc['incident_id'])}</span>
                        {badge_html(f"Mode: {triage_label}", "teal")}
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:0.5rem;">
                        <div>
                            <div style="font-size:0.65rem; text-transform:uppercase; color:#6A8294; font-weight:700;">Calculated Priority</div>
                            <div style="font-size:1.75rem; font-weight:700; color:#F0F5F8;">{p_score:.0f}<span style="font-size:0.85rem; color:#6A8294;">/100</span></div>
                        </div>
                        <div>{badge_html(f"{inc['ai_category']} · {band}", band.lower())}</div>
                    </div>
                    <div class="fiq-card-meta" style="margin-top:0.55rem;">
                        <span>Stranded: <b>{'Yes' if inc['stranded'] else 'No'}</b></span>
                        <span>Affected: <b>{inc['people_affected']}</b></span>
                        <span>Vulnerable: <b>{html.escape(inc['vulnerable_group'] if inc['vulnerable_flag'] else 'None')}</b></span>
                        <span>Immediate Hazard: <b>{'Yes' if inc['immediate_hazard'] else 'No'}</b></span>
                    </div>
                    <div class="fiq-card-loc" style="margin-top:0.55rem; padding-top:0.45rem; border-top:1px solid #1E384D;">
                        <b>Triage Rationale:</b> {html.escape(inc['ai_rationale'])}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption("Notice: AI/fallback output is assistive and unverified; human operators control dispatch.")
            st.button(
                "Forward to Response Control Room",
                key="goto_dispatch",
                type="primary",
                use_container_width=True,
                on_click=_go_to_control_room,
                args=(inc["incident_id"],),
            )


# ===========================================================================
# PHASE 6: RESPONSE CONTROL ROOM
# ===========================================================================

elif nav_option == "Response Control Room":
    incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}
    crit_cnt = len([i for i in incidents if i["priority_score"] >= 75 and i["status"] != "Resolved"])

    render_page_header(
        kicker="INCIDENT TRIAGE & TACTICAL DISPATCH",
        title="Response Control Room",
        subtitle="Human-in-the-loop dispatch console. Operators hold sole authority over unit assignment.",
        right_badge=(f"{crit_cnt} CRITICAL", "critical" if crit_cnt else "low"),
    )

    if not incidents:
        st.info("No incidents currently in the system.")
    else:
        if not st.session_state.get("selected_incident_id") or not get_incident(st.session_state["selected_incident_id"]):
            st.session_state["selected_incident_id"] = incidents[0]["incident_id"]

        col_q, col_detail, col_auth = st.columns([0.82, 1.12, 1.06], gap="medium")

        with col_q:
            render_section_heading("Active Incidents", f"{len(incidents)} total")
            for item in incidents:
                ip = item.get("priority_score", 0)
                iband = band_from_score(ip)
                is_sel = item["incident_id"] == st.session_state["selected_incident_id"]
                border_style = "border: 1px solid #21C7B7;" if is_sel else ""
                st.markdown(
                    f"""
                    <div class="fiq-card fiq-card-{iband.lower()}" style="{border_style} padding:0.55rem 0.7rem; margin-bottom:0.28rem;">
                        <div class="fiq-card-top">
                            <span class="fiq-card-id">#{html.escape(item['incident_id'])}</span>
                            {badge_html(f"{ip:.0f}/100", iband.lower())}
                        </div>
                        <div style="font-size:0.8rem; font-weight:600; color:#F0F5F8; margin-top:0.12rem;">{html.escape(item['ai_category'] or item['reported_category'])}</div>
                        <div class="fiq-card-meta" style="margin-top:0.15rem;">
                            <span>{html.escape(zone_name_by_id.get(item['zone_id'], item['zone_id']))}</span>
                            <span><b>{html.escape(item['status'])}</b></span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.button(
                    "Selected" if is_sel else f"Inspect {item['incident_id']}",
                    key=f"sel_inc_{item['incident_id']}",
                    disabled=is_sel,
                    use_container_width=True,
                    on_click=_select_incident,
                    args=(item["incident_id"],),
                )

        inc = get_incident(st.session_state["selected_incident_id"])

        with col_detail:
            p_score = inc.get("operator_priority") or inc.get("priority_score", 0)
            band = band_from_score(p_score)
            zone_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())

            render_section_heading(f"Priority Case #{inc['incident_id']}", inc["status"])
            st.markdown(
                f"""
                <div class="fiq-card fiq-card-{band.lower()}">
                    <div class="fiq-card-top">
                        <span class="fiq-card-title">{html.escape(inc['ai_category'] or inc['reported_category'])}</span>
                        <span style="font-size:1.25rem; font-weight:700; color:#F0F5F8;">{p_score:.0f}<span style="font-size:0.75rem; color:#6A8294;">/100</span></span>
                    </div>
                    <div class="fiq-card-loc" style="margin-top:0.35rem;"><b>{html.escape(zone_label)}</b> &mdash; {html.escape(inc['location_text'] or 'N/A')}</div>
                    <div style="margin-top:0.45rem; padding:0.5rem 0.6rem; background:#09131D; border:1px solid #1E384D; border-radius:4px; font-size:0.79rem; color:#D9E3F2; line-height:1.45;">
                        "{html.escape(inc['description'])}"
                    </div>
                    <div class="fiq-card-meta" style="margin-top:0.48rem;">
                        <span>Affected: <b>{inc['people_affected']}</b></span>
                        <span>Vulnerable: <b>{html.escape(inc['vulnerable_group'] if inc['vulnerable_flag'] else 'None')}</b></span>
                        <span>Stranded: <b>{'Yes' if inc['stranded'] else 'No'}</b></span>
                        <span>Hazard: <b>{'Yes' if inc['immediate_hazard'] else 'No'}</b></span>
                        <span>Triage: <b>{html.escape(str(inc['triage_mode']))}</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.caption(f"**Triage Rationale:** {inc['ai_rationale']}")

            priority_calc = calculate_priority({
                "ai_category": inc["ai_category"],
                "ai_urgency": inc["ai_urgency"],
                "people_affected": inc["people_affected"],
                "vulnerable_flag": inc["vulnerable_flag"],
                "stranded": inc["stranded"],
                "unable_to_evacuate": inc["unable_to_evacuate"],
                "immediate_hazard": inc["immediate_hazard"],
            })

            with st.expander("Priority Score Breakdown (Vulnerability-First)", expanded=True):
                factors = priority_calc["factors"]
                p_df = pd.DataFrame([
                    {"Factor": "Severity (S, 30%)", "Raw": factors["severity"]["score"], "Contribution": factors["severity"]["contribution"]},
                    {"Factor": "Stranded / Trapped (T, 25%)", "Raw": factors["stranded"]["score"], "Contribution": factors["stranded"]["contribution"]},
                    {"Factor": "Vulnerability (V, 25%)", "Raw": factors["vulnerability"]["score"], "Contribution": factors["vulnerability"]["contribution"]},
                    {"Factor": "People Count (N, 10%)", "Raw": factors["people_affected"]["score"], "Contribution": factors["people_affected"]["contribution"]},
                    {"Factor": "Immediate Hazard (H, 10%)", "Raw": factors["hazard"]["score"], "Contribution": factors["hazard"]["contribution"]},
                ])
                st.dataframe(p_df, use_container_width=True, hide_index=True)

        with col_auth:
            render_section_heading("Tactical Dispatch & Authorization", "Manual operator approval mandatory")
            st.markdown(
                """
                <div class="fiq-vuln-strip" style="margin-top:0; margin-bottom:0.55rem;">
                    <b>MANUAL OPERATOR DISPATCH MANDATORY</b> &mdash; Autonomous deployment is disabled. Team locations are illustrative demo data.
                </div>
                """,
                unsafe_allow_html=True,
            )

            rec = recommend_team(inc, teams, zone_coords=zone_coords)
            recommended_team = rec.get("recommended_team")

            if recommended_team:
                rec_base = zone_name_by_id.get(recommended_team["base_zone"], recommended_team["base_zone"].replace("_", " ").title())
                st.markdown(
                    f"""
                    <div class="fiq-card" style="border-left-color: var(--teal);">
                        <div class="fiq-card-top">
                            <span class="fiq-card-id" style="color:#21C7B7;">AI RECOMMENDED UNIT</span>
                            {badge_html(f"{rec.get('match_score', 0):.1f}/100 Match", "teal")}
                        </div>
                        <div class="fiq-card-title">{html.escape(recommended_team['team_name'])}</div>
                        <div class="fiq-card-meta">
                            <span>Specialty: <b>{html.escape(recommended_team['specialty'])}</b></span>
                            <span>Base: <b>{html.escape(rec_base)}</b></span>
                            <span>Distance: <b>{html.escape(rec['distance_desc'])}</b></span>
                        </div>
                        <div class="fiq-card-loc" style="margin-top:0.3rem;">{html.escape(rec['match_reason'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                alternatives = rec.get("alternatives", [])
                if alternatives:
                    with st.expander(f"Compare All Available Units ({len(alternatives) + 1})"):
                        alt_rows = [{
                            "Unit": recommended_team["team_name"],
                            "Specialty": recommended_team["specialty"],
                            "Base Zone": rec_base,
                            "Distance": rec["distance_desc"],
                            "Score": f"{rec.get('match_score', 0):.1f}/100",
                        }]
                        for alt in alternatives:
                            t_alt = alt["team"]
                            alt_rows.append({
                                "Unit": t_alt["team_name"],
                                "Specialty": t_alt["specialty"],
                                "Base Zone": zone_name_by_id.get(t_alt["base_zone"], t_alt["base_zone"].replace("_", " ").title()),
                                "Distance": alt["distance_desc"],
                                "Score": f"{alt['match_score']:.1f}/100",
                            })
                        st.dataframe(pd.DataFrame(alt_rows), use_container_width=True, hide_index=True)
            else:
                st.warning(rec["match_reason"])

            current_status = inc["status"]
            available_teams = [t for t in teams if t["status"] == "Available"]

            if current_status in ("Triaged", "In Review"):
                if current_status == "Triaged":
                    if st.button("Mark 'In Review' (Operator Acknowledged)", key=f"in_rev_{inc['incident_id']}", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Review", note="Operator took ownership for dispatch review.")
                        st.rerun()

                team_choices = {
                    f"{t['team_name']} ({t['specialty']}) — {zone_name_by_id.get(t['base_zone'], t['base_zone'].replace('_', ' ').title())}": t["team_id"]
                    for t in available_teams
                }

                if recommended_team and recommended_team["team_id"] in [t["team_id"] for t in available_teams]:
                    rec_label = [k for k, v in team_choices.items() if v == recommended_team["team_id"]][0]
                    rec_idx = list(team_choices.keys()).index(rec_label)
                else:
                    rec_idx = 0

                selected_team_label = st.selectbox(
                    "Available Units Selector:",
                    list(team_choices.keys()) if team_choices else ["No teams available"],
                    index=rec_idx if team_choices else 0,
                    disabled=not team_choices,
                )

                op_note = st.text_input(
                    "Duty Chief Dispatch Directive",
                    placeholder="e.g. Deploy with inflatable boat and medical kit",
                )

                if st.button("Authorize & Dispatch Team", key=f"dispatch_{inc['incident_id']}", type="primary", use_container_width=True, disabled=not team_choices):
                    chosen_team_id = team_choices[selected_team_label]
                    chosen_team_name = team_name_by_id.get(chosen_team_id, chosen_team_id)
                    try:
                        if current_status == "Triaged":
                            update_incident_workflow(
                                incident_id=inc["incident_id"],
                                new_status="In Review",
                                note="Operator reviewed incident for dispatch.",
                            )
                        update_incident_workflow(
                            incident_id=inc["incident_id"],
                            new_status="Team Assigned",
                            assigned_team_id=chosen_team_id,
                            note=op_note or f"Operator approved dispatch of {chosen_team_name} ({chosen_team_id}).",
                        )
                        st.success(f"{chosen_team_name} dispatched.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Dispatch failed: {e}")

            elif current_status == "Team Assigned":
                assigned_name = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"])
                st.info(f"**{assigned_name}** (`{inc['assigned_team_id']}`) is assigned to this incident.")
                c_act1, c_act2 = st.columns(2)
                with c_act1:
                    if st.button("Mark 'In Progress'", key=f"in_prog_{inc['incident_id']}", type="primary", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Progress", note="Team on-site and rescue operation underway.")
                        st.rerun()
                with c_act2:
                    if st.button("Revoke / Re-assign", key=f"revoke_{inc['incident_id']}", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Review", note="Assignment revoked by operator for reassignment.")
                        st.rerun()

            elif current_status == "In Progress":
                st.info("Response operation is in progress.")
                res_note = st.text_input("Resolution Report Note", placeholder="e.g. All 3 residents safely evacuated.")
                if st.button("Mark Incident Resolved", key=f"resolve_{inc['incident_id']}", type="primary", use_container_width=True):
                    update_incident_workflow(inc["incident_id"], "Resolved", note=res_note or "Incident resolved.")
                    st.success("Incident resolved and team returned to Available status.")
                    st.rerun()

            elif current_status == "Resolved":
                st.success("Incident is Resolved. Assigned unit has been released back to Available duty.")

            st.button(
                "View Audit Timeline in Incident History",
                key="goto_history_from_dispatch",
                use_container_width=True,
                on_click=_go_to_page,
                args=("Incident History",),
            )


# ===========================================================================
# PHASE 7A: INCIDENT HISTORY
# ===========================================================================

elif nav_option == "Incident History":
    render_page_header(
        kicker="OPERATIONAL ARCHIVE / INCIDENT HISTORY",
        title="Incident History & Chronological Timeline",
        subtitle="Immutable SQLite audit trail of reports, triage assessments, operator approvals, and resolutions.",
        right_badge=("APPEND-ONLY AUDIT LOG", "teal"),
    )

    all_incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}

    col_flt1, col_flt2 = st.columns(2)
    with col_flt1:
        status_flt = st.selectbox("Filter by Status:", ["All"] + list(STATUS_TRANSITIONS.keys()))
    with col_flt2:
        zone_flt_options = {"All": "All"} | {z["zone_name"]: z["zone_id"] for z in zones_data}
        zone_flt_label = st.selectbox("Filter by Zone:", list(zone_flt_options.keys()))
        zone_flt = zone_flt_options[zone_flt_label]

    filtered = all_incidents
    if status_flt != "All":
        filtered = [i for i in filtered if i["status"] == status_flt]
    if zone_flt != "All":
        filtered = [i for i in filtered if i["zone_id"] == zone_flt]

    if not filtered:
        st.info("No incidents match the selected filters.")
    else:
        if "history_inc_id" not in st.session_state or st.session_state["history_inc_id"] not in [i["incident_id"] for i in filtered]:
            st.session_state["history_inc_id"] = filtered[0]["incident_id"]

        col_ledger, col_trail = st.columns([0.95, 1.05], gap="medium")

        with col_ledger:
            render_section_heading("Historical Incident Ledger", f"{len(filtered)} record(s)")
            for inc in filtered:
                ip = inc.get("priority_score", 0)
                iband = band_from_score(ip)
                z_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())
                t_label = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"]) if inc.get("assigned_team_id") else "Unassigned"
                is_sel = inc["incident_id"] == st.session_state["history_inc_id"]
                border_css = "border: 1px solid #21C7B7;" if is_sel else ""

                st.markdown(
                    f"""
                    <div class="fiq-card fiq-card-{iband.lower()}" style="{border_css} padding:0.6rem 0.75rem; margin-bottom:0.3rem;">
                        <div class="fiq-card-top">
                            <span class="fiq-card-id">#{html.escape(inc['incident_id'])} &nbsp; {badge_html(iband, iband.lower())}</span>
                            <span style="font-size:0.8rem; font-weight:700; color:#F0F5F8;">{ip:.0f}/100</span>
                        </div>
                        <div class="fiq-card-title">{html.escape(inc['ai_category'] or inc['reported_category'])} &middot; {html.escape(z_label)}</div>
                        <div class="fiq-card-meta">
                            <span>Status: <b>{html.escape(inc['status'])}</b></span>
                            <span>Unit: <b>{html.escape(t_label)}</b></span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.button(
                    "Viewing Audit Trace" if is_sel else f"Inspect Trace · {inc['incident_id']}",
                    key=f"hist_sel_{inc['incident_id']}",
                    disabled=is_sel,
                    use_container_width=True,
                    on_click=lambda iid=inc["incident_id"]: st.session_state.__setitem__("history_inc_id", iid),
                )

        with col_trail:
            sel_inc = next(i for i in filtered if i["incident_id"] == st.session_state["history_inc_id"])
            created_disp = sel_inc["created_at"][:19].replace("T", " ") + " UTC" if sel_inc.get("created_at") else "N/A"
            render_section_heading(f"Incident Audit Trail: #{sel_inc['incident_id']}", f"Logged {created_disp}")

            st.markdown(
                f"""
                <div class="fiq-card" style="border-left-color: var(--blue);">
                    <div class="fiq-card-loc" style="color:#D9E3F2;">{html.escape(sel_inc['description'])}</div>
                    <div class="fiq-card-meta" style="margin-top:0.35rem;">
                        <span>Location: <b>{html.escape(sel_inc['location_text'] or 'N/A')}</b></span>
                        <span>Affected: <b>{sel_inc['people_affected']}</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            updates = get_incident_updates(sel_inc["incident_id"])
            for u in updates:
                u_time = u["updated_at"][:19].replace("T", " ") + " UTC" if u.get("updated_at") else ""
                old_s = html.escape(u["old_status"] or "Created")
                new_s = html.escape(u["new_status"] or "")
                note_s = html.escape(u["note"] or "")
                st.markdown(
                    f"""
                    <div class="timeline-item">
                        <span class="timeline-time">{u_time}</span><br>
                        <b style="color:#F0F5F8; font-size:0.84rem;">{old_s} &rarr; {new_s}</b><br>
                        <span style="font-size:0.78rem; color:#91A5B3;">{note_s}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ===========================================================================
# PHASE 7B: SYSTEM INFORMATION
# ===========================================================================

elif nav_option == "System Information":
    render_page_header(
        kicker="ARCHITECTURE & OPERATIONAL INTEGRITY",
        title="System Information & Diagnostics",
        subtitle="Live weather/AI service modes, explainable scoring formulas, and hackathon prototype disclosures.",
        right_badge=("PROTOTYPE ENVIRONMENT", "teal"),
    )

    col_w, col_ai, col_db = st.columns(3)

    w_status = get_weather_status()
    with col_w:
        render_section_heading("Weather & Precipitation", "TELEM-01")
        if w_status["connected"]:
            st.success(f"Connected (Open-Meteo API)\nLatency: {w_status['latency_ms']} ms")
        else:
            st.warning(f"Offline / Fallback Active\n{w_status.get('error', 'Using simulated or default fallback')}")

    with col_ai:
        render_section_heading("AI Triage Service", "INFER-02")
        gemini_key_present = bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here")
        if gemini_key_present and not OFFLINE_MODE:
            st.success("Google Gemini API: Active\nModel: gemini-2.0-flash (auto-fallback enabled)")
        else:
            st.info("Deterministic Fallback: Active\nRule-based triage with identical JSON schema")

    with col_db:
        render_section_heading("Database & Persistence", "PERSIST-03")
        all_inc = list_incidents()
        teams = get_response_teams()
        st.success(f"SQLite (WAL Mode)\nIncidents: {len(all_inc)} | Demo Teams: {len(teams)}")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    col_arch, col_lim = st.columns(2, gap="medium")

    with col_arch:
        render_section_heading("Explainable Scoring & Resilience", "Mathematical transparency")
        st.markdown(
            r"""
            - **Zone Risk Heuristic:** $\mathbf{R = 0.40P + 0.30D + 0.30L}$ combines normalized rainfall ($P$, 150 mm ceiling), drainage vulnerability ($D$), and low-lying terrain ($L$).
            - **Vulnerability-First Priority:** $\mathbf{I = 0.30S + 0.25T + 0.25V + 0.10N + 0.10H}$ ensures stranded or vulnerable citizens outrank general traffic disruption.
            - **Offline Guarantees:** Missing API keys, timeouts, or malformed responses fall back cleanly to deterministic triage and cached/default rainfall.
            - **Transaction Safety:** SQLite transactions prevent duplicate team assignments and enforce valid status transitions.
            """
        )

    with col_lim:
        render_section_heading("Prototype Scope & Limitations", "Judge disclosures")
        st.markdown(
            """
            - **Illustrative Risk Scores:** The risk formula is an explainable hackathon heuristic, not a validated hydrological or flood-probability model.
            - **Simulated Rainfall:** Slider values are scenario inputs for demonstration, not real-time rain-gauge observations.
            - **Illustrative Team Data:** Response team locations, specialties, and availability are demonstration seed data.
            - **Human-in-the-Loop:** AI assists with triage and unit matching; human operators retain sole dispatch authority. Citizen reports are not independently verified.
            """
        )
