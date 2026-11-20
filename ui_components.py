"""
FloodIQ — Shared UI Components & Visual Helpers

Implements the FloodIQ Command System dark tactical design tokens across all
seven application pages while preserving live SQLite/weather/AI state.
"""

from __future__ import annotations

import html
from typing import Iterable, Optional

import streamlit as st


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
    """Return an inline HTML badge using FloodIQ Command System tones."""
    safe_label = html.escape(str(label))
    safe_tone = html.escape(tone.lower())
    return f'<span class="fiq-badge fiq-badge-{safe_tone}">{safe_label}</span>'


def render_topbar(mode_label: str, mode_tone: str, source_desc: str, rain_label: str) -> None:
    """Render the persistent top operational scope & weather/simulation bar."""
    st.markdown(
        f"""
        <div class="fiq-topbar">
          <div class="fiq-topbar-left">
            <span class="fiq-scope-label">SCOPE:</span>
            <span class="fiq-scope-title">Hyderabad Urban Flood (Pilot)</span>
            <span class="fiq-mode-pill fiq-mode-{html.escape(mode_tone)}"><i></i>{html.escape(mode_label)}</span>
          </div>
          <div class="fiq-topbar-right">
            <span class="fiq-rain-chip">Weather: <b>{html.escape(source_desc)}</b></span>
            <span class="fiq-rain-chip">Rainfall: <b>{html.escape(rain_label)}</b></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(
    kicker: str,
    title: str,
    subtitle: str,
    right_badge: Optional[tuple[str, str]] = None,
) -> None:
    """Render a compact dark-tactical page header banner."""
    badge_block = badge_html(right_badge[0], right_badge[1]) if right_badge else ""
    st.markdown(
        f"""
        <header class="fiq-page-head">
          <div>
            <div class="fiq-page-kicker">{html.escape(kicker)}</div>
            <h1 class="fiq-page-title">{html.escape(title)}</h1>
            <p class="fiq-page-sub">{html.escape(subtitle)}</p>
          </div>
          <div>{badge_block}</div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card(
    label: str,
    value: str,
    suffix: str = "",
    badge: Optional[tuple[str, str]] = None,
    foot: str = "",
    critical: bool = False,
) -> None:
    """Render a single dark-tactical KPI card."""
    cls = "fiq-kpi fiq-kpi-critical" if critical else "fiq-kpi"
    badge_str = badge_html(badge[0], badge[1]) if badge else ""
    suffix_str = f"<span>{html.escape(suffix)}</span>" if suffix else ""
    st.markdown(
        f"""
        <div class="{cls}">
          <div class="fiq-kpi-top">
            <span class="fiq-kpi-label">{html.escape(label)}</span>
            {badge_str}
          </div>
          <div class="fiq-kpi-val">{html.escape(value)}{suffix_str}</div>
          <div class="fiq-kpi-foot">{html.escape(foot)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, subtitle: Optional[str] = None) -> None:
    """Render a crisp hairline-underlined section header."""
    sub_html = f'<span class="fiq-sec-sub">{html.escape(subtitle)}</span>' if subtitle else ""
    st.markdown(
        f'<div class="fiq-sec-head"><h3 class="fiq-sec-title">{html.escape(title)}</h3>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def render_map_legend(items: Iterable[tuple[str, str]]) -> None:
    """Render a compact horizontal legend bar below a map."""
    pills = "".join(
        f'<span class="fiq-legend-item"><i style="background:{html.escape(color)};"></i>{html.escape(label)}</span>'
        for label, color in items
    )
    st.markdown(f'<div class="fiq-legend">{pills}</div>', unsafe_allow_html=True)
