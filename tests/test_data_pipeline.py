"""
Tests for FloodIQ real-world data pipeline, caching, error handling, and dataset endpoints.
"""

import json
import sqlite3
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient

import api
import data_pipeline
import database


def _make_gpkg_point_polygon_blob(lon: float, lat: float) -> bytes:
    # GeoPackage binary header with standard 4-double envelope (env_ind = 1)
    header = b"GP\x00\x03" + struct.pack("<i", 4326)  # little-endian + envelope=1 -> flags=0x03
    env = struct.pack("<4d", lon - 0.1, lon + 0.1, lat - 0.1, lat + 0.1)
    return header + env


def test_srtm_elevation_success_and_cache_fallback(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(data_pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_pipeline, "CACHE_DIR", cache_dir)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "results": [{"location": {"lat": 17.37, "lng": 78.48}, "elevation": 503.0}]
    }

    with patch("data_pipeline.requests.get", return_value=mock_resp) as mock_get:
        res1 = data_pipeline.fetch_srtm_elevations([(17.37, 78.48)])
        assert res1["17.37,78.48"] == 503.0
        assert mock_get.call_count == 1

    # Second call should use cache without calling API
    with patch("data_pipeline.requests.get", side_effect=requests.ConnectionError("offline")):
        res2 = data_pipeline.fetch_srtm_elevations([(17.37, 78.48)])
        assert res2["17.37,78.48"] == 503.0


def test_open_meteo_archive_missing_values_and_malformed_response(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(data_pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_pipeline, "CACHE_DIR", cache_dir)

    # Malformed response (missing 'hourly') -> returns None gracefully
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.raise_for_status.return_value = None
    bad_resp.json.return_value = {"unexpected": True}
    with patch("data_pipeline.requests.get", return_value=bad_resp):
        assert data_pipeline.fetch_open_meteo_archive(17.37, 78.48, "2024-01-01", "2024-01-02") is None

    # Valid response with missing values (None) preserved without fabrication
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.raise_for_status.return_value = None
    ok_resp.json.return_value = {
        "hourly": {
            "time": ["2024-01-01T00:00", "2024-01-01T01:00", "2024-01-01T02:00"],
            "precipitation": [1.5, None, 2.5],
            "relative_humidity_2m": [80, 82, None],
            "temperature_2m": [25.0, 24.5, 24.0],
            "soil_moisture_0_to_7cm": [None, 0.25, 0.26],
        }
    }
    with patch("data_pipeline.requests.get", return_value=ok_resp):
        df = data_pipeline.fetch_open_meteo_archive(17.37, 78.48, "2024-01-01", "2024-01-02")
    assert df is not None
    assert len(df) == 3
    assert pd.isna(df.loc[1, "rainfall_1h"])
    assert df.loc[2, "rainfall_3h"] == pytest.approx(4.0)


def test_gpkg_geographic_filtering_india_and_hyderabad(tmp_path):
    gpkg = tmp_path / "test_floods.gpkg"
    conn = sqlite3.connect(str(gpkg))
    conn.execute(
        """CREATE TABLE combined_floods (
            ReportNumber TEXT, Country TEXT, BeginDate TEXT, EndDate TEXT,
            Severity TEXT, MainCause TEXT, NumberOfFatalities TEXT, NumberOfDisplaced TEXT, geom BLOB
        )"""
    )
    # 1. Near Hyderabad (~40 km)
    conn.execute(
        "INSERT INTO combined_floods VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("4969", "India", "2020-10-16", "2020-10-25", "1.5", "Monsoonal Rain", "6", "2100",
         _make_gpkg_point_polygon_blob(78.86, 17.34)),
    )
    # 2. Far India (Assam ~1600 km)
    conn.execute(
        "INSERT INTO combined_floods VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("5001", "India", "2020-07-01", "2020-07-10", "2", "Monsoonal Rain", "50", "100000",
         _make_gpkg_point_polygon_blob(92.9, 26.2)),
    )
    # 3. Non-India
    conn.execute(
        "INSERT INTO combined_floods VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("5506", "Australia", "2024-01-06", "2024-01-09", "1.5", "Heavy rain", "0", "0",
         _make_gpkg_point_polygon_blob(153.0, -27.5)),
    )
    conn.commit()
    conn.close()

    res = data_pipeline.extract_indian_and_hyderabad_events(pd.DataFrame(), gpkg_path=str(gpkg))
    assert res["total_records"] == 3
    assert len(res["india_events"]) == 2
    assert len(res["hyderabad_300km_events"]) == 1
    assert len(res["hyderabad_100km_events"]) == 1
    assert res["hyderabad_100km_events"][0]["event_id"] == "4969"


def test_dataset_api_endpoints(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_ds.db")
    monkeypatch.setattr(database, "DATABASE_PATH", db_file)
    database.init_db(db_file)

    with TestClient(api.app) as client:
        st_resp = client.get("/api/dataset/status")
        assert st_resp.status_code == 200
        assert st_resp.json()["available"] is True
        assert st_resp.json()["record_count"] > 0

        hist_resp = client.get("/api/weather/historical/musi_riverfront?days=10")
        assert hist_resp.status_code == 200
        assert hist_resp.json()["zone_id"] == "musi_riverfront"
        assert len(hist_resp.json()["records"]) == 10
        assert hist_resp.json()["elevation_m"] == 503.0

        dl_resp = client.get("/api/dataset/download")
        assert dl_resp.status_code == 200
        assert "rainfall_24h" in dl_resp.text
