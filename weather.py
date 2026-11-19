"""
FloodIQ — Weather Module

Integrates with the Open-Meteo API to retrieve rainfall data for pilot zones.
Provides three data modes:
  - "live_open_meteo" : Successfully fetched from the API
  - "cached"          : Returned from in-memory cache (within TTL)
  - "simulated"       : Using the operator-provided simulated rainfall value

Handles network errors, timeouts, malformed responses, and API unavailability
gracefully. The rest of the application never crashes due to weather failures.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from config import (
    OPEN_METEO_BASE_URL,
    WEATHER_API_TIMEOUT,
    OFFLINE_MODE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_weather_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_key(lat: float, lon: float) -> str:
    """Generate a cache key from rounded coordinates."""
    return f"{round(lat, 3)},{round(lon, 3)}"


def _is_cache_valid(entry: Dict[str, Any]) -> bool:
    """Check if a cache entry is still within TTL."""
    cached_at = entry.get("_cached_at", 0)
    return (time.time() - cached_at) < _CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# Open-Meteo API fetch
# ---------------------------------------------------------------------------

def _fetch_open_meteo(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Fetch current rainfall data from Open-Meteo for a single coordinate.
    Returns parsed result dict or None on any failure.

    Uses the forecast endpoint with current weather variables:
    - rain: rainfall in mm (liquid water equivalent)
    - precipitation: total precipitation in mm

    Docs: https://open-meteo.com/en/docs
    """
    try:
        params = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "current": "rain,precipitation,weather_code,temperature_2m,relative_humidity_2m,wind_speed_10m",
            "timezone": "Asia/Kolkata",
            "forecast_days": 1,
        }

        response = requests.get(
            OPEN_METEO_BASE_URL,
            params=params,
            timeout=WEATHER_API_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        # Validate the response has what we need
        current = data.get("current")
        if not current:
            logger.warning("Open-Meteo response missing 'current' block for (%s, %s)", lat, lon)
            return None

        # Extract rainfall — prefer 'rain' field, fall back to 'precipitation'
        rainfall_mm = current.get("rain")
        if rainfall_mm is None:
            rainfall_mm = current.get("precipitation", 0.0)

        result = {
            "rainfall_mm": float(rainfall_mm) if rainfall_mm is not None else 0.0,
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "source": "live_open_meteo",
            "timestamp": current.get("time", datetime.now(timezone.utc).isoformat()),
            "api_response_time": data.get("current", {}).get("time"),
        }

        return result

    except requests.exceptions.Timeout:
        logger.warning("Open-Meteo request timed out for (%s, %s)", lat, lon)
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Open-Meteo connection error for (%s, %s)", lat, lon)
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning("Open-Meteo HTTP error for (%s, %s): %s", lat, lon, e)
        return None
    except (ValueError, KeyError, TypeError) as e:
        logger.warning("Open-Meteo parse error for (%s, %s): %s", lat, lon, e)
        return None
    except Exception as e:
        logger.warning("Unexpected weather error for (%s, %s): %s", lat, lon, e)
        return None


# ---------------------------------------------------------------------------
# Default / fallback rainfall data
# ---------------------------------------------------------------------------

_DEFAULT_RAINFALL: Dict[str, float] = {
    "begumpet": 5.0,
    "khairatabad": 8.0,
    "ameerpet": 6.0,
    "kukatpally": 7.0,
    "musi_riverfront": 10.0,
}


def _get_default_weather(zone_id: str) -> Dict[str, Any]:
    """Return fallback weather data for offline/error scenarios."""
    return {
        "rainfall_mm": _DEFAULT_RAINFALL.get(zone_id, 5.0),
        "temperature_c": None,
        "humidity_pct": None,
        "wind_speed_kmh": None,
        "weather_code": None,
        "source": "default_fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_rainfall_for_zones(
    zones: List[Dict[str, Any]],
    simulated_rainfall_mm: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Get rainfall data for a list of zone dicts.

    Args:
        zones: List of zone dicts, each with 'zone_id', 'latitude', 'longitude'.
        simulated_rainfall_mm: If provided, use this value for all zones
                               (simulation/slider mode). No API calls made.

    Returns:
        Dict keyed by zone_id, each value containing:
        {
            "rainfall_mm": float,
            "temperature_c": float | None,
            "humidity_pct": float | None,
            "wind_speed_kmh": float | None,
            "weather_code": int | None,
            "source": "live_open_meteo" | "cached" | "simulated" | "default_fallback",
            "timestamp": str (ISO 8601),
        }
    """
    result: Dict[str, Dict[str, Any]] = {}

    for zone in zones:
        zone_id = zone["zone_id"]
        lat = zone["latitude"]
        lon = zone["longitude"]

        # --- Simulation mode (slider) ---
        if simulated_rainfall_mm is not None:
            result[zone_id] = {
                "rainfall_mm": float(simulated_rainfall_mm),
                "temperature_c": None,
                "humidity_pct": None,
                "wind_speed_kmh": None,
                "weather_code": None,
                "source": "simulated",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            continue

        # --- Offline mode ---
        if OFFLINE_MODE:
            result[zone_id] = _get_default_weather(zone_id)
            continue

        # --- Check cache ---
        key = _cache_key(lat, lon)
        if key in _weather_cache and _is_cache_valid(_weather_cache[key]):
            cached = _weather_cache[key].copy()
            cached["source"] = "cached"
            result[zone_id] = cached
            continue

        # --- Live API fetch ---
        live_data = _fetch_open_meteo(lat, lon)

        if live_data:
            # Store in cache
            live_data["_cached_at"] = time.time()
            _weather_cache[key] = live_data.copy()
            # Return without internal cache timestamp
            return_data = {k: v for k, v in live_data.items() if k != "_cached_at"}
            result[zone_id] = return_data
        else:
            # Check if we have stale cache
            if key in _weather_cache:
                stale = _weather_cache[key].copy()
                stale["source"] = "cached"
                stale.pop("_cached_at", None)
                result[zone_id] = stale
                logger.info("Using stale cache for zone %s", zone_id)
            else:
                # Complete fallback
                result[zone_id] = _get_default_weather(zone_id)

    return result


def get_weather_status() -> Dict[str, Any]:
    """
    Quick health check: attempts a single API call to verify Open-Meteo connectivity.

    Returns:
        {
            "connected": bool,
            "latency_ms": float | None,
            "error": str | None,
            "offline_mode": bool,
        }
    """
    if OFFLINE_MODE:
        return {
            "connected": False,
            "latency_ms": None,
            "error": "Offline mode enabled",
            "offline_mode": True,
        }

    try:
        start = time.time()
        response = requests.get(
            OPEN_METEO_BASE_URL,
            params={
                "latitude": 17.385,
                "longitude": 78.4867,
                "current": "rain",
            },
            timeout=WEATHER_API_TIMEOUT,
        )
        latency = (time.time() - start) * 1000
        response.raise_for_status()

        return {
            "connected": True,
            "latency_ms": round(latency, 1),
            "error": None,
            "offline_mode": False,
        }
    except Exception as e:
        return {
            "connected": False,
            "latency_ms": None,
            "error": str(e),
            "offline_mode": False,
        }


def clear_cache() -> None:
    """Clear the in-memory weather cache."""
    global _weather_cache
    _weather_cache = {}
