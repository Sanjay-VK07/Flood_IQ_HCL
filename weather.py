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

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    Fetch current rainfall and a six-hour precipitation outlook for one coordinate.
    Returns parsed result dict or None on any failure.

    Current values include rainfall, temperature, humidity, wind, and weather code.
    The hourly precipitation outlook is kept separate from the heuristic risk score.

    Docs: https://open-meteo.com/en/docs
    """
    try:
        params = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "current": "rain,precipitation,weather_code,temperature_2m,relative_humidity_2m,wind_speed_10m",
            "hourly": "precipitation",
            "forecast_hours": 12,
            "timezone": "Asia/Kolkata",
            "forecast_days": 2,
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

        forecast_precipitation_6h_mm = None
        forecast_window_end = None
        hourly = data.get("hourly") or {}
        hourly_times = hourly.get("time") or []
        hourly_precipitation = hourly.get("precipitation") or []
        current_time = current.get("time")

        if isinstance(current_time, str) and len(hourly_times) == len(hourly_precipitation):
            try:
                current_datetime = datetime.fromisoformat(current_time)
                future_hours = []
                for hour_text, amount in zip(hourly_times, hourly_precipitation):
                    try:
                        hour_datetime = datetime.fromisoformat(str(hour_text))
                    except (TypeError, ValueError):
                        continue
                    if hour_datetime > current_datetime:
                        future_hours.append((hour_datetime, amount))

                next_six_hours = future_hours[:6]
                if len(next_six_hours) == 6 and all(amount is not None for _, amount in next_six_hours):
                    amounts = [float(amount) for _, amount in next_six_hours]
                    if all(math.isfinite(amount) and amount >= 0 for amount in amounts):
                        forecast_precipitation_6h_mm = round(sum(amounts), 1)
                        forecast_window_end = next_six_hours[-1][0].isoformat()
            except (TypeError, ValueError):
                pass

        result = {
            "rainfall_mm": float(rainfall_mm) if rainfall_mm is not None else 0.0,
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "source": "live_open_meteo",
            "timestamp": current.get("time", datetime.now(timezone.utc).isoformat()),
            "api_response_time": data.get("current", {}).get("time"),
            "forecast_precipitation_6h_mm": forecast_precipitation_6h_mm,
            "forecast_window_start": current_time if forecast_precipitation_6h_mm is not None else None,
            "forecast_window_end": forecast_window_end,
            "forecast_source": "Open-Meteo" if forecast_precipitation_6h_mm is not None else None,
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
        "forecast_precipitation_6h_mm": None,
        "forecast_window_start": None,
        "forecast_window_end": None,
        "forecast_source": None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_rainfall_for_zones(
    zones: List[Dict[str, Any]],
    simulated_rainfall_mm: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Get rainfall data for pilot zones.

    Simulation and offline modes remain local. Live zone requests are fetched
    concurrently so one slow location does not serialize every other request.
    """
    result: Dict[str, Dict[str, Any]] = {}
    live_zones: List[tuple[Dict[str, Any], str]] = []

    for zone in zones:
        zone_id = zone["zone_id"]
        lat = zone["latitude"]
        lon = zone["longitude"]

        if simulated_rainfall_mm is not None:
            result[zone_id] = {
                "rainfall_mm": float(simulated_rainfall_mm),
                "temperature_c": None,
                "humidity_pct": None,
                "wind_speed_kmh": None,
                "weather_code": None,
                "forecast_precipitation_6h_mm": None,
                "forecast_window_start": None,
                "forecast_window_end": None,
                "forecast_source": None,
                "source": "simulated",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            continue

        if OFFLINE_MODE:
            result[zone_id] = _get_default_weather(zone_id)
            continue

        key = _cache_key(lat, lon)
        cached = _weather_cache.get(key)
        if cached and _is_cache_valid(cached):
            cached_result = cached.copy()
            cached_result["source"] = "cached"
            cached_result.pop("_cached_at", None)
            result[zone_id] = cached_result
            continue

        live_zones.append((zone, key))

    if live_zones:
        max_workers = min(5, len(live_zones))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    _fetch_open_meteo,
                    zone["latitude"],
                    zone["longitude"],
                ): (zone, key)
                for zone, key in live_zones
            }

            for future in as_completed(futures):
                zone, key = futures[future]
                zone_id = zone["zone_id"]
                live_data = future.result()

                if live_data:
                    live_data["_cached_at"] = time.time()
                    _weather_cache[key] = live_data.copy()
                    result[zone_id] = {
                        name: value
                        for name, value in live_data.items()
                        if name != "_cached_at"
                    }
                elif key in _weather_cache:
                    stale = _weather_cache[key].copy()
                    stale["source"] = "cached"
                    stale.pop("_cached_at", None)
                    result[zone_id] = stale
                    logger.info("Using stale cache for zone %s", zone_id)
                else:
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
