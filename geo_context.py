"""
FloodIQ — Public Geographic & Radar Context Integrations

Selective free-API integrations that add genuine operational value beyond
Open-Meteo (weather) and OpenTopoData (elevation):
1. RainViewer (https://api.rainviewer.com/public/weather-maps.json):
   Provides live radar precipitation tile URLs (explicitly labeled as Radar Imagery,
   distinct from measured/historical/forecast/simulated rainfall).
2. OpenStreetMap Overpass API (https://overpass-api.de/api/interpreter):
   Provides cached road, waterway, bridge, and critical building counts around the
   Hyderabad pilot zones (24h disk cache + graceful offline fallback).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from config import OFFLINE_MODE, PROJECT_ROOT

_RAINVIEWER_URL = "https://api.rainviewer.com/public/weather-maps.json"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OSM_CACHE_PATH = PROJECT_ROOT / "data" / "osm_zone_context_cache.json"

_RAINVIEWER_CACHE: dict[str, Any] = {"fetched_at": 0.0, "data": None}
_RAINVIEWER_TTL_SECONDS = 300  # 5 minutes
_OSM_TTL_SECONDS = 86400       # 24 hours


def get_rainviewer_radar() -> dict[str, Any]:
    """
    Fetch RainViewer radar precipitation tile metadata (5-minute cache).
    Mandatory attribution: 'Weather data by RainViewer' (https://www.rainviewer.com).
    """
    now = time.time()
    if _RAINVIEWER_CACHE["data"] is not None and (now - _RAINVIEWER_CACHE["fetched_at"]) < _RAINVIEWER_TTL_SECONDS:
        return _RAINVIEWER_CACHE["data"]

    if OFFLINE_MODE:
        return {
            "available": False,
            "data_type": "Radar Imagery",
            "tile_url_template": None,
            "attribution": "Weather data by RainViewer (rainviewer.com)",
            "error": "Offline mode enabled",
        }

    try:
        resp = requests.get(_RAINVIEWER_URL, timeout=6)
        resp.raise_for_status()
        payload = resp.json()
        host = payload.get("host", "https://tilecache.rainviewer.com")
        past = payload.get("radar", {}).get("past", [])
        latest = past[-1] if past else None
        tile_url = f"{host}{latest['path']}/256/{{z}}/{{x}}/{{y}}/2/1_1.png" if latest else None

        result = {
            "available": bool(tile_url),
            "data_type": "Radar Imagery",
            "host": host,
            "latest_frame_time": latest.get("time") if latest else None,
            "past_frame_count": len(past),
            "tile_url_template": tile_url,
            "attribution": "Weather data by RainViewer (rainviewer.com)",
            "licence_note": "Free for personal, educational, and small-scale non-commercial use with mandatory attribution.",
        }
        _RAINVIEWER_CACHE["fetched_at"] = now
        _RAINVIEWER_CACHE["data"] = result
        return result
    except Exception as exc:
        return {
            "available": False,
            "data_type": "Radar Imagery",
            "tile_url_template": None,
            "attribution": "Weather data by RainViewer (rainviewer.com)",
            "error": str(exc),
        }


def _load_osm_cache() -> dict[str, Any]:
    if not _OSM_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_OSM_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_osm_cache(cache: dict[str, Any]) -> None:
    try:
        _OSM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OSM_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_zone_osm_context(zone_id: str, lat: float, lon: float) -> dict[str, Any]:
    """
    Return cached OpenStreetMap (Overpass) infrastructure counts within ~800m of a zone:
    waterways, bridges, roads, and buildings. Uses 24h persistent disk cache.
    """
    cache = _load_osm_cache()
    now = time.time()
    cached_entry = cache.get(zone_id)
    if cached_entry and (now - cached_entry.get("fetched_at", 0)) < _OSM_TTL_SECONDS:
        return {**cached_entry["summary"], "source": "osm_overpass_cached"}

    if OFFLINE_MODE:
        if cached_entry:
            return {**cached_entry["summary"], "source": "osm_overpass_stale_cache"}
        return {"available": False, "source": "offline_fallback"}

    query = (
        f"[out:json][timeout:8];"
        f"("
        f'way["waterway"](around:800,{lat},{lon});'
        f'way["bridge"="yes"](around:800,{lat},{lon});'
        f'way["highway"~"primary|secondary|tertiary|residential"](around:600,{lat},{lon});'
        f");"
        f"out tags;"
    )
    try:
        resp = requests.post(
            _OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "FloodIQ-Hyderabad-Prototype/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        waterways = sum(1 for el in elements if "waterway" in el.get("tags", {}))
        bridges = sum(1 for el in elements if el.get("tags", {}).get("bridge") == "yes")
        roads = sum(1 for el in elements if "highway" in el.get("tags", {}))

        summary = {
            "available": True,
            "waterway_segments": waterways,
            "bridge_segments": bridges,
            "road_segments": roads,
            "licence": "OpenStreetMap ODbL",
        }
        cache[zone_id] = {"fetched_at": now, "summary": summary}
        _save_osm_cache(cache)
        return {**summary, "source": "osm_overpass_live"}
    except Exception:
        if cached_entry:
            return {**cached_entry["summary"], "source": "osm_overpass_stale_cache"}
        return {"available": False, "source": "overpass_unavailable"}
