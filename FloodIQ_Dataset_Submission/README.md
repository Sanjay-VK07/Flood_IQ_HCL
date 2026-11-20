# FloodIQ Dataset Submission Package

Reproducible, audited real-world dataset package for the FloodIQ urban flood-risk prototype (Hyderabad pilot).

## Dataset Summary
- **Total Rows:** `28,943`
- **Date Coverage:** `1986-08-15T00:00` to `2025-10-31T00:00`
- **Duplicate `(timestamp, location_id)` Rows:** `0`
- **Positive Row Reconciliation (`flood_event = 1`):** `288` rows = `28` event-location snapshots (28 unique `flood_event_id`s) + `260` pilot-zone daily rows from `3` distinct regional events in 2010–2025 (`4198`: 80, `4405`: 130, `4969`: 50).
- **Class Distribution:** `1` (`confirmed_event`): `288` | `0` (`no_recorded_flood_low_rainfall_control`): `19,981` | `uncertain` (`uncertain_unrecorded`): `8,674`
- **Zenodo Licence Disclosure:** Zenodo metadata declares `CC BY 4.0`, while archive `LICENSE.txt` states `CC0 1.0 Universal`. Conservative `CC BY 4.0` attribution is applied in `LICENSE_AND_ATTRIBUTION.md`.

## Regeneration Command
```bash
python data_pipeline.py --refresh
```

## Package Files & SHA-256 Checksums
| File | SHA-256 |
|---|---|
| `data_pipeline.py` | `b6a405d59ffaf8ab7db8ca368546708557c5877e41f98f48243e5270a8eaee82` |
| `dataset_metadata.json` | `1de707d0fd48ec82b57cc35387462679e5c599599d0e461ae6d6f7cb3ed648bc` |
| `dataset_sources.md` | `9653ef293596349ba055c100084e06981a505a6c4a5653d67e8d5a924a1d6e77` |
| `floodiq_training_dataset.csv` | `cb74b01213c2314da24b58870199afd78749f247691f9118d7d062ed52fb4354` |
| `LICENSE_AND_ATTRIBUTION.md` | `4870aa6f57edad1277aef3c0183d50337bfb48318374c31f3946d3c20cb242d9` |
| `methodology.pdf` | `2ee5cf953abaf2d6361fd99e884dd9cf6643f32af4687c07316c944e7a3e8fb7` |
