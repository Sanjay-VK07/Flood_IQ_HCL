"""
FloodIQ — AI-Powered Urban Disaster Intelligence & Emergency Response Coordination Platform

Main Streamlit Application.
Follows clean separation of concerns — delegates all logic to backend modules.
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from config import (
    APP_TITLE,
    APP_SUBTITLE,
    APP_ICON,
    LEVEL_COLORS,
    MAP_CENTER_LAT,
    MAP_CENTER_LNG,
    MAP_DEFAULT_ZOOM,
    INCIDENT_CATEGORIES,
    STATUS_TRANSITIONS,
)
from database import (
    init_db,
    get_zones,
    create_incident,
    list_incidents,
    get_incident,
    get_response_teams,
    update_incident_workflow,
    get_incident_updates,
    reset_demo_data,
)
from weather import (
    get_rainfall_for_zones,
    get_weather_status,
)
from risk_engine import (
    evaluate_zones,
    get_risk_summary,
    classify_risk,
)
from ai_engine import triage_incident
from response_engine import (
    calculate_priority,
    recommend_team,
    haversine_distance,
)

# ---------------------------------------------------------------------------
# Streamlit Page Setup & Custom CSS
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title=f"{APP_TITLE} | Urban Flood Intelligence",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

def _load_css():
    css_path = Path(__file__).parent / "assets" / "style.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

_load_css()

# Ensure Database is initialized
init_db()

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------

if "simulated_rain_mm" not in st.session_state:
    st.session_state["simulated_rain_mm"] = 20.0  # Default to 20mm Normal

if "use_simulation" not in st.session_state:
    st.session_state["use_simulation"] = True

if "selected_incident_id" not in st.session_state:
    st.session_state["selected_incident_id"] = None

if "last_submitted_id" not in st.session_state:
    st.session_state["last_submitted_id"] = None


# ---------------------------------------------------------------------------
# Global Sidebar Navigation & Simulation Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(f"## {APP_ICON} {APP_TITLE}")
    st.caption(APP_SUBTITLE)
    st.markdown("---")

    nav_option = st.radio(
        "Navigation",
        [
            "1. Command Center",
            "2. Predict — Flood Risk",
            "3. Prepare — Readiness",
            "4. Citizen Reporting",
            "5. Respond — Control Room",
            "6. Incident History",
            "7. System Information",
        ],
        index=0,
    )

    st.markdown("---")
    st.markdown("### 🌧️ Rainfall Control")

    use_sim = st.toggle("Simulation Mode (Slider)", value=st.session_state["use_simulation"])
    st.session_state["use_simulation"] = use_sim

    if use_sim:
        # Quick Presets
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            if st.button("20mm\nNormal", use_container_width=True):
                st.session_state["simulated_rain_mm"] = 20.0
                st.rerun()
        with col_p2:
            if st.button("50mm\nModerate", use_container_width=True):
                st.session_state["simulated_rain_mm"] = 50.0
                st.rerun()
        with col_p3:
            if st.button("100mm\nCloudburst", use_container_width=True):
                st.session_state["simulated_rain_mm"] = 100.0
                st.rerun()

        rain_slider = st.slider(
            "Rainfall (mm)",
            min_value=0.0,
            max_value=150.0,
            value=float(st.session_state["simulated_rain_mm"]),
            step=5.0,
            help="Simulates rainfall over Hyderabad pilot catchment zones in real time.",
        )
        st.session_state["simulated_rain_mm"] = rain_slider
        st.caption(f"Currently simulating **{rain_slider:.0f} mm** rainfall across all zones.")
    else:
        st.info("Using **Live Open-Meteo Weather API** feed.")

    st.markdown("---")
    # Quick Reset Demo Data
    if st.button("🔄 Reset Demo Data", help="Restore seeded demo incidents and reset response teams"):
        reset_demo_data()
        st.session_state["selected_incident_id"] = None
        st.session_state["last_submitted_id"] = None
        st.success("Demo dataset re-seeded!")
        st.rerun()

    st.caption("Pilot Scenario: Hyderabad, India")


# ---------------------------------------------------------------------------
# Cached / Prepared Zone Evaluation
# ---------------------------------------------------------------------------

zones_data = get_zones()
sim_val = st.session_state["simulated_rain_mm"] if st.session_state["use_simulation"] else None
rainfall_map = get_rainfall_for_zones(zones_data, simulated_rainfall_mm=sim_val)
evaluated_zones = evaluate_zones(zones_data, rainfall_map)
risk_counts = get_risk_summary(evaluated_zones)

# Map zone coordinates for lookup
zone_coords = {z["zone_id"]: (z["latitude"], z["longitude"]) for z in zones_data}


# ---------------------------------------------------------------------------
# Helper: Folium Risk Map Generator
# ---------------------------------------------------------------------------

def create_folium_map(zones_evaluated, teams=None, highlight_zone_id=None):
    m = folium.Map(
        location=[MAP_CENTER_LAT, MAP_CENTER_LNG],
        zoom_start=MAP_DEFAULT_ZOOM,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Color map for risk levels
    color_map = {
        "Low": "green",
        "Moderate": "orange",
        "High": "red",
        "Critical": "darkred",
    }

    # Add zone circles
    for z in zones_evaluated:
        color = color_map.get(z["risk_level"], "blue")
        is_highlighted = (z["zone_id"] == highlight_zone_id)

        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 180px;">
            <h4 style="margin:0 0 6px 0;">{z['zone_name']}</h4>
            <b>Risk Score:</b> {z['risk_score']:.1f}/100<br>
            <b>Risk Level:</b> <span style="color:{LEVEL_COLORS.get(z['risk_level'], '#000')}; font-weight:bold;">{z['risk_level']}</span><br>
            <b>Rainfall:</b> {z['rainfall_mm']:.1f} mm ({z['rainfall_source']})<br>
            <b>Drainage Vulnerability:</b> {z['drainage_score']}/100<br>
            <b>Low-lying Score:</b> {z['low_lying_score']}/100
        </div>
        """

        folium.CircleMarker(
            location=[z["latitude"], z["longitude"]],
            radius=16 if is_highlighted else 12,
            color="black" if is_highlighted else color,
            weight=3 if is_highlighted else 2,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{z['zone_name']}: {z['risk_level']} Risk ({z['risk_score']:.0f}/100)",
        ).add_to(m)

    # Add response teams if provided
    if teams:
        for t in teams:
            status = t.get("status", "Available")
            icon_color = "blue" if status == "Available" else "gray"
            folium.Marker(
                location=[t["latitude"], t["longitude"]],
                popup=f"<b>{t['team_name']}</b><br>Specialty: {t['specialty']}<br>Status: {status}",
                tooltip=f"{t['team_name']} ({status})",
                icon=folium.Icon(color=icon_color, icon="shield", prefix="fa"),
            ).add_to(m)

    return m


