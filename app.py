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
    render_page_header(
        title="Emergency Operations Command Center",
        subtitle="Situational awareness, vulnerability-first incident queue, and operator-approved dispatch.",
        mode_label=mode_label,
        mode_tone=mode_tone,
        right_label="Scenario rainfall",
        right_value=rain_label,
        right_note="Illustrative risk simulation",
    )

    incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}

    total_zones = len(evaluated_zones)
    high_risk_zones = risk_counts.get("High", 0) + risk_counts.get("Critical", 0)
    open_incidents = [i for i in incidents if i["status"] != "Resolved"]
    critical_incidents = [i for i in open_incidents if i["priority_score"] >= 75]
    avail_teams = len([t for t in teams if t["status"] == "Available"])
    assigned_teams = len([t for t in teams if t["status"] == "Assigned"])

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Monitored zones", f"{total_zones}", "Hyderabad pilot")
    kpi2.metric("Elevated-risk zones", f"{high_risk_zones}", delta="High / critical", delta_color="inverse")
    kpi3.metric("Open incidents", f"{len(open_incidents)}", f"{len(incidents) - len(open_incidents)} resolved")
    kpi4.metric("Critical incidents", f"{len(critical_incidents)}", delta="Immediate review" if critical_incidents else "None active", delta_color="inverse")
    kpi5.metric("Available teams", f"{avail_teams}", f"{assigned_teams} assigned")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    col_map, col_queue = st.columns([1.12, 0.88], gap="medium")

    with col_map:
        render_section_heading(
            "Hyderabad Risk & Incident Map",
            f"Data source: {source_desc} — risk scores and team locations are illustrative demo data.",
        )
        fmap = create_folium_map(evaluated_zones, teams=teams, incidents=incidents)
        st_folium(fmap, height=420, use_container_width=True, returned_objects=[])
        render_map_legend([
            ("Critical Zone", "#c23934"),
            ("High Zone", "#e06d1b"),
            ("Moderate Zone", "#d4940a"),
            ("Low Zone", "#227752"),
            ("Active Incident", "#dc2626"),
            ("Response Unit", "#0b7a82"),
        ])

    with col_queue:
        render_section_heading(
            "Priority Incident Queue",
            "Ordered by vulnerability-first priority score (highest urgency & vulnerability first).",
        )

        if not open_incidents:
            st.info("No open incidents in queue. All reported incidents are resolved.")
        else:
            for inc in open_incidents[:5]:
                p_score = inc.get("priority_score", 0)
                band = band_from_score(p_score)
                zone_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())
                assigned_label = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"]) if inc.get("assigned_team_id") else "Unassigned"
                cat_label = inc["ai_category"] or inc["reported_category"]

                tags = [badge_html(f"Priority {p_score:.0f}/100 ({band})", band.lower())]
                if inc.get("vulnerable_flag"):
                    tags.append(badge_html(f"Vulnerable: {inc.get('vulnerable_group', 'Yes')}", "critical"))
                if inc.get("stranded"):
                    tags.append(badge_html("Stranded", "high"))

                extra_tags_html = (
                    f'<div style="margin-top:0.38rem; display:flex; flex-wrap:wrap; gap:0.35rem;">{"".join(tags[1:])}</div>'
                    if len(tags) > 1
                    else ""
                )

                st.markdown(
                    f"""
                    <div class="fiq-card fiq-card-{band.lower()}">
                        <div class="fiq-card-top">
                            <span class="fiq-card-title">{html.escape(inc['incident_id'])} &middot; {html.escape(cat_label)}</span>
                            {tags[0]}
                        </div>
                        <div class="fiq-card-loc"><b>{html.escape(zone_label)}</b> &mdash; {html.escape(inc['location_text'] or 'Location specified in report')}</div>
                        <div class="fiq-card-meta">
                            <span>Affected: <b>{inc['people_affected']}</b></span>
                            <span>Status: <b>{html.escape(inc['status'])}</b></span>
                            <span>Unit: <b>{html.escape(assigned_label)}</b></span>
                        </div>
                        {extra_tags_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.button(
                    f"Review & Dispatch {inc['incident_id']}",
                    key=f"quick_resp_{inc['incident_id']}",
                    use_container_width=True,
                    on_click=_go_to_control_room,
                    args=(inc["incident_id"],),
                )


# ===========================================================================
# MODULE 2: FLOOD RISK INTELLIGENCE
# ===========================================================================

elif nav_option == "Flood Risk Intelligence":
    render_page_header(
        title="Flood Risk Intelligence",
        subtitle="Illustrative scenario risk scoring combining rainfall input, drainage capacity, and terrain elevation.",
        mode_label=mode_label,
        mode_tone=mode_tone,
        right_label="Active rainfall",
        right_value=rain_label,
        right_note="Heuristic model (not a hydrological forecast)",
    )

    with st.expander("Explainable Risk Formula & Heuristic Model", expanded=False):
        st.markdown(
            r"""
            **Composite Risk Heuristic (Illustrative Scenario Score):**
            $$\mathbf{R = 0.40 \times P + 0.30 \times D + 0.30 \times L}$$

            - **$\mathbf{P}$ (Rainfall Score, 40% weight):** Normalized rainfall ($0\text{--}100$), calibrated to a $150\text{ mm}$ ceiling.
            - **$\mathbf{D}$ (Drainage Vulnerability, 30% weight):** Zone storm-drain capacity constraint ($0\text{--}100$).
            - **$\mathbf{L}$ (Low-Lying Vulnerability, 30% weight):** Topographic elevation and riverine proximity ($0\text{--}100$).

            *Bands: 0–29 Low | 30–49 Moderate | 50–74 High | 75–100 Critical. This is an explainable hackathon heuristic, not a validated hydrological model.*
            """
        )

    col_m, col_b = st.columns([1.1, 0.9], gap="medium")

    with col_m:
        render_section_heading("Pilot Catchment Risk Zones", f"Source: {source_desc}")
        fmap = create_folium_map(evaluated_zones)
        st_folium(fmap, height=410, use_container_width=True, returned_objects=[])
        render_map_legend([
            ("Critical (75–100)", "#c23934"),
            ("High (50–74)", "#e06d1b"),
            ("Moderate (30–49)", "#d4940a"),
            ("Low (0–29)", "#227752"),
        ])

    with col_b:
        render_section_heading("Risk Contribution Breakdown", f"Weighted factor contributions ({source_desc})")
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
                "Rainfall (40%)": "#0b7a82",
                "Drainage (30%)": "#e06d1b",
                "Low-Lying (30%)": "#3b5b70",
            },
            template="plotly_white",
            height=410,
        )
        fig.update_layout(
            margin=dict(l=16, r=16, t=42, b=16),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            yaxis_title="Risk Contribution (0–100)",
            xaxis_title="",
            legend_title_text="",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    render_section_heading("Zone-Wise Risk Comparison", "Sorted highest illustrative risk score first.")
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
    render_page_header(
        title="Zone Preparedness & Readiness",
        subtitle="Dynamic operational checklists triggered by each zone's current scenario risk band.",
        mode_label=mode_label,
        mode_tone=mode_tone,
        right_label="Active rainfall",
        right_value=rain_label,
        right_note="Updates dynamically with rainfall",
    )

    selected_zone_name = st.selectbox(
        "Select Hyderabad Pilot Zone:",
        [z["zone_name"] for z in evaluated_zones],
        index=0,
    )
    zone_match = next(z for z in evaluated_zones if z["zone_name"] == selected_zone_name)

    z_col1, z_col2, z_col3 = st.columns(3)
    z_col1.metric("Illustrative Risk Score", f"{zone_match['risk_score']:.1f}/100")
    z_col2.metric("Readiness Band", zone_match["risk_level"])
    z_col3.metric("Scenario Rainfall", f"{zone_match['rainfall_mm']:.1f} mm")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    col_list, col_prof = st.columns([1.35, 0.65], gap="medium")

    with col_list:
        render_section_heading(
            f"Action Checklist — {zone_match['zone_name']}",
            f"Triggered by {zone_match['risk_level']} risk band.",
        )
        checklist = zone_match.get("prep_checklist", [])
        if not checklist:
            st.info("No specific preparedness actions defined for this risk level.")
        else:
            for idx, item in enumerate(checklist, 1):
                st.markdown(
                    f"""
                    <div class="prep-action-card">
                        <div class="prep-action-title">{idx}. {html.escape(item['action'])}</div>
                        <div class="prep-action-reason"><b>Why:</b> {html.escape(item['reason'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with col_prof:
        render_section_heading("Zone Vulnerability Profile", "Static catchment characteristics.")
        zone_desc = next(
            (z.get("description", "") for z in zones_data if z["zone_id"] == zone_match["zone_id"]),
            "Urban residential and commercial catchment area.",
        )
        st.markdown(
            f"""
            <div class="fiq-card fiq-card-{zone_match['risk_level'].lower()}">
                <div class="fiq-card-top">
                    <span class="fiq-card-title">{html.escape(zone_match['zone_name'])}</span>
                    {badge_html(zone_match['risk_level'], zone_match['risk_level'].lower())}
                </div>
                <div class="fiq-card-loc" style="margin-top:0.5rem; line-height:1.45;">{html.escape(zone_desc)}</div>
                <div class="fiq-card-meta" style="margin-top:0.6rem;">
                    <span>Drainage: <b>{zone_match['drainage_score']}/100</b></span>
                    <span>Low-Lying: <b>{zone_match['low_lying_score']}/100</b></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ===========================================================================
# MODULE 4: CITIZEN REPORTING
# ===========================================================================

elif nav_option == "Citizen Reporting":
    render_page_header(
        title="Citizen Incident Reporting & Triage",
        subtitle="Structured intake with AI-assisted triage and deterministic offline fallback.",
        mode_label=mode_label,
        mode_tone=mode_tone,
        right_label="Triage engine",
        right_value="Gemini AI" if (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here" and not OFFLINE_MODE) else "Deterministic",
        right_note="Auto-fallback on API loss",
    )

    render_section_heading("Demo Presets", "Load contrasting scenarios to demonstrate vulnerability-first prioritization.")
    col_d1, col_d2 = st.columns(2)

    if col_d1.button("Load Incident A — Stranded Elderly (Critical)", use_container_width=True):
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

    if col_d2.button("Load Incident B — Waterlogged Road (Moderate)", use_container_width=True):
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
        desc = st.text_area(
            "Incident Description *",
            value=st.session_state.get("form_desc", ""),
            placeholder="Describe what is happening, water depth, and whether anyone is stranded or vulnerable...",
            height=110,
        )

        c_f1, c_f2 = st.columns(2)
        with c_f1:
            zone_names = [z["zone_name"] for z in zones_data]
            default_zone_idx = zone_names.index(st.session_state["form_zone"]) if st.session_state.get("form_zone") in zone_names else 0
            selected_zone_name = st.selectbox("Pilot Zone *", zone_names, index=default_zone_idx)
            location_text = st.text_input(
                "Specific Landmark / Street Address",
                value=st.session_state.get("form_loc", ""),
                placeholder="e.g. Near Community Hall, Pillar 45",
            )

        with c_f2:
            people_affected = st.number_input(
                "People Affected / Stranded (if known)",
                min_value=0,
                max_value=100,
                value=int(st.session_state.get("form_people", 1)),
                step=1,
            )
            cat_list = INCIDENT_CATEGORIES
            default_cat_idx = cat_list.index(st.session_state["form_cat"]) if st.session_state.get("form_cat") in cat_list else 0
            reported_category = st.selectbox("Reporter Category (Optional)", cat_list, index=default_cat_idx)

        submit_report = st.form_submit_button("Submit Emergency Report", type="primary", use_container_width=True)

    if submit_report:
        if not desc.strip():
            st.error("Please provide an incident description before submitting.")
        else:
            with st.spinner("Running triage and priority scoring..."):
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
                st.success(f"Incident **{new_id}** logged and triaged.")

    last_id = st.session_state.get("last_submitted_id")
    if last_id:
        inc = get_incident(last_id)
        if inc:
            st.markdown("---")
            p_score = inc.get("priority_score", 0)
            band = band_from_score(p_score)
            triage_label = (
                "Gemini AI"
                if inc["triage_mode"] == "ai"
                else ("Deterministic Fallback" if inc["triage_mode"] == "fallback" else str(inc["triage_mode"]))
            )
            render_section_heading(f"Triage Assessment — {inc['incident_id']}", "Extracted fields and priority score. Reports are not independently verified.")

            col_s1, col_s2 = st.columns([1.1, 0.9], gap="medium")
            with col_s1:
                flags_html = [
                    badge_html(f"Mode: {triage_label}", "teal"),
                    badge_html(f"Urgency: {inc['ai_urgency']}", band.lower()),
                ]
                if inc["vulnerable_flag"]:
                    flags_html.append(badge_html(f"Vulnerable: {inc['vulnerable_group']}", "critical"))
                if inc["stranded"]:
                    flags_html.append(badge_html("Stranded", "high"))
                if inc["unable_to_evacuate"]:
                    flags_html.append(badge_html("Unable to Evacuate", "high"))
                if inc["immediate_hazard"]:
                    flags_html.append(badge_html("Immediate Hazard", "critical"))

                st.markdown(
                    f"""
                    <div class="fiq-card fiq-card-{band.lower()}">
                        <div class="fiq-card-top">
                            <span class="fiq-card-title">{html.escape(inc['ai_category'])} &middot; {html.escape(zone_name_by_id.get(inc['zone_id'], inc['zone_id']))}</span>
                            {badge_html(f"Priority {p_score:.0f}/100 ({band})", band.lower())}
                        </div>
                        <div class="fiq-card-loc"><b>Triage Rationale:</b> {html.escape(inc['ai_rationale'])}</div>
                        <div style="margin-top:0.55rem; display:flex; flex-wrap:wrap; gap:0.35rem;">
                            {''.join(flags_html)}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col_s2:
                st.metric("Vulnerability-First Priority", f"{p_score:.1f}/100", f"Band: {band}")
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
    render_page_header(
        title="Response Control Room",
        subtitle="Human-in-the-loop dispatch workspace. AI recommends units; operators authorize all assignments.",
        mode_label=mode_label,
        mode_tone=mode_tone,
        right_label="Human control",
        right_value="Required",
        right_note="No autonomous dispatch",
    )

    incidents = list_incidents()
    teams = get_response_teams()
    team_name_by_id = {t["team_id"]: t["team_name"] for t in teams}

    if not incidents:
        st.info("No incidents currently in the system.")
    else:
        incident_options = {
            f"{i['incident_id']} | Priority {i['priority_score']:.0f} | {i['ai_category'] or i['reported_category']} ({i['status']})": i["incident_id"]
            for i in incidents
        }

        default_index = 0
        if st.session_state.get("selected_incident_id"):
            for idx, inc_id in enumerate(incident_options.values()):
                if inc_id == st.session_state["selected_incident_id"]:
                    default_index = idx
                    break

        selected_label = st.selectbox(
            "Select Incident to Review:",
            list(incident_options.keys()),
            index=default_index,
        )
        selected_id = incident_options[selected_label]
        st.session_state["selected_incident_id"] = selected_id
        inc = get_incident(selected_id)

        st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)
        col_info, col_dispatch = st.columns([1.05, 0.95], gap="medium")

        with col_info:
            p_score = inc.get("operator_priority") or inc.get("priority_score", 0)
            band = band_from_score(p_score)
            zone_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())

            render_section_heading(f"Incident Brief — {inc['incident_id']}")
            st.markdown(
                f"""
                <div class="fiq-card fiq-card-{band.lower()}">
                    <div class="fiq-card-top">
                        <span class="fiq-card-title">{html.escape(inc['ai_category'] or inc['reported_category'])} &middot; {html.escape(zone_label)}</span>
                        {badge_html(f"Priority {p_score:.0f}/100 ({band})", band.lower())}
                    </div>
                    <div class="fiq-card-loc" style="margin-top:0.45rem; line-height:1.5;">"{html.escape(inc['description'])}"</div>
                    <div class="fiq-card-meta" style="margin-top:0.55rem;">
                        <span>Location: <b>{html.escape(inc['location_text'] or 'N/A')}</b></span>
                        <span>Affected: <b>{inc['people_affected']}</b></span>
                        <span>Vulnerable: <b>{html.escape(inc['vulnerable_group'] if inc['vulnerable_flag'] else 'None reported')}</b></span>
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
                st.caption(f"Total Score: **{inc['priority_score']:.1f}/100** | Band: **{band}**")

        with col_dispatch:
            render_section_heading("Response Unit Recommendation", "Team locations and availability are illustrative demo data.")

            rec = recommend_team(inc, teams, zone_coords=zone_coords)
            recommended_team = rec.get("recommended_team")

            if recommended_team:
                rec_base = zone_name_by_id.get(recommended_team["base_zone"], recommended_team["base_zone"].replace("_", " ").title())
                st.markdown(
                    f"""
                    <div class="fiq-card" style="border-left-color: var(--teal);">
                        <div class="fiq-card-top">
                            <span class="fiq-card-title">Recommended: {html.escape(recommended_team['team_name'])}</span>
                            {badge_html(f"Match {rec.get('match_score', 0):.1f}/100", "teal")}
                        </div>
                        <div class="fiq-card-meta" style="margin-top:0.35rem;">
                            <span>Specialty: <b>{html.escape(recommended_team['specialty'])}</b></span>
                            <span>Base: <b>{html.escape(rec_base)}</b></span>
                            <span>Distance: <b>{html.escape(rec['distance_desc'])}</b></span>
                        </div>
                        <div class="fiq-card-loc" style="margin-top:0.35rem; font-size:0.76rem; color:var(--muted);">
                            {html.escape(rec['match_reason'])}
                        </div>
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
                            "Match Score": f"{rec.get('match_score', 0):.1f}/100",
                        }]
                        for alt in alternatives:
                            t_alt = alt["team"]
                            alt_rows.append({
                                "Unit": t_alt["team_name"],
                                "Specialty": t_alt["specialty"],
                                "Base Zone": zone_name_by_id.get(t_alt["base_zone"], t_alt["base_zone"].replace("_", " ").title()),
                                "Distance": alt["distance_desc"],
                                "Match Score": f"{alt['match_score']:.1f}/100",
                            })
                        st.dataframe(pd.DataFrame(alt_rows), use_container_width=True, hide_index=True)
            else:
                st.warning(rec["match_reason"])

            st.markdown("---")
            render_section_heading("Operator Dispatch Authorization", f"Current workflow status: {inc['status']}")

            current_status = inc["status"]
            available_teams = [t for t in teams if t["status"] == "Available"]

            if current_status in ("Triaged", "In Review"):
                if current_status == "Triaged":
                    if st.button("Mark 'In Review' (Operator Acknowledged)", use_container_width=True):
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
                    "Select Response Unit to Dispatch:",
                    list(team_choices.keys()) if team_choices else ["No teams available"],
                    index=rec_idx if team_choices else 0,
                    disabled=not team_choices,
                )

                op_note = st.text_input(
                    "Operator Dispatch Order / Note",
                    placeholder="e.g. Deploy with inflatable rescue boat and medical kit",
                )

                if st.button("Approve & Dispatch Selected Team", type="primary", use_container_width=True, disabled=not team_choices):
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
                        st.success(f"{chosen_team_name} assigned successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Dispatch failed: {e}")

            elif current_status == "Team Assigned":
                assigned_name = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"])
                st.info(f"**{assigned_name}** (`{inc['assigned_team_id']}`) is assigned to this incident.")
                c_act1, c_act2 = st.columns(2)
                with c_act1:
                    if st.button("Mark 'In Progress'", type="primary", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Progress", note="Team on-site and rescue operation underway.")
                        st.rerun()
                with c_act2:
                    if st.button("Revoke / Re-assign", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Review", note="Assignment revoked by operator for reassignment.")
                        st.rerun()

            elif current_status == "In Progress":
                st.info("Emergency response is actively underway.")
                res_note = st.text_input("Resolution Note", placeholder="e.g. All 3 residents safely evacuated.")
                if st.button("Mark Incident Resolved", type="primary", use_container_width=True):
                    update_incident_workflow(inc["incident_id"], "Resolved", note=res_note or "Incident resolved.")
                    st.success("Incident resolved and team released to Available status.")
                    st.rerun()

            elif current_status == "Resolved":
                st.success("Incident is Resolved. Assigned response team has been released back to Available duty.")

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
    render_page_header(
        title="Incident Audit Trail & History",
        subtitle="Chronological transaction log of reports, operator reviews, dispatches, and resolutions.",
        mode_label=mode_label,
        mode_tone=mode_tone,
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

    st.caption(f"Showing **{len(filtered)}** incident(s), ordered by priority.")

    if not filtered:
        st.info("No incidents match the selected filters.")
    else:
        for inc in filtered:
            z_label = zone_name_by_id.get(inc["zone_id"], inc["zone_id"].replace("_", " ").title())
            t_label = team_name_by_id.get(inc["assigned_team_id"], inc["assigned_team_id"]) if inc.get("assigned_team_id") else "None"
            created_disp = inc["created_at"][:19].replace("T", " ") + " UTC" if inc.get("created_at") else "N/A"
            cat_label = inc["ai_category"] or inc["reported_category"]

            with st.expander(f"{inc['incident_id']} — {cat_label} | {inc['status']} | Priority {inc['priority_score']:.0f}/100"):
                st.markdown(f"**Zone:** {z_label} | **Location:** {inc['location_text'] or 'N/A'}")
                st.markdown(f"**Description:** {inc['description']}")
                st.markdown(f"**Assigned Team:** {t_label} | **Logged:** {created_disp}")

                st.markdown("**Chronological Audit Timeline**")
                updates = get_incident_updates(inc["incident_id"])
                for u in updates:
                    u_time = u["updated_at"][:19].replace("T", " ") + " UTC" if u.get("updated_at") else ""
                    old_s = html.escape(u["old_status"] or "Created")
                    new_s = html.escape(u["new_status"] or "")
                    note_s = html.escape(u["note"] or "")
                    st.markdown(
                        f"""
                        <div class="timeline-item">
                            <span class="timeline-time">{u_time}</span><br>
                            <b>{old_s} &rarr; {new_s}</b><br>
                            <span style="font-size:0.8rem; color:var(--ink-2);">{note_s}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


# ===========================================================================
# MODULE 7: SYSTEM INFORMATION
# ===========================================================================

elif nav_option == "System Information":
    render_page_header(
        title="System Diagnostics & Architecture",
        subtitle="Live service status, offline fallback guarantees, scoring formulas, and prototype scope.",
        mode_label=mode_label,
        mode_tone=mode_tone,
    )

    col_w, col_ai, col_db = st.columns(3)

    w_status = get_weather_status()
    with col_w:
        st.markdown("#### Weather Feed")
        if w_status["connected"]:
            st.success(f"Connected (Open-Meteo)\nLatency: {w_status['latency_ms']} ms")
        else:
            st.warning(f"Offline / Fallback\n{w_status.get('error', 'Using simulated/default fallback')}")

    with col_ai:
        st.markdown("#### AI Triage Engine")
        gemini_key_present = bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here")
        if gemini_key_present and not OFFLINE_MODE:
            st.success("Google Gemini API: Active\nModel: gemini-2.0-flash")
        else:
            st.info("Deterministic Fallback: Active\nRule-based triage with identical output schema")

    with col_db:
        st.markdown("#### Persistence Engine")
        all_inc = list_incidents()
        teams = get_response_teams()
        st.success(f"SQLite (WAL Mode)\nIncidents: {len(all_inc)} | Demo Teams: {len(teams)}")

    st.markdown("---")
    col_arch, col_lim = st.columns(2, gap="medium")

    with col_arch:
        render_section_heading("Scoring & Triage Architecture")
        st.markdown(
            r"""
            - **Explainable Risk Heuristic:** $\mathbf{R = 0.40P + 0.30D + 0.30L}$ combines normalized rainfall ($P$), drainage vulnerability ($D$), and low-lying terrain ($L$).
            - **Vulnerability-First Priority:** $\mathbf{I = 0.30S + 0.25T + 0.25V + 0.10N + 0.10H}$ ensures stranded or vulnerable citizens outrank general traffic waterlogging.
            - **Offline Resilience:** Missing API keys, network loss, or malformed responses automatically fall back to deterministic triage and cached/default rainfall.
            - **Transaction Integrity:** SQLite transactions prevent duplicate team assignments and enforce valid status transitions.
            """
        )

    with col_lim:
        render_section_heading("Prototype Scope & Limitations")
        st.markdown(
            """
            - **Illustrative Risk Scores:** The risk formula is an explainable hackathon heuristic, not a validated hydrological or flood-probability model.
            - **Simulated Inputs:** Scenario rainfall values are operator-controlled simulation inputs, not real-time gauge observations.
            - **Demo Unit Data:** Response team locations, specialties, and availability are illustrative demonstration data.
            - **Human-in-the-Loop:** AI assists with triage and unit matching, but human operators hold sole dispatch authority. Citizen reports are not independently verified.
            """
        )
