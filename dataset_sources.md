# FloodIQ — Real-World Dataset Sources, Provenance & Methodology

## 1. Data Provenance & Attribution

| Dataset Title | Publisher & Authors | Original URL / DOI | Coverage | Licence & Attribution |
|---|---|---|---|---|
| **Open-Meteo Historical Weather API** | Open-Meteo (Patrick Zippenfenig; ERA5 / ECMWF reanalysis) | `https://archive-api.open-meteo.com/v1/archive` | 5 Hyderabad pilot zones (`2010-01-01` to `2025-10-31`) + 28 regional event windows | **CC BY 4.0** (Non-commercial; attribution: *Weather data by Open-Meteo.com*) |
| **Global Flood Records** | DFO - Flood Observatory (DFO), hosted on Zenodo (`2026-03-28`) | `https://zenodo.org/records/19288171` (DOI: `10.5281/zenodo.19288171`) | `5,503` global records; `316` in India; `28` within 300 km / intersecting Hyderabad (`3` within 100 km) | **Discrepancy Disclosed:** Zenodo API `metadata.license.id` = `cc-by-4.0` (`access_right: open`, `rights: null`), while archive `LICENSE.txt` = `CC0 1.0 Universal`. **Conservative CC BY 4.0 attribution recommended.** |
| **SRTM 90m Digital Elevation** | NASA / CGIAR-CSI via OpenTopoData | `https://api.opentopodata.org/v1/srtm90m` | 5 Hyderabad pilot zones (`503 m` – `574 m`) + 28 regional event coordinates | **Public Domain** (NASA SRTM) |

## 2. Measured Features vs. Heuristic Scores
- **Measured / Reanalysis Features (in `floodiq_training_dataset.csv`):** `rainfall_1h`, `rainfall_3h`, `rainfall_6h`, `rainfall_24h`, `rainfall_72h`, `relative_humidity`, `temperature`, `soil_moisture` (Open-Meteo Archive), and `elevation_m` (SRTM 90m).
- **Manually Assigned Heuristic Scores (in `data/hyderabad_zones.json` only, NOT in training CSV):** `drainage_score` and `low_lying_score` are illustrative prototype weights used by `risk_engine.py`.
- **SRTM 90m Limitation:** SRTM 90m provides ~90 m horizontal terrain height only. Absolute elevation does **not** equate to flood susceptibility and does not capture local micro-topography, storm drains, or culverts.

## 3. Label Integrity & Terminology (`flood_event` & `label_confidence`)
- **`1` (`confirmed_event` — 288 rows):** Reconciles exactly as **28 event-location peak snapshots** (1 per unique `flood_event_id`) + **260 pilot-zone daily rows** from the **3 distinct regional events in 2010–2025** (`4198`: 16 days × 5 zones = 80; `4405`: 26 days × 5 zones = 130; `4969`: 10 days × 5 zones = 50). Multiple rows from the same event share `flood_event_id` and must **not** be treated as independent flood events.
- **`0` (`no_recorded_flood_low_rainfall_control` — 19,981 rows):** Pilot zone date with daily peak `rainfall_24h < 2.0 mm` and no recorded regional flood event.
- **`uncertain` (`uncertain_unrecorded` — 8,674 rows):** Pilot zone date with `rainfall_24h >= 2.0 mm` and no Zenodo disaster record. Missing flood records are **never** treated as proof that no flood occurred.

