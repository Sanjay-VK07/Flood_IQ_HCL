"""
FloodIQ — Configuration Module

Centralizes all configuration, environment variable loading, and application constants.
All settings are loaded once at import time and exposed as module-level constants.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "floodiq.db"))

# ---------------------------------------------------------------------------
# Weather API
# ---------------------------------------------------------------------------
OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
WEATHER_API_TIMEOUT: int = int(os.getenv("WEATHER_API_TIMEOUT", "10"))

# ---------------------------------------------------------------------------
# Offline / Demo Mode
# ---------------------------------------------------------------------------
OFFLINE_MODE: bool = os.getenv("OFFLINE_MODE", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Risk Engine Constants
# ---------------------------------------------------------------------------
# Weights for the flood risk formula: R = wP*P + wD*D + wL*L
RISK_WEIGHT_RAINFALL: float = 0.40
RISK_WEIGHT_DRAINAGE: float = 0.30
RISK_WEIGHT_LOWLYING: float = 0.30

# Rainfall normalization ceiling (mm). Rainfall >= this value maps to score 100.
RAINFALL_NORM_CEILING: float = 150.0

# Risk level thresholds (inclusive lower bound)
RISK_THRESHOLDS: dict = {
    "Low":      (0, 29),
    "Moderate": (30, 49),
    "High":     (50, 74),
    "Critical": (75, 100),
}

# ---------------------------------------------------------------------------
# Priority Engine Constants
# ---------------------------------------------------------------------------
# Weights for incident priority: I = wS*S + wT*T + wV*V + wN*N + wH*H
PRIORITY_WEIGHT_SEVERITY: float = 0.30
PRIORITY_WEIGHT_STRANDED: float = 0.25
PRIORITY_WEIGHT_VULNERABILITY: float = 0.25
PRIORITY_WEIGHT_PEOPLE: float = 0.10
PRIORITY_WEIGHT_HAZARD: float = 0.10

# People affected normalization ceiling
PEOPLE_NORM_CEILING: int = 20

# Priority level thresholds
PRIORITY_THRESHOLDS: dict = {
    "Low":      (0, 29),
    "Moderate": (30, 49),
    "High":     (50, 74),
    "Critical": (75, 100),
}

# ---------------------------------------------------------------------------
# Incident Categories & Statuses
# ---------------------------------------------------------------------------
INCIDENT_CATEGORIES: list[str] = [
    "Water Rescue",
    "Medical Emergency",
    "Road Blockage",
    "Infrastructure Damage",
    "Flooded Building",
    "Other",
]

URGENCY_LEVELS: list[str] = ["Critical", "High", "Medium", "Low"]

INCIDENT_STATUSES: list[str] = [
    "New",
    "Triaged",
    "In Review",
    "Team Assigned",
    "In Progress",
    "Resolved",
]

# Valid status transitions: current_status -> list of allowed next statuses
STATUS_TRANSITIONS: dict[str, list[str]] = {
    "New":           ["Triaged"],
    "Triaged":       ["In Review"],
    "In Review":     ["Team Assigned", "Resolved"],
    "Team Assigned": ["In Progress", "In Review"],
    "In Progress":   ["Resolved", "In Review"],
    "Resolved":      [],
}

# ---------------------------------------------------------------------------
# Vulnerable Groups
# ---------------------------------------------------------------------------
VULNERABLE_GROUPS: list[str] = [
    "Elderly people",
    "Children",
    "People with disabilities",
    "Pregnant women",
    "None reported",
]

# ---------------------------------------------------------------------------
# Gemini AI
# ---------------------------------------------------------------------------
GEMINI_MODEL: str = "gemini-2.0-flash"

# ---------------------------------------------------------------------------
# Seed Data Paths
# ---------------------------------------------------------------------------
ZONES_DATA_PATH: str = str(PROJECT_ROOT / "data" / "hyderabad_zones.json")
SEED_DATA_PATH: str = str(PROJECT_ROOT / "data" / "seed_data.json")
PREP_PLAYBOOKS_PATH: str = str(PROJECT_ROOT / "data" / "prep_playbooks.json")

# ---------------------------------------------------------------------------
# UI Constants
# ---------------------------------------------------------------------------
APP_TITLE: str = "FloodIQ"
APP_SUBTITLE: str = "AI-Powered Urban Flood Intelligence & Emergency Response"
APP_ICON: str = "🌊"

# Map defaults (centered on Hyderabad)
MAP_CENTER_LAT: float = 17.385
MAP_CENTER_LNG: float = 78.4867
MAP_DEFAULT_ZOOM: int = 12

# Color palette for risk/priority levels
LEVEL_COLORS: dict[str, str] = {
    "Low":      "#22c55e",   # Green
    "Moderate": "#eab308",   # Yellow
    "High":     "#f97316",   # Orange
    "Critical": "#ef4444",   # Red
}
