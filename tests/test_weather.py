"""
Tests for FloodIQ weather module — simulation mode, offline fallback, and API error handling.
"""

from unittest.mock import patch, MagicMock
import requests

import weather


SAMPLE_ZONES = [
    {"zone_id": "begumpet", "latitude": 17.44, "longitude": 78.4983},
    {"zone_id": "musi_riverfront", "latitude": 17.37, "longitude": 78.48},
]


def test_simulation_mode_returns_simulated_rainfall():
    result = weather.get_rainfall_for_zones(SAMPLE_ZONES, simulated_rainfall_mm=100.0)
    assert result["begumpet"]["rainfall_mm"] == 100.0
    assert result["begumpet"]["source"] == "simulated"
    assert result["musi_riverfront"]["rainfall_mm"] == 100.0
    assert result["musi_riverfront"]["source"] == "simulated"


def test_offline_mode_returns_default_fallback(monkeypatch):
    monkeypatch.setattr(weather, "OFFLINE_MODE", True)
    result = weather.get_rainfall_for_zones(SAMPLE_ZONES, simulated_rainfall_mm=None)
    assert result["begumpet"]["source"] == "default_fallback"
    assert result["musi_riverfront"]["source"] == "default_fallback"
    assert result["begumpet"]["rainfall_mm"] >= 0.0


def test_timeout_falls_back_gracefully(monkeypatch):
    monkeypatch.setattr(weather, "OFFLINE_MODE", False)
    weather._weather_cache.clear()
    with patch("weather.requests.get", side_effect=requests.exceptions.Timeout("timed out")):
        result = weather.get_rainfall_for_zones(SAMPLE_ZONES, simulated_rainfall_mm=None)
    assert result["begumpet"]["source"] == "default_fallback"
    assert result["musi_riverfront"]["source"] == "default_fallback"


def test_malformed_json_falls_back_gracefully(monkeypatch):
    monkeypatch.setattr(weather, "OFFLINE_MODE", False)
    weather._weather_cache.clear()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"unexpected": "payload"}
    with patch("weather.requests.get", return_value=mock_resp):
        result = weather.get_rainfall_for_zones(SAMPLE_ZONES, simulated_rainfall_mm=None)
    assert result["begumpet"]["source"] == "default_fallback"


def test_live_api_success_and_cache(monkeypatch):
    monkeypatch.setattr(weather, "OFFLINE_MODE", False)
    weather._weather_cache.clear()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "current": {
            "rain": 12.5,
            "precipitation": 12.5,
            "temperature_2m": 26.0,
            "relative_humidity_2m": 85,
            "wind_speed_10m": 14.0,
            "weather_code": 63,
            "time": "2026-11-19T18:00",
        }
    }
    with patch("weather.requests.get", return_value=mock_resp) as mock_get:
        first = weather.get_rainfall_for_zones(SAMPLE_ZONES[:1], simulated_rainfall_mm=None)
        second = weather.get_rainfall_for_zones(SAMPLE_ZONES[:1], simulated_rainfall_mm=None)
    assert first["begumpet"]["source"] == "live_open_meteo"
    assert first["begumpet"]["rainfall_mm"] == 12.5
    assert second["begumpet"]["source"] == "cached"
    assert mock_get.call_count == 1