### Event-Level Reconciliation Table (28 Unique `flood_event_id` Values = 288 Positive Rows)
| Event ID | Start Date | End Date | Centroid (Lat, Lon) | Dist to Hyd (km) | Cause | Event Snapshot | Pilot-Zone Rows | Total Rows |
|---|---|---|---|---|---|---|---|---|
| `98` | 1986-08-15 | 1986-08-22 | 17.4331, 80.187 | 180.48 | Monsoonal rain | 1 | 0 | 1 |
| `214` | 1988-07-31 | 1988-08-02 | 18.4311, 80.713 | 262.71 | Heavy rain | 1 | 0 | 1 |
| `330` | 1989-07-22 | 1989-07-31 | 15.1816, 79.5671 | 270.78 | Monsoonal rain | 1 | 0 | 1 |
| `411` | 1990-05-10 | 1990-05-13 | 16.2843, 80.6926 | 264.76 | Tropical cyclone | 1 | 0 | 1 |
| `598` | 1991-11-13 | 1991-11-18 | 14.0025, 79.4752 | 390.72 | Heavy rain | 1 | 0 | 1 |
| `694` | 1992-09-12 | 1992-11-20 | 13.0242, 78.8487 | 486.45 | Tropical cyclone | 1 | 0 | 1 |
| `855` | 1994-07-01 | 1994-07-24 | 22.0806, 76.4506 | 563.91 | Monsoonal rain | 1 | 0 | 1 |
| `1027` | 1995-10-20 | 1995-10-23 | 16.4132, 80.612 | 250.61 | Tropical cyclone | 1 | 0 | 1 |
| `1125` | 1996-10-21 | 1996-10-25 | 15.4474, 79.1569 | 227.0 | Heavy rain | 1 | 0 | 1 |
| `1256` | 1997-07-05 | 1997-07-22 | 13.3154, 76.3598 | 506.71 | Monsoonal rain | 1 | 0 | 1 |
| `1295` | 1997-12-04 | 1997-12-09 | 13.8493, 80.5931 | 453.24 | Monsoonal rain | 1 | 0 | 1 |
| `1457` | 1998-10-01 | 1998-10-20 | 16.1464, 81.1138 | 311.76 | Heavy rain | 1 | 0 | 1 |
| `1623` | 2000-08-23 | 2000-08-31 | 17.1335, 79.2098 | 81.72 | Torrential rain | 1 | 0 | 1 |
| `1803` | 2001-09-30 | 2001-10-02 | 16.746, 79.1214 | 97.99 | Torrential rain | 1 | 0 | 1 |
| `1811` | 2001-10-16 | 2001-10-21 | 14.8405, 78.9741 | 287.69 | Heavy rain | 1 | 0 | 1 |
| `2312` | 2003-07-29 | 2003-08-03 | 19.1881, 79.2948 | 217.9 | Monsoonal Rain and Dam Break | 1 | 0 | 1 |
| `2698` | 2005-07-23 | 2005-08-16 | 16.3304, 78.0916 | 124.58 | Monsoonal rain | 1 | 0 | 1 |
| `2728` | 2005-09-14 | 2005-09-30 | 18.9485, 82.6626 | 474.19 | Heavy rain | 1 | 0 | 1 |
| `2844` | 2006-04-15 | 2006-04-18 | 16.0744, 81.3674 | 339.61 | Heavy rain | 1 | 0 | 1 |
| `2935` | 2006-07-28 | 2006-09-12 | 21.1427, 73.6095 | 660.71 | Monsoonal rain | 1 | 0 | 1 |
| `2940` | 2006-08-01 | 2006-09-10 | 19.2428, 82.95 | 514.42 | Monsoonal rain | 1 | 0 | 1 |
| `2965` | 2006-09-18 | 2006-10-05 | 20.6822, 83.7466 | 663.31 | Monsoonal rain | 1 | 0 | 1 |
| `3107` | 2007-06-22 | 2007-07-04 | 14.945, 78.1615 | 273.53 | Monsoonal rain | 1 | 0 | 1 |
| `3191` | 2007-09-16 | 2007-10-07 | 15.7067, 79.878 | 238.36 | Monsoonal rain | 1 | 0 | 1 |
| `3551` | 2009-09-25 | 2009-10-12 | 15.7081, 78.233 | 188.41 | Heavy rain | 1 | 0 | 1 |
| `4198` | 2014-10-12 | 2014-10-27 | 18.4473, 79.6967 | 174.19 | Tropical Storm Hudhug | 1 | 80 | 81 |
| `4405` | 2016-09-21 | 2016-10-16 | 17.6536, 80.3401 | 198.78 | Monsoonal Rain | 1 | 130 | 131 |
| `4969` | 2020-10-16 | 2020-10-25 | 17.3444, 78.8637 | 40.26 | Monsoonal Rain | 1 | 50 | 51 |
| **TOTAL (28 unique events)** | — | — | — | — | — | **28** | **260** | **288** |

## 4. Modeling Decision
Because only **3 distinct regional flood events** appear in 2010–2025 and `0` controls are separated from `uncertain` monsoon days by a `2.0 mm` rainfall threshold, supervised ML training is **not** justified. FloodIQ retains its explainable heuristic (`R = 0.40P + 0.30D + 0.30L`) enriched with real SRTM elevation and historical Open-Meteo context.