# ===========================================================================
# MODULE 1: COMMAND CENTER
# ===========================================================================

if nav_option == "1. Command Center":
    st.markdown("## 🚨 Emergency Command Center")
    st.caption("Live operational intelligence, zone vulnerability overview, and priority incident queue.")

    # High-level KPIs
    incidents = list_incidents()
    teams = get_response_teams()

    total_zones = len(evaluated_zones)
    high_risk_zones = risk_counts.get("High", 0) + risk_counts.get("Critical", 0)
    active_incidents = len([i for i in incidents if i["status"] not in ("Resolved",)])
    critical_incidents = len([i for i in incidents if i["priority_score"] >= 75 and i["status"] != "Resolved"])
    avail_teams = len([t for t in teams if t["status"] == "Available"])
    assigned_teams = len([t for t in teams if t["status"] == "Assigned"])
    resolved_incidents = len([i for i in incidents if i["status"] == "Resolved"])

    # KPI Metric Row
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6, kpi7 = st.columns(7)
    kpi1.metric("Monitored Zones", f"{total_zones}")
    kpi2.metric("High/Crit Risk Zones", f"{high_risk_zones}", delta="Escalated" if high_risk_zones > 0 else "Normal", delta_color="inverse")
    kpi3.metric("Active Incidents", f"{active_incidents}")
    kpi4.metric("Critical Incidents", f"{critical_incidents}", delta="Urgent" if critical_incidents > 0 else "Clear", delta_color="inverse")
    kpi5.metric("Available Teams", f"{avail_teams}")
    kpi6.metric("Assigned Teams", f"{assigned_teams}")
    kpi7.metric("Resolved", f"{resolved_incidents}")

    st.markdown("---")

    # Map + Priority Queue
    col_map, col_queue = st.columns([1.1, 0.9])

    with col_map:
        st.markdown("#### 🗺️ Hyderabad Risk & Unit Deployment Map")
        sim_badge = "Simulated" if st.session_state["use_simulation"] else "Live Open-Meteo"
        st.caption(f"Weather Data Source: **{sim_badge}** | Active Rainfall: **{st.session_state['simulated_rain_mm'] if st.session_state['use_simulation'] else 'Live'} mm**")
        fmap = create_folium_map(evaluated_zones, teams)
        st_folium(fmap, height=430, use_container_width=True)

    with col_queue:
        st.markdown("#### ⚡ Priority Incident Queue (Vulnerability-First)")
        active_list = [i for i in incidents if i["status"] != "Resolved"]

        if not active_list:
            st.info("No active incidents in queue. All reports resolved or clear.")
        else:
            for inc in active_list[:5]:
                p_score = inc.get("priority_score", 0)
                band = "Critical" if p_score >= 75 else ("High" if p_score >= 50 else ("Moderate" if p_score >= 30 else "Low"))
                badge_class = f"badge-{band.lower()}"

                with st.container():
                    st.markdown(
                        f"""
                        <div class="card card-{band.lower()}" style="padding: 12px 16px; margin-bottom: 8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <b>{inc['incident_id']} — {inc['ai_category']}</b>
                                <span class="badge {badge_class}">Priority: {p_score:.0f}/100 ({band})</span>
                            </div>
                            <div style="font-size:13px; color:#334155; margin-top:4px;">
                                📍 <b>{inc['zone_id'].replace('_', ' ').title()}</b>: {inc['location_text'] or 'Location specified in report'}
                            </div>
                            <div style="font-size:12px; color:#64748b; margin-top:4px;">
                                👥 {inc['people_affected']} affected | Status: <b>{inc['status']}</b> | Team: {inc['assigned_team_id'] or 'Unassigned'}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    c_btn1, c_btn2 = st.columns([1, 1])
                    with c_btn1:
                        if st.button(f"Respond to {inc['incident_id']}", key=f"quick_resp_{inc['incident_id']}", use_container_width=True):
                            st.session_state["selected_incident_id"] = inc["incident_id"]
                            st.info(f"Selected {inc['incident_id']}. Please switch to '5. Respond — Control Room' in sidebar.")


# ===========================================================================
# MODULE 2: PREDICT — FLOOD RISK
# ===========================================================================

elif nav_option == "2. Predict — Flood Risk":
    st.markdown("## 🔍 Predict: Flood Risk Intelligence")
    st.caption("Transparent hydrological risk heuristic based on real-time rainfall, drainage capacity, and low-lying vulnerability.")

    # Formula Callout
    with st.expander("📐 Explainable Risk Formula & Heuristic Model", expanded=True):
        st.markdown(
            r"""
            **Risk Calculation Heuristic:**
            $$\mathbf{R = 0.40 \times P + 0.30 \times D + 0.30 \times L}$$

            - **$\mathbf{P}$ (Rainfall Score, 40% weight):** Normalized rainfall score ($0\text{--}100$), calibrated to $150\text{ mm}$ ceiling.
            - **$\mathbf{D}$ (Drainage Vulnerability, 30% weight):** Infrastructure drainage constraints ($0\text{--}100$).
            - **$\mathbf{L}$ (Low-lying Vulnerability, 30% weight):** Topographic elevation and riverine proximity ($0\text{--}100$).

            *Bands: 0–29 Low | 30–49 Moderate | 50–74 High | 75–100 Critical*
            """
        )

    # Interactive Map & Breakdown
    col_m, col_b = st.columns([1.2, 0.8])

    with col_m:
        st.markdown("#### Pilot Catchment Risk Zones")
        fmap = create_folium_map(evaluated_zones)
        st_folium(fmap, height=450, use_container_width=True)

    with col_b:
        st.markdown("#### Risk Contribution Breakdown")
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
            title=f"Zone Risk Components (Rainfall: {st.session_state['simulated_rain_mm'] if st.session_state['use_simulation'] else 'Live'} mm)",
            barmode="stack",
            color_discrete_map={
                "Rainfall (40%)": "#0284c7",
                "Drainage (30%)": "#f97316",
                "Low-Lying (30%)": "#8b5cf6",
            },
            height=380,
        )
        fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Detailed Zone Risk Comparison Table")
    table_rows = []
    for z in evaluated_zones:
        table_rows.append({
            "Zone": z["zone_name"],
            "Rainfall": f"{z['rainfall_mm']:.1f} mm ({z['rainfall_source']})",
            "Drainage Score": f"{z['drainage_score']}/100",
            "Low-Lying Score": f"{z['low_lying_score']}/100",
            "Total Risk Score": f"{z['risk_score']:.1f}/100",
            "Risk Level": z["risk_level"],
            "Dominant Factors": "; ".join(z["reasons"][:2]),
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True)


# ===========================================================================
# MODULE 3: PREPARE — READINESS
# ===========================================================================

elif nav_option == "3. Prepare — Readiness":
    st.markdown("## 🛡️ Prepare: Dynamic Preparedness Engine")
    st.caption("Automated emergency checklists triggered dynamically by zone risk level and vulnerable infrastructure indicators.")

    selected_zone_name = st.selectbox(
        "Select Urban Zone to Inspect Playbook:",
        [z["zone_name"] for z in evaluated_zones],
        index=0,
    )
    zone_match = next(z for z in evaluated_zones if z["zone_name"] == selected_zone_name)

    z_col1, z_col2, z_col3 = st.columns(3)
    z_col1.metric("Calculated Risk Score", f"{zone_match['risk_score']:.1f}/100")
    z_col2.metric("Risk Level", zone_match["risk_level"])
    z_col3.metric("Rainfall", f"{zone_match['rainfall_mm']:.1f} mm")

    st.markdown(f"### Preparedness Checklist for **{zone_match['zone_name']}** ({zone_match['risk_level']} Readiness)")

    checklist = zone_match.get("prep_checklist", [])
    if not checklist:
        st.info("No specific preparedness actions defined for this risk level.")
    else:
        for idx, item in enumerate(checklist, 1):
            st.markdown(
                f"""
                <div class="prep-action-card">
                    <div class="prep-action-title">☑️ {idx}. {item['action']}</div>
                    <div class="prep-action-reason"><b>Operational Rationale:</b> {item['reason']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("#### Zone Vulnerability Profile & Infrastructure Description")
    st.write(zone_match.get("description", "Urban residential and commercial catchment area."))


# ===========================================================================
# MODULE 4: CITIZEN REPORTING
# ===========================================================================

elif nav_option == "4. Citizen Reporting":
    st.markdown("## 📢 Citizen Emergency Incident Reporting")
    st.caption("Citizen emergency intake with immediate AI triage, vulnerability detection, and control room dispatch ingestion.")

    # Demonstration Preset Buttons
    st.markdown("##### 💡 Load Demonstration Presets:")
    col_d1, col_d2 = st.columns(2)

    preset_desc = ""
    preset_zone = "Musi Riverfront"
    preset_loc = ""
    preset_people = 1

    if col_d1.button("📋 Load Incident A (Stranded Elderly — Critical)", use_container_width=True):
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

    if col_d2.button("📋 Load Incident B (Waterlogged Road — Moderate)", use_container_width=True):
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
            placeholder="Describe what is happening, water levels, people trapped or needing help...",
            height=120,
        )

        c_f1, c_f2 = st.columns(2)
        with c_f1:
            zone_names = [z["zone_name"] for z in zones_data]
            default_zone_idx = 0
            if "form_zone" in st.session_state and st.session_state["form_zone"] in zone_names:
                default_zone_idx = zone_names.index(st.session_state["form_zone"])

            selected_zone_name = st.selectbox("Zone *", zone_names, index=default_zone_idx)
            location_text = st.text_input(
                "Specific Landmark / Street Address",
                value=st.session_state.get("form_loc", ""),
                placeholder="e.g. Near Community Hall, Pillar 45",
            )

        with c_f2:
            people_affected = st.number_input(
                "Number of People Affected / Stranded",
                min_value=0,
                max_value=100,
                value=int(st.session_state.get("form_people", 1)),
                step=1,
            )
            cat_list = INCIDENT_CATEGORIES
            default_cat_idx = 0
            if "form_cat" in st.session_state and st.session_state["form_cat"] in cat_list:
                default_cat_idx = cat_list.index(st.session_state["form_cat"])

            reported_category = st.selectbox("Incident Category (Optional)", cat_list, index=default_cat_idx)

        submit_report = st.form_submit_button("🚨 Submit Emergency Report", use_container_width=True)

    if submit_report:
        if not desc.strip():
            st.error("Please provide a valid incident description.")
        else:
            with st.spinner("Processing report through AI Triage Engine..."):
                # 1. Match zone_id
                target_zone = next(z for z in zones_data if z["zone_name"] == selected_zone_name)
                zone_id = target_zone["zone_id"]

                # 2. AI Triage
                triage_res = triage_incident(
                    description=desc,
                    zone_name=selected_zone_name,
                    location_text=location_text,
                    people_affected=people_affected,
                )

                # 3. Priority calculation
                priority_res = calculate_priority(triage_res)
                p_score = priority_res["priority_score"]

                # 4. Save to Database
                payload = {
                    "zone_id": zone_id,
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
                    "priority_score": p_score,
                    "status": "Triaged",
                }

                new_id = create_incident(payload)
                st.session_state["last_submitted_id"] = new_id
                st.session_state["selected_incident_id"] = new_id

                st.success(f"Emergency Report successfully lodged! Incident Reference ID: **{new_id}**")

    # Display confirmation card if report submitted
    last_id = st.session_state.get("last_submitted_id")
    if last_id:
        inc = get_incident(last_id)
        if inc:
            st.markdown("---")
            st.markdown(f"### Report Ingestion Summary — `{inc['incident_id']}`")
            p_score = inc.get("priority_score", 0)
            band = "Critical" if p_score >= 75 else ("High" if p_score >= 50 else ("Moderate" if p_score >= 30 else "Low"))

            col_s1, col_s2 = st.columns([1, 1])
            with col_s1:
                st.markdown(f"**AI Classification:** {inc['ai_category']}")
                st.markdown(f"**Assessed Urgency:** {inc['ai_urgency']}")
                st.markdown(f"**Triage Mode:** `{inc['triage_mode']}`")
                st.markdown(f"**Vulnerability Detected:** {'Yes — ' + str(inc['vulnerable_group']) if inc['vulnerable_flag'] else 'None reported'}")
                st.markdown(f"**Stranded / Trapped:** {'Yes' if inc['stranded'] else 'No'}")
                st.markdown(f"**Immediate Hazard:** {'Yes' if inc['immediate_hazard'] else 'No'}")

            with col_s2:
                st.metric("Vulnerability-First Priority Score", f"{p_score:.1f}/100", f"Band: {band}")
                st.info(f"**AI Rationale:** {inc['ai_rationale']}")
                if st.button("👉 Proceed to Control Room Response Dispatch", key="goto_dispatch"):
                    st.session_state["selected_incident_id"] = inc["incident_id"]
                    st.info("Switching to Respond — Control Room...")


# ===========================================================================
# MODULE 5: RESPOND — CONTROL ROOM
# ===========================================================================

elif nav_option == "5. Respond — Control Room":
    st.markdown("## 🎛️ Respond: Emergency Control Room")
    st.caption("Human-in-the-loop decision platform. AI assists with recommendations; operators hold sole assignment authority.")

    incidents = list_incidents()
    teams = get_response_teams()

    if not incidents:
        st.info("No incidents currently in system.")
    else:
        # Incident Selector (sorted by priority descending)
        incident_options = {
            f"{i['incident_id']} | Priority: {i['priority_score']:.0f} | {i['ai_category'] or i['reported_category']} ({i['status']})": i["incident_id"]
            for i in incidents
        }

        # Auto select
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

        st.markdown("---")

        # Incident Detail View
        col_info, col_dispatch = st.columns([1.1, 0.9])

        with col_info:
            p_score = inc.get("operator_priority") or inc.get("priority_score", 0)
            band = "Critical" if p_score >= 75 else ("High" if p_score >= 50 else ("Moderate" if p_score >= 30 else "Low"))

            st.markdown(f"### Incident `{inc['incident_id']}`")
            st.markdown(
                f"""
                <div class="card card-{band.lower()}">
                    <div style="font-size:16px; font-weight:600;">{inc['ai_category'] or inc['reported_category']} — {inc['zone_id'].replace('_', ' ').title()}</div>
                    <div style="margin-top:8px; font-size:14px; line-height:1.5;">"{inc['description']}"</div>
                    <div style="margin-top:10px; font-size:13px; color:#64748b;">
                        📍 <b>Location:</b> {inc['location_text'] or 'N/A'}<br>
                        👥 <b>Reported Affected:</b> {inc['people_affected']} person(s)<br>
                        ⚠️ <b>Vulnerable Group:</b> {inc['vulnerable_group'] if inc['vulnerable_flag'] else 'None reported'}<br>
                        🌊 <b>Immediate Hazard:</b> {'Yes (Rising water / collapse hazard)' if inc['immediate_hazard'] else 'No'}<br>
                        🚪 <b>Stranded / Unable to Evacuate:</b> {'Yes' if inc['stranded'] else 'No'}<br>
                        🤖 <b>Triage Mode:</b> {inc['triage_mode']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(f"**AI Rationale:** {inc['ai_rationale']}")

            # Priority Breakdown display
            priority_calc = calculate_priority({
                "ai_category": inc["ai_category"],
                "ai_urgency": inc["ai_urgency"],
                "people_affected": inc["people_affected"],
                "vulnerable_flag": inc["vulnerable_flag"],
                "stranded": inc["stranded"],
                "unable_to_evacuate": inc["unable_to_evacuate"],
                "immediate_hazard": inc["immediate_hazard"],
            })

            with st.expander("📊 Priority Score Breakdown (Vulnerability-First)", expanded=True):
                factors = priority_calc["factors"]
                p_df = pd.DataFrame([
                    {"Factor": "Severity (S, 30%)", "Raw Score": factors["severity"]["score"], "Weighted Contribution": factors["severity"]["contribution"]},
                    {"Factor": "Stranded / Trapped (T, 25%)", "Raw Score": factors["stranded"]["score"], "Weighted Contribution": factors["stranded"]["contribution"]},
                    {"Factor": "Vulnerability (V, 25%)", "Raw Score": factors["vulnerability"]["score"], "Weighted Contribution": factors["vulnerability"]["contribution"]},
                    {"Factor": "People Count (N, 10%)", "Raw Score": factors["people_affected"]["score"], "Weighted Contribution": factors["people_affected"]["contribution"]},
                    {"Factor": "Hazard (H, 10%)", "Raw Score": factors["hazard"]["score"], "Weighted Contribution": factors["hazard"]["contribution"]},
                ])
                st.dataframe(p_df, use_container_width=True)
                st.caption(f"Calculated Score: **{inc['priority_score']:.1f}/100** | Band: **{band}**")

        with col_dispatch:
            st.markdown("### 🚒 Response Unit Recommendation")

            # Run recommendation engine
            rec = recommend_team(inc, teams, zone_coords=zone_coords)
            recommended_team = rec.get("recommended_team")

            if recommended_team:
                st.success(f"🎯 **Top Recommended Unit:** {recommended_team['team_name']}")
                st.markdown(f"**Specialty:** `{recommended_team['specialty']}` | **Base:** `{recommended_team['base_zone']}`")
                st.markdown(f"**Proximity:** {rec['distance_desc']}")
                st.caption(f"**Suitability Analysis:** {rec['match_reason']}")
            else:
                st.warning(rec["match_reason"])

            st.markdown("---")
            st.markdown("#### ✍️ Human Operator Dispatch Decision")

            current_status = inc["status"]
            allowed_next = STATUS_TRANSITIONS.get(current_status, [])

            st.markdown(f"Current Workflow Status: **`{current_status}`**")

            # Team selection for assignment
            available_teams = [t for t in teams if t["status"] == "Available"]

            if current_status in ("Triaged", "In Review"):
                # Transition to In Review if currently Triaged
                if current_status == "Triaged":
                    if st.button("Mark 'In Review' (Operator Acknowledged)", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Review", note="Operator took ownership for dispatch review.")
                        st.rerun()

                # Team assignment form
                team_choices = {f"{t['team_name']} ({t['specialty']}) — Base: {t['base_zone']}": t["team_id"] for t in available_teams}

                if recommended_team and recommended_team["team_id"] in [t["team_id"] for t in available_teams]:
                    rec_label = [k for k, v in team_choices.items() if v == recommended_team["team_id"]][0]
                    rec_idx = list(team_choices.keys()).index(rec_label)
                else:
                    rec_idx = 0

                selected_team_label = st.selectbox(
                    "Choose Response Team to Dispatch:",
                    list(team_choices.keys()) if team_choices else ["No teams available"],
                    index=rec_idx if team_choices else 0,
                    disabled=not team_choices,
                )

                op_note = st.text_input("Operator Dispatch Order / Field Note", placeholder="e.g. Deploy with inflatable rescue boat and medical kit")

                if st.button("✅ Approve & Dispatch Selected Team", type="primary", use_container_width=True, disabled=not team_choices):
                    chosen_team_id = team_choices[selected_team_label]
                    try:
                        update_incident_workflow(
                            incident_id=inc["incident_id"],
                            new_status="Team Assigned",
                            assigned_team_id=chosen_team_id,
                            note=op_note or f"Assigned team {chosen_team_id} by operator.",
                        )
                        st.success(f"Team {chosen_team_id} assigned successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Dispatch failed: {e}")

            elif current_status == "Team Assigned":
                st.info(f"Team **{inc['assigned_team_id']}** is currently assigned to this incident.")
                c_act1, c_act2 = st.columns(2)
                with c_act1:
                    if st.button("Mark 'In Progress'", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Progress", note="Team on-site and rescue operation underway.")
                        st.rerun()
                with c_act2:
                    if st.button("Revoke / Re-assign", use_container_width=True):
                        update_incident_workflow(inc["incident_id"], "In Review", note="Assignment revoked by operator for reassignment.")
                        st.rerun()

            elif current_status == "In Progress":
                st.info("Emergency response in active progress on ground.")
                res_note = st.text_input("Resolution Report Note", placeholder="e.g. All 3 residents safely evacuated to dry shelter.")
                if st.button("🏁 Mark Incident Resolved", type="primary", use_container_width=True):
                    update_incident_workflow(inc["incident_id"], "Resolved", note=res_note or "Incident successfully resolved.")
                    st.success("Incident resolved and team returned to Available status!")
                    st.rerun()

            elif current_status == "Resolved":
                st.success("This incident has been marked as Resolved. Response team has been released back to Available duty.")


# ===========================================================================
# MODULE 6: INCIDENT HISTORY
# ===========================================================================

elif nav_option == "6. Incident History":
    st.markdown("## 📜 Incident Audit Trail & History")
    st.caption("Immutable transaction history of all emergency reports, priority adjustments, dispatch decisions, and resolutions.")

    all_incidents = list_incidents()

    col_flt1, col_flt2 = st.columns(2)
    with col_flt1:
        status_flt = st.selectbox("Filter by Status:", ["All"] + list(STATUS_TRANSITIONS.keys()))
    with col_flt2:
        zone_flt = st.selectbox("Filter by Zone:", ["All"] + [z["zone_id"] for z in zones_data])

    filtered = all_incidents
    if status_flt != "All":
        filtered = [i for i in filtered if i["status"] == status_flt]
    if zone_flt != "All":
        filtered = [i for i in filtered if i["zone_id"] == zone_flt]

    st.markdown(f"Showing **{len(filtered)}** incident(s):")

    for inc in filtered:
        with st.expander(f"Incident {inc['incident_id']} — {inc['ai_category']} ({inc['status']}) — Priority {inc['priority_score']:.0f}/100"):
            st.markdown(f"**Zone:** {inc['zone_id']} | **Location:** {inc['location_text']}")
            st.markdown(f"**Description:** {inc['description']}")
            st.markdown(f"**Assigned Team:** {inc['assigned_team_id'] or 'None'}")
            st.markdown(f"**Logged At:** {inc['created_at']}")

            st.markdown("##### ⏱️ Audit Updates Timeline:")
            updates = get_incident_updates(inc["incident_id"])
            for u in updates:
                st.markdown(
                    f"""
                    <div class="timeline-item">
                        <span class="timeline-time">{u['updated_at']}</span><br>
                        <b>Transition:</b> {u['old_status'] or 'None'} ➔ <b>{u['new_status']}</b><br>
                        <span style="font-size:13px; color:#475569;">📝 {u['note']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ===========================================================================
# MODULE 7: SYSTEM INFORMATION
# ===========================================================================

elif nav_option == "7. System Information":
    st.markdown("## ⚙️ System Status & Technical Diagnostics")
    st.caption("Architecture overview, API connectivity, and technical judging documentation.")

    col_w, col_ai, col_db = st.columns(3)

    # Weather status
    w_status = get_weather_status()
    with col_w:
        st.markdown("#### ☁️ Weather Service")
        if w_status["connected"]:
            st.success(f"Connected (Open-Meteo)\nLatency: {w_status['latency_ms']} ms")
        else:
            st.warning(f"Offline / Fallback\n{w_status.get('error', 'Using simulated/cache')}")

    # AI status
    with col_ai:
        st.markdown("#### 🧠 AI Triage Engine")
        gemini_key_present = bool(os.getenv("GEMINI_API_KEY"))
        if gemini_key_present and not os.getenv("OFFLINE_MODE", "").lower() in ("true", "1"):
            st.success("Google Gemini API: Active\nModel: gemini-2.0-flash")
        else:
            st.info("Deterministic Fallback: Active\n(Zero external API dependencies)")

    # DB status
    with col_db:
        st.markdown("#### 🗄️ Database Engine")
        all_inc = list_incidents()
        teams = get_response_teams()
        st.success(f"SQLite (WAL Mode)\nIncidents: {len(all_inc)} | Teams: {len(teams)}")

    st.markdown("---")

    st.markdown("### 🏆 Technical Judging Brief & Explainability Notes")
    st.markdown(
        """
        1. **Explainable Risk Heuristic:** Zone risk calculation uses a transparent formula $\mathbf{R = 0.40P + 0.30D + 0.30L}$. It separates rainfall input from static topographical & drainage vulnerability.
        2. **Vulnerability-First Priority Engine:** Incident ranking does not rely on timestamp queue order. It computes priority $\mathbf{I = 0.30S + 0.25T + 0.25V + 0.10N + 0.10H}$, guaranteeing that stranded elderly citizens (Incident A, ~92) receive priority over general waterlogged traffic (Incident B, ~48).
        3. **Deterministic Fallback Triage:** When external cloud APIs encounter rate limits, timeouts, or network loss, the system automatically falls back to an internal deterministic triage ruleset that outputs the exact same schema.
        4. **Human-in-the-Loop Safeguards:** AI assists with categorization and suitability matching, but response units are **never dispatched autonomously**. All deployments require affirmative human operator authorization.
        5. **Transaction Integrity:** Response unit assignment uses SQLite database transactions ensuring a team cannot be double-assigned to concurrent incidents.
        6. **Prototype Disclaimer:** Hydrological risk scores and response team locations are illustrative prototype models developed for hackathon demonstration. Production deployment would integrate municipal GIS layers and official dispatch channels.
        """
    )
