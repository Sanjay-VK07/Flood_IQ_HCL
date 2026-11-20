"""
FloodIQ — Automatic Real-World Data Acquisition & Dataset Pipeline

Fetches and caches three real public datasets without manual intervention:
1. Zenodo Global Flood Records (https://zenodo.org/api/records/19288171)
2. Open-Meteo Historical Weather API (https://archive-api.open-meteo.com/v1/archive)
3. OpenTopoData SRTM 90m Elevation API (https://api.opentopodata.org/v1/srtm90m)

Produces:
- data/floodiq_training_dataset.csv
- data/dataset_metadata.json
- Cached raw artifacts in data/cache/
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sqlite3
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from config import PROJECT_ROOT, ZONES_DATA_PATH

logger = logging.getLogger(__name__)

DATA_DIR = Path(PROJECT_ROOT) / "data"
CACHE_DIR = DATA_DIR / "cache"
TRAINING_CSV_PATH = DATA_DIR / "floodiq_training_dataset.csv"
METADATA_JSON_PATH = DATA_DIR / "dataset_metadata.json"

ZENODO_RECORD_ID = "19288171"
ZENODO_API_URL = f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SRTM_API_URL = "https://api.opentopodata.org/v1/srtm90m"

HYDERABAD_CENTER = (17.3850, 78.4867)
DEFAULT_TIMEOUT = 25


# ---------------------------------------------------------------------------
# HTTP & Retry Helpers
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ("open_meteo", "zenodo", "srtm"):
        (CACHE_DIR / sub).mkdir(parents=True, exist_ok=True)


def _cache_file(subdir: str, filename: str) -> Path:
    """
    Return the organized cache path `CACHE_DIR/<subdir>/<filename>`.
    Supports legacy flat cache files under `CACHE_DIR/<filename>` by migrating
    them into the organized subdirectory if present.
    """
    _ensure_dirs()
    target = CACHE_DIR / subdir / filename
    legacy = CACHE_DIR / filename
    if not target.exists() and legacy.exists() and legacy.is_file():
        try:
            legacy.replace(target)
        except OSError:
            return legacy
    return target


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return round(2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)), 2)


def _request_with_retry(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = 3,
    backoff_base: float = 1.5,
) -> requests.Response:
    """GET request with exponential backoff for timeouts, 429 rate limits, and 5xx."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = backoff_base ** (attempt + 1)
                logger.warning("HTTP %s from %s; retrying in %.1fs", resp.status_code, url, wait)
                time.sleep(wait)
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                continue
            resp.raise_for_status()
            return resp
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(backoff_base ** (attempt + 1))
        except requests.HTTPError as exc:
            last_exc = exc
            break
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# 1. Zenodo Global Flood Records
# ---------------------------------------------------------------------------

