# License & Attribution — FloodIQ Dataset Submission

## 1. Global Flood Records (Zenodo Record 19288171) — Licence Discrepancy Disclosure
- **Title:** Global Flood Records
- **Authors / Publisher:** DFO - Flood Observatory (DFO), hosted via Zenodo (Publication Date: `2026-03-28`)
- **DOI / URL:** `https://doi.org/10.5281/zenodo.19288171` (`https://zenodo.org/records/19288171`)
- **Observed Licence Discrepancy:**
  - **Zenodo API Metadata (`metadata.license.id`):** `cc-by-4.0` (`access_right: open`, `rights: null`).
  - **Downloaded `LICENSE.txt` inside the Zenodo archive:** `CC0 1.0 Universal` (Public Domain Dedication).
- **Resolution & Recommendation:** Because this discrepancy between the repository metadata (`CC BY 4.0`) and the bundled `LICENSE.txt` (`CC0 1.0`) cannot be conclusively resolved from the archive alone, FloodIQ discloses both and **recommends conservative CC BY 4.0 attribution** pending clarification from the upstream publisher (*DFO - Flood Observatory*):
  > *Global Flood Records, DFO - Flood Observatory (DFO), Zenodo (2026-03-28), DOI: 10.5281/zenodo.19288171.*

## 2. Open-Meteo Historical Weather API
- **Title:** Open-Meteo Historical Weather API (ERA5 / ECMWF Reanalysis)
- **Publisher:** Open-Meteo (Patrick Zippenfenig)
- **URL:** `https://archive-api.open-meteo.com/v1/archive`
- **Licence:** **Creative Commons Attribution 4.0 International (CC BY 4.0)** (Non-commercial usage supported without API key)
- **Required Attribution:**
  > *Weather data by Open-Meteo.com (https://open-meteo.com/).*

## 3. SRTM 90m Digital Elevation Model (via OpenTopoData)
- **Title:** Shuttle Radar Topography Mission (SRTM) 90m DEM
- **Publisher:** NASA / CGIAR-CSI, served via OpenTopoData (`https://api.opentopodata.org/v1/srtm90m`)
- **Licence:** **Public Domain** (NASA SRTM)
- **Attribution:**
  > *Elevation data from NASA SRTM 90m via OpenTopoData.*

## 4. FloodIQ Pipeline & Derived Dataset
- **Pipeline Code (`data_pipeline.py`):** MIT License (FloodIQ Hackathon Prototype).
- **Derived Dataset (`floodiq_training_dataset.csv`):** Distributed with full upstream **CC BY 4.0** attribution as above.
