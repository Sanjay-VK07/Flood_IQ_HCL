"""
FloodIQ — Shared UI Components & Visual Helpers

Provides consistent headers, KPI strips, status badges, and severity color
mappings across all seven application pages.
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