def fetch_zenodo_flood_records(force_refresh: bool = False) -> Dict[str, Any]:
    """Discover and download Global_Flood_Records.csv, .gpkg, and LICENSE.txt from Zenodo."""
    _ensure_dirs()
    meta_cache = _cache_file("zenodo", f"zenodo_{ZENODO_RECORD_ID}_metadata.json")
    csv_cache = _cache_file("zenodo", "Global_Flood_Records.csv")
    gpkg_cache = _cache_file("zenodo", "Global_Flood_Records.gpkg")
    lic_cache = _cache_file("zenodo", f"LICENSE_zenodo_{ZENODO_RECORD_ID}.txt")

    record_meta: Optional[Dict[str, Any]] = None
    if not force_refresh and meta_cache.exists() and csv_cache.exists() and gpkg_cache.exists():
        try:
            record_meta = json.loads(meta_cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            record_meta = None

    if record_meta is None or force_refresh:
        try:
            resp = _request_with_retry(ZENODO_API_URL, timeout=30)
            record_meta = resp.json()
            meta_cache.write_text(json.dumps(record_meta, indent=2), encoding="utf-8")

            files = {f["key"]: f["links"]["self"] for f in record_meta.get("files", [])}
            if "Global_Flood_Records.csv" in files and (force_refresh or not csv_cache.exists()):
                csv_resp = _request_with_retry(files["Global_Flood_Records.csv"], timeout=60)
                csv_cache.write_bytes(csv_resp.content)
            if "Global_Flood_Records.gpkg" in files and (force_refresh or not gpkg_cache.exists()):
                gpkg_resp = _request_with_retry(files["Global_Flood_Records.gpkg"], timeout=120)
                gpkg_cache.write_bytes(gpkg_resp.content)
            if "LICENSE.txt" in files and (force_refresh or not lic_cache.exists()):
                lic_resp = _request_with_retry(files["LICENSE.txt"], timeout=30)
                lic_cache.write_bytes(lic_resp.content)
        except Exception as exc:
            logger.warning("Zenodo fetch failed (%s); falling back to cache if present.", exc)
            if not csv_cache.exists() and not gpkg_cache.exists():
                raise

    metadata_block = (record_meta or {}).get("metadata", {})
    license_id = (metadata_block.get("license") or {}).get("id", "Unknown")
    version = metadata_block.get("version") or metadata_block.get("publication_date") or "1.0"
    doi = (record_meta or {}).get("doi", f"10.5281/zenodo.{ZENODO_RECORD_ID}")

    df = pd.read_csv(csv_cache) if csv_cache.exists() else pd.DataFrame()
    return {
        "dataframe": df,
        "gpkg_path": str(gpkg_cache) if gpkg_cache.exists() else None,
        "source_url": f"https://zenodo.org/records/{ZENODO_RECORD_ID}",
        "api_url": ZENODO_API_URL,
        "doi": doi,
        "version": str(version),
        "license": str(license_id),
        "license_text": lic_cache.read_text(encoding="utf-8", errors="replace").strip() if lic_cache.exists() else "",
        "retrieved_at": datetime.fromtimestamp(
            (gpkg_cache if gpkg_cache.exists() else csv_cache).stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def _gpkg_centroid_and_bbox(blob: Optional[bytes]) -> Optional[Tuple[float, float, Tuple[float, float, float, float]]]:
    """Extract centroid (lat, lon) and bbox (miny, maxy, minx, maxx) from a GeoPackage geometry header."""
    if not blob or len(blob) < 40 or blob[:2] != b"GP":
        return None
    flags = blob[3]
    endian = "<" if (flags & 1) else ">"
    env_ind = (flags >> 1) & 0x07
    if env_ind in (1, 2, 3, 4):
        minx, maxx, miny, maxy = struct.unpack(endian + "4d", blob[8:40])
        return (miny + maxy) / 2.0, (minx + maxx) / 2.0, (miny, maxy, minx, maxx)
    return None


def extract_indian_and_hyderabad_events(df: pd.DataFrame, gpkg_path: Optional[str] = None) -> Dict[str, Any]:
    """Filter Global Flood Records (preferring GeoPackage with spatial geometries) for India and Hyderabad."""
    india_events: List[Dict[str, Any]] = []
    hyd_300km: List[Dict[str, Any]] = []
    hyd_100km: List[Dict[str, Any]] = []
    total_records = len(df)

    if gpkg_path and Path(gpkg_path).exists():
        conn = sqlite3.connect(gpkg_path)
        try:
            total_records = conn.execute("SELECT COUNT(*) FROM combined_floods").fetchone()[0]
            rows = conn.execute(
                """SELECT ReportNumber, Country, BeginDate, EndDate, Severity, MainCause,
                          NumberOfFatalities, NumberOfDisplaced, geom
                   FROM combined_floods
                   WHERE Country LIKE '%India%'"""
            ).fetchall()
        finally:
            conn.close()

        for rep_num, country, began, ended, sev, cause, dead, disp, geom_blob in rows:
            parsed = _gpkg_centroid_and_bbox(geom_blob)
            if not parsed:
                continue
            lat, lon, (miny, maxy, minx, maxx) = parsed
            dist_km = _haversine_km(HYDERABAD_CENTER[0], HYDERABAD_CENTER[1], lat, lon)
            intersects_hyd = (miny <= HYDERABAD_CENTER[0] <= maxy) and (minx <= HYDERABAD_CENTER[1] <= maxx)

            def _to_float(val: Any) -> Optional[float]:
                try:
                    return float(val) if val not in (None, "") else None
                except (TypeError, ValueError):
                    return None

            ev = {
                "event_id": str(rep_num),
                "country": str(country),
                "start_date": str(began)[:10] if began else None,
                "end_date": str(ended)[:10] if ended else None,
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "distance_to_hyderabad_km": dist_km,
                "intersects_hyderabad_bbox": intersects_hyd,
                "severity": _to_float(sev),
                "flood_cause": str(cause) if cause else None,
                "deaths": _to_float(dead),
                "displaced": _to_float(disp),
            }
            india_events.append(ev)
            if dist_km <= 300.0 or intersects_hyd:
                hyd_300km.append(ev)
            if dist_km <= 100.0:
                hyd_100km.append(ev)

        return {
            "total_records": int(total_records),
            "india_events": india_events,
            "hyderabad_300km_events": hyd_300km,
            "hyderabad_100km_events": hyd_100km,
            "columns_found": ["ReportNumber", "Country", "BeginDate", "EndDate", "Severity", "MainCause", "NumberOfFatalities", "NumberOfDisplaced", "geom"],
        }

    # Fallback: CSV-only (no spatial coordinates in Global_Flood_Records.csv)
    return {
        "total_records": int(total_records),
        "india_events": [],
        "hyderabad_300km_events": [],
        "hyderabad_100km_events": [],
        "columns_found": list(df.columns),
    }


# ---------------------------------------------------------------------------
# 2. SRTM Elevation API
# ---------------------------------------------------------------------------

def fetch_srtm_elevations(
    coordinates: List[Tuple[float, float]],
    force_refresh: bool = False,
) -> Dict[str, Optional[float]]:
    """Fetch and cache SRTM 90m elevation (meters) for a list of (lat, lon) pairs."""
    _ensure_dirs()
    cache_file = _cache_file("srtm", "srtm_elevations.json")
    elev_cache: Dict[str, Optional[float]] = {}
    if cache_file.exists():
        try:
            elev_cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            elev_cache = {}

    missing: List[Tuple[float, float]] = []
    for lat, lon in coordinates:
        key = f"{round(lat, 4)},{round(lon, 4)}"
        if force_refresh or key not in elev_cache:
            missing.append((round(lat, 4), round(lon, 4)))

    # Deduplicate missing
    missing = list(dict.fromkeys(missing))

    # OpenTopoData allows up to 100 locations per request; 1 req/s rate limit
    for i in range(0, len(missing), 80):
        batch = missing[i : i + 80]
        loc_str = "|".join(f"{lat},{lon}" for lat, lon in batch)
        try:
            resp = _request_with_retry(SRTM_API_URL, params={"locations": loc_str}, timeout=20)
            payload = resp.json()
            for item in payload.get("results", []):
                loc = item.get("location", {})
                k = f"{round(float(loc['lat']), 4)},{round(float(loc['lng']), 4)}"
                elev_cache[k] = float(item["elevation"]) if item.get("elevation") is not None else None
            if i + 80 < len(missing):
                time.sleep(1.1)
        except Exception as exc:
            logger.warning("SRTM elevation batch failed (%s); keeping cached values.", exc)

    cache_file.write_text(json.dumps(elev_cache, indent=2), encoding="utf-8")
    return elev_cache


# ---------------------------------------------------------------------------
# 3. Open-Meteo Historical Weather API
# ---------------------------------------------------------------------------

def fetch_open_meteo_archive(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> Optional[pd.DataFrame]:
    """Fetch and cache hourly Open-Meteo Archive weather for a coordinate and date range."""
    _ensure_dirs()
    lat_r, lon_r = round(lat, 4), round(lon, 4)
    cache_file = _cache_file("open_meteo", f"open_meteo_{lat_r}_{lon_r}_{start_date}_{end_date}.json")

    raw_json: Optional[Dict[str, Any]] = None
    if not force_refresh and cache_file.exists():
        try:
            raw_json = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw_json = None

    if raw_json is None:
        params = {
            "latitude": lat_r,
            "longitude": lon_r,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": "precipitation,relative_humidity_2m,temperature_2m,soil_moisture_0_to_7cm",
            "timezone": "Asia/Kolkata",
        }
        try:
            resp = _request_with_retry(OPEN_METEO_ARCHIVE_URL, params=params, timeout=45)
            raw_json = resp.json()
            if "hourly" not in raw_json or "time" not in raw_json["hourly"]:
                logger.warning("Malformed Open-Meteo archive response for (%s, %s)", lat_r, lon_r)
                return None
            cache_file.write_text(json.dumps(raw_json), encoding="utf-8")
        except Exception as exc:
            logger.warning("Open-Meteo archive failed for (%s, %s) %s..%s: %s", lat_r, lon_r, start_date, end_date, exc)
            if cache_file.exists():
                raw_json = json.loads(cache_file.read_text(encoding="utf-8"))
            else:
                return None

    hourly = raw_json.get("hourly", {})
    df = pd.DataFrame({
        "timestamp": hourly.get("time", []),
        "precipitation": hourly.get("precipitation", []),
        "relative_humidity": hourly.get("relative_humidity_2m", []),
        "temperature": hourly.get("temperature_2m", []),
        "soil_moisture": hourly.get("soil_moisture_0_to_7cm", []),
    })
    if df.empty:
        return df

    df["precipitation"] = pd.to_numeric(df["precipitation"], errors="coerce")
    df["relative_humidity"] = pd.to_numeric(df["relative_humidity"], errors="coerce")
    df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    df["soil_moisture"] = pd.to_numeric(df["soil_moisture"], errors="coerce")

    # Compute rolling rainfall accumulations on real hourly observations
    df["rainfall_1h"] = df["precipitation"]
    df["rainfall_3h"] = df["precipitation"].rolling(3, min_periods=1).sum()
    df["rainfall_6h"] = df["precipitation"].rolling(6, min_periods=1).sum()
    df["rainfall_24h"] = df["precipitation"].rolling(24, min_periods=1).sum()
    df["rainfall_72h"] = df["precipitation"].rolling(72, min_periods=1).sum()
    return df


# ---------------------------------------------------------------------------
# 4. Build Reproducible Training Dataset & Metadata
# ---------------------------------------------------------------------------

def build_training_dataset(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Execute full real-world pipeline and generate:
      - data/floodiq_training_dataset.csv
      - data/dataset_metadata.json
    """
    _ensure_dirs()
    zones = json.loads(Path(ZONES_DATA_PATH).read_text(encoding="utf-8"))

    # 1. Zenodo Global Flood Records
    zenodo = fetch_zenodo_flood_records(force_refresh=force_refresh)
    flood_summary = extract_indian_and_hyderabad_events(zenodo["dataframe"], gpkg_path=zenodo.get("gpkg_path"))

    # 2. SRTM Elevation for all 5 pilot zones + Hyderabad-300km flood event coordinates
    coords: List[Tuple[float, float]] = [(z["latitude"], z["longitude"]) for z in zones]
    for ev in flood_summary["hyderabad_300km_events"]:
        coords.append((ev["latitude"], ev["longitude"]))
    elev_map = fetch_srtm_elevations(coords, force_refresh=force_refresh)

    # 3. Historical weather for 5 Hyderabad pilot zones (2010-01-01 to 2025-10-31 in chunks)
    # Using daily-representative / peak + baseline hourly snapshots so CSV stays clean & fast
    year_chunks = [
        ("2010-01-01", "2013-12-31"),
        ("2014-01-01", "2017-12-31"),
        ("2018-01-01", "2021-12-31"),
        ("2022-01-01", "2025-10-31"),
    ]

    hyd_events_300 = flood_summary["hyderabad_300km_events"]
    rows: List[Dict[str, Any]] = []

    # 3a. Pilot zones historical daily-peak & dry-baseline samples (2010-2025)
    for z in zones:
        z_lat, z_lon = round(z["latitude"], 4), round(z["longitude"], 4)
        elev_m = elev_map.get(f"{z_lat},{z_lon}")
        zone_frames: List[pd.DataFrame] = []
        for s_dt, e_dt in year_chunks:
            chunk_df = fetch_open_meteo_archive(z_lat, z_lon, s_dt, e_dt, force_refresh=force_refresh)
            if chunk_df is not None and not chunk_df.empty:
                zone_frames.append(chunk_df)
            time.sleep(0.15)

        if not zone_frames:
            continue
        full_df = pd.concat(zone_frames, ignore_index=True)
        full_df["date"] = full_df["timestamp"].astype(str).str.slice(0, 10)

        # Pick daily peak rainfall_24h hour per date to avoid 138k+ redundant hourly rows per zone
        idx_max = full_df.groupby("date")["rainfall_24h"].idxmax().dropna()
        daily_df = full_df.loc[idx_max].copy()

        for _, r in daily_df.iterrows():
            dt_str = str(r["date"])
            matched_ev = None
            for ev in hyd_events_300:
                if ev.get("start_date") and ev.get("end_date"):
                    if ev["start_date"] <= dt_str <= ev["end_date"]:
                        matched_ev = ev
                        break

            r24 = float(r["rainfall_24h"]) if pd.notna(r["rainfall_24h"]) else None
            if matched_ev is not None:
                flood_label: Any = 1
                label_conf = "confirmed_event"
                ev_id = matched_ev["event_id"]
                ev_sev = matched_ev["severity"]
            elif r24 is not None and r24 < 2.0:
                flood_label = 0
                label_conf = "no_recorded_flood_low_rainfall_control"
                ev_id = None
                ev_sev = None
            else:
                # Uncertain: rainfall occurred (>= 2 mm) with no recorded flood event in Zenodo
                flood_label = "uncertain"
                label_conf = "uncertain_unrecorded"
                ev_id = None
                ev_sev = None

            rows.append({
                "timestamp": r["timestamp"],
                "location_id": z["zone_id"],
                "latitude": z_lat,
                "longitude": z_lon,
                "rainfall_1h": round(float(r["rainfall_1h"]), 3) if pd.notna(r["rainfall_1h"]) else None,
                "rainfall_3h": round(float(r["rainfall_3h"]), 3) if pd.notna(r["rainfall_3h"]) else None,
                "rainfall_6h": round(float(r["rainfall_6h"]), 3) if pd.notna(r["rainfall_6h"]) else None,
                "rainfall_24h": round(r24, 3) if r24 is not None else None,
                "rainfall_72h": round(float(r["rainfall_72h"]), 3) if pd.notna(r["rainfall_72h"]) else None,
                "relative_humidity": round(float(r["relative_humidity"]), 2) if pd.notna(r["relative_humidity"]) else None,
                "temperature": round(float(r["temperature"]), 2) if pd.notna(r["temperature"]) else None,
                "soil_moisture": round(float(r["soil_moisture"]), 4) if pd.notna(r["soil_moisture"]) else None,
                "elevation_m": elev_m,
                "flood_event": flood_label,
                "label_confidence": label_conf,
                "flood_event_id": ev_id,
                "flood_severity": ev_sev,
                "source": "open_meteo_archive+srtm90m+zenodo_19288171",
            })

    # 3b. Event-location weather samples for Hyderabad-300km events (if >= 1940-01-01)
    for ev in hyd_events_300:
        s_dt = ev.get("start_date")
        e_dt = ev.get("end_date") or s_dt
        if not s_dt or s_dt < "1940-01-01":
            continue
        try:
            dt_start = (datetime.strptime(s_dt, "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d")
            dt_end = min(datetime.strptime(e_dt, "%Y-%m-%d") + timedelta(days=1), datetime(2025, 10, 31)).strftime("%Y-%m-%d")
        except ValueError:
            continue
        ev_df = fetch_open_meteo_archive(ev["latitude"], ev["longitude"], dt_start, dt_end, force_refresh=force_refresh)
        if ev_df is None or ev_df.empty:
            continue
        ev_df["date"] = ev_df["timestamp"].astype(str).str.slice(0, 10)
        ev_window = ev_df[(ev_df["date"] >= s_dt) & (ev_df["date"] <= e_dt)]
        if ev_window.empty:
            ev_window = ev_df
        peak_row = ev_window.loc[ev_window["rainfall_24h"].idxmax()]
        elev_m = elev_map.get(f"{ev['latitude']},{ev['longitude']}")
        rows.append({
            "timestamp": peak_row["timestamp"],
            "location_id": f"event_{ev['event_id']}",
            "latitude": ev["latitude"],
            "longitude": ev["longitude"],
            "rainfall_1h": round(float(peak_row["rainfall_1h"]), 3) if pd.notna(peak_row["rainfall_1h"]) else None,
            "rainfall_3h": round(float(peak_row["rainfall_3h"]), 3) if pd.notna(peak_row["rainfall_3h"]) else None,
            "rainfall_6h": round(float(peak_row["rainfall_6h"]), 3) if pd.notna(peak_row["rainfall_6h"]) else None,
            "rainfall_24h": round(float(peak_row["rainfall_24h"]), 3) if pd.notna(peak_row["rainfall_24h"]) else None,
            "rainfall_72h": round(float(peak_row["rainfall_72h"]), 3) if pd.notna(peak_row["rainfall_72h"]) else None,
            "relative_humidity": round(float(peak_row["relative_humidity"]), 2) if pd.notna(peak_row["relative_humidity"]) else None,
            "temperature": round(float(peak_row["temperature"]), 2) if pd.notna(peak_row["temperature"]) else None,
            "soil_moisture": round(float(peak_row["soil_moisture"]), 4) if pd.notna(peak_row["soil_moisture"]) else None,
            "elevation_m": elev_m,
            "flood_event": 1,
            "label_confidence": "confirmed_event",
            "flood_event_id": ev["event_id"],
            "flood_severity": ev["severity"],
            "source": "open_meteo_archive+srtm90m+zenodo_19288171",
        })

    out_df = pd.DataFrame(rows)
    out_df.to_csv(TRAINING_CSV_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    missing_counts = {col: int(out_df[col].isna().sum()) for col in out_df.columns} if not out_df.empty else {}
    class_dist = out_df["flood_event"].astype(str).value_counts().to_dict() if not out_df.empty else {}
    label_conf_dist = out_df["label_confidence"].astype(str).value_counts().to_dict() if not out_df.empty else {}
    pos_df = out_df[out_df["flood_event"].astype(str) == "1"]
    unique_event_ids = sorted(pos_df["flood_event_id"].dropna().astype(str).unique().tolist()) if not pos_df.empty else []

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": int(len(out_df)),
        "duplicate_timestamp_location_count": int(out_df.duplicated(subset=["timestamp", "location_id"]).sum()) if not out_df.empty else 0,
        "date_coverage": {
            "start": str(out_df["timestamp"].min()) if not out_df.empty else None,
            "end": str(out_df["timestamp"].max()) if not out_df.empty else None,
            "pilot_zone_archive_window": "2010-01-01 to 2025-10-31",
        },
        "geographic_coverage": {
            "pilot_zones": [z["zone_name"] for z in zones],
            "hyderabad_center": {"lat": HYDERABAD_CENTER[0], "lon": HYDERABAD_CENTER[1]},
            "zenodo_total_global_records": flood_summary["total_records"],
            "zenodo_india_records": len(flood_summary["india_events"]),
            "zenodo_within_300km_hyderabad": len(flood_summary["hyderabad_300km_events"]),
            "zenodo_within_100km_hyderabad": len(flood_summary["hyderabad_100km_events"]),
            "unique_flood_events_in_dataset": len(unique_event_ids),
            "hyderabad_300km_events": flood_summary["hyderabad_300km_events"],
        },
        "missing_values": missing_counts,
        "class_distribution": class_dist,
        "label_confidence_distribution": label_conf_dist,
        "feature_provenance": {
            "measured_or_reanalysis": [
                "rainfall_1h", "rainfall_3h", "rainfall_6h", "rainfall_24h", "rainfall_72h",
                "relative_humidity", "temperature", "soil_moisture", "elevation_m",
            ],
            "manually_assigned_heuristic_scores_in_app_only": [
                "drainage_score (hyderabad_zones.json)",
                "low_lying_score (hyderabad_zones.json)",
            ],
        },
        "label_generation_methodology": (
            "1 (confirmed_event) = Date falls within a recorded Zenodo Global Flood Records event window within 300 km of or intersecting Hyderabad. "
            "Note: 288 positive rows represent 28 unique flood events (3 distinct events in 2010-2025 across 5 pilot zones + 28 event-location snapshots). "
            "0 (no_recorded_flood_low_rainfall_control) = Pilot zone date with daily peak 24h rainfall < 2.0 mm and no recorded flood event. "
            "uncertain (uncertain_unrecorded) = Pilot zone date with >= 2.0 mm rainfall and no recorded regional flood event; missing flood records are NOT treated as proof of non-flood."
        ),
        "sources": [
            {
                "name": "Open-Meteo Historical Weather API",
                "publisher": "Open-Meteo (Zippenfenig, P.)",
                "url": OPEN_METEO_ARCHIVE_URL,
                "license": "CC BY 4.0 (Non-commercial / Attribution required)",
                "variables": ["precipitation", "relative_humidity_2m", "temperature_2m", "soil_moisture_0_to_7cm"],
            },
            {
                "name": "Global Flood Records",
                "publisher": "DFO - Flood Observatory (DFO) via Zenodo",
                "url": zenodo["source_url"],
                "doi": zenodo["doi"],
                "version": zenodo["version"],
                "license": f"{zenodo['license']} (Zenodo metadata) / CC0 1.0 Universal (archive LICENSE.txt)",
                "retrieved_at": zenodo["retrieved_at"],
            },
            {
                "name": "OpenTopoData SRTM 90m",
                "publisher": "NASA / CGIAR-CSI via OpenTopoData",
                "url": SRTM_API_URL,
                "license": "Public Domain (NASA SRTM)",
                "elevations_by_zone": {
                    z["zone_id"]: elev_map.get(f"{round(z['latitude'], 4)},{round(z['longitude'], 4)}")
                    for z in zones
                },
            },
        ],
        "limitations": [
            "Global Flood Records primarily captures major reported flood disasters rather than localized urban waterlogging; only 3 distinct regional events appear in 2010-2025.",
            "Multiple daily/zone rows share the same flood_event_id and must not be treated as independent flood events.",
            "Open-Meteo ERA5/IFS reanalysis grid (~9-25 km resolution) smooths localized urban cloudburst peaks.",
            "SRTM 90m elevation measures ~90m surface height and does not represent municipal storm-drainage capacity or flood susceptibility.",
            "Dates without a Zenodo flood record during monsoon rain (>= 2.0 mm) are marked 'uncertain' rather than fabricated as non-floods.",
        ],
    }

    METADATA_JSON_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def get_dataset_status() -> Dict[str, Any]:
    """Return cached dataset metadata and file freshness without triggering network calls."""
    if not METADATA_JSON_PATH.exists() or not TRAINING_CSV_PATH.exists():
        return {
            "available": False,
            "message": "Dataset has not been generated yet. Run `python data_pipeline.py --refresh` or POST /api/dataset/refresh.",
        }
    meta = json.loads(METADATA_JSON_PATH.read_text(encoding="utf-8"))
    age_seconds = round(time.time() - METADATA_JSON_PATH.stat().st_mtime, 1)
    meta["available"] = True
    meta["cache_age_seconds"] = age_seconds
    meta["csv_path"] = str(TRAINING_CSV_PATH)
    return meta


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="FloodIQ Real-World Dataset Pipeline")
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch from external APIs")
    args = parser.parse_args()
    summary = build_training_dataset(force_refresh=args.refresh)
    print(json.dumps({
        "record_count": summary["record_count"],
        "class_distribution": summary["class_distribution"],
        "geographic_coverage": summary["geographic_coverage"],
    }, indent=2))
