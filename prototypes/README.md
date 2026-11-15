# Prototypes (superseded)

First scripts written by Tracks B and C during the hackathon. Their logic now lives in `pipeline/`:

| Prototype | Replaced by |
|---|---|
| `water_detection/polygone.py`, `SARingestion/polygone.py` | `pipeline/02_search_download.py` + `pipeline/utils/nisar.py` |
| `water_detection/water_detection.py` | `pipeline/03_preprocess.py`, `04_detect_water.py`, `05_monthly_composite.py` + `pipeline/utils/sar.py` |
| `water_detection/sentinel1_gee.py` | `pipeline/06_baseline_s1_gee.py` (Earth Engine) and `06_baseline_s1_pc.py` (Planetary Computer) |
| `SARingestion/ouvrir_npz.py` | `notebooks/00_explore_gcov.ipynb` |

Kept for reference only; they are not maintained.
