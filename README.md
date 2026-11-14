# nasa_space_apps_project
# 🌊 SaddSAR

**Radar-based monitoring of lakes and reservoirs: Morocco prototype → global water monitoring**

> *AquaPulse uses NISAR radar to monitor Morocco's lakes and reservoirs every month, tracking how much water they hold and flagging drought early, whatever the weather.*

Built for the **2026 NASA Space Apps Challenge**, challenge: [**Dancing with the SARs**](https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/).

---

## 📑 Table of contents

1. [Overview](#-overview)
2. [The problem](#-the-problem)
3. [Our solution](#-our-solution)
4. [Key features](#-key-features)
5. [Why radar (SAR)?](#-why-radar-sar)
6. [Data sources](#-data-sources)
7. [Methodology](#-methodology)
8. [System architecture](#-system-architecture)
9. [Tech stack](#-tech-stack)
10. [Repository structure](#-repository-structure)
11. [Getting started](#-getting-started)
12. [Team workstreams](#-team-workstreams)
13. [Interface contracts](#-interface-contracts)
14. [Task list (parallel tracks)](#-task-list)
15. [Validation plan](#-validation-plan)
16. [Known limitations & risks](#-known-limitations--risks)
17. [Roadmap: from Morocco to the world](#-roadmap-from-morocco-to-the-world)
18. [License](#-license)
19. [Acknowledgments & references](#-acknowledgments--references)

---

## 🔭 Overview

AquaPulse is an **open-source, interactive web GIS** that monitors the surface water stored in lakes, dams and reservoirs. For each water body it:

1. **Identifies** it using public reservoir and lake polygon datasets.
2. **Analyzes** a time series of radar images (NISAR L-band + Sentinel-1 C-band) to map its water extent each month.
3. **Compares** the current water area with its long-term normal for that month.
4. **Presents** the results on an interactive web map with time sliders, charts, comparisons and status alerts.

The **hackathon prototype covers Morocco's national reservoirs**. The architecture works per polygon so it can be **extended to global monitoring** without changing the core algorithm.

---

## ❗ The problem

- Water is one of Morocco's most critical resources. Recent years brought severe drought, with national dam storage falling to historic lows, followed by a strong recovery in 2026. Conditions vary sharply between basins: the north fills up while the south stays under stress.
- Official dam statistics exist in some countries (e.g. Morocco's *Al Maa Dialna* platform), but **most reservoirs worldwide have no public, timely storage data**.
- Optical satellites (e.g. Landsat, Sentinel-2) can map water, but **clouds block them**, often during the rainy season, exactly when reservoirs refill.
- Raw radar data is powerful but **hard for non-specialists to use and interpret**.

## 💡 Our solution

AquaPulse turns complex radar observations into **simple, actionable water information**:

- **How much surface water does each reservoir hold this month?**
- **Is that above, near, or below normal for this time of year?**
- **Is it rising or falling, and how fast?**
- **Where in the country is water stress concentrated?**

Drought is one output of the monitoring system: an alert raised when a reservoir is significantly below normal.

---

## ✨ Key features

### Core (hackathon MVP)
- 🗺️ **Interactive national map** of Moroccan reservoirs and lakes, colored by water status.
- 🎚️ **Monthly time slider** animating water extents across the country.
- 📈 **Reservoir detail panel**: name, basin, capacity, monthly water-area time series against the normal range.
- 🚦 **Two-sided status classification**:

  | Status | Meaning (percent of normal area for that month) |
  |---|---|
  | 🔵 Above normal | > 110% |
  | 🟢 Normal | 90–110% |
  | 🟡 Below normal (watch) | 75–90% |
  | 🟠 Drought | 50–75% |
  | 🔴 Severe drought | < 50% |
  | ⚪ No data / low confidence | insufficient observations or reservoir too small |

  *(Thresholds are initial values and will be tuned during validation.)*

- ↔️ **Before/after swipe comparison** (e.g. the same reservoir in 2025 vs 2026).
- 🧭 **Layer control**: reservoirs, basins, water extents, basemaps (optical / radar).
- 🔍 **Search & filter** by name, basin, size or status.
- 📚 **"How radar sees water" explainer** for the general public.

### Extended (stretch goals)
- 🏞️ **Basin-level dashboard** with aggregated storage indicators.
- 🌧️ **Rainfall anomaly overlay** (CHIRPS / GPM) to separate climate causes from human ones (irrigation, dam releases).
- 💧 **Area → % full / volume estimation** using area–storage curves calibrated against official fill rates.
- 🛰️ **SWOT water surface elevation** integration for volume change.
- 🌱 **NISAR soil moisture (SME2)** as an early drought signal.
- 📥 **Data export** (CSV / GeoJSON) and a simple public API.
- 🔔 **Alerts** when a reservoir changes status.

---

## 📡 Why radar (SAR)?

- **Works through clouds, day and night.** Radar is an *active* sensor: it supplies its own microwave energy.
- **Water is easy to detect.** Calm water reflects the radar pulse away from the satellite like a mirror, so it appears **very dark**. Land scatters energy back and appears brighter.
- **Regular revisits.** NISAR images each spot about every **12 days**, giving 2–3 observations per month.
- **L-band advantage.** NISAR's long wavelength helps separate open water, flooded vegetation and land, and can detect water beneath vegetation canopies.

---

## 🗂️ Data sources

| Dataset | Purpose | Access |
|---|---|---|
| **NISAR L2 GCOV** (L-band, HH/HV) | Main radar input for water detection | [ASF Vertex](https://search.asf.alaska.edu/#/?dataset=NISAR), `asf_search`, [Earthdata Search](https://search.earthdata.nasa.gov), AWS S3 |
| **NISAR L3 SME2** | Soil moisture (stretch goal) | ASF DAAC |
| **Sentinel-1 GRD** (C-band, VV/VH) | Long-term baseline (2015 → present) | Google Earth Engine `COPERNICUS/S1_GRD` |
| **Global Dam Watch (GDW) v1.0** | Reservoir polygons + attributes (capacity, height, year, purpose) | [Figshare](https://doi.org/10.6084/m9.figshare.25988293), GEE `projects/sat-io/open-datasets/GDW/GDW_RESERVOIRS_V1_0` |
| **HydroLAKES** | Natural lake polygons (≥ 10 ha) | [HydroSHEDS](https://www.hydrosheds.org/products/hydrolakes) |
| **OpenStreetMap** | Recent dams / reservoirs missing from GDW | Overpass API / Geofabrik |
| **JRC Global Surface Water** | Maximum water extent → search zone | GEE `JRC/GSW1_4/GlobalSurfaceWater` |
| **MERIT Hydro (HAND)** or Copernicus DEM | Terrain mask to remove false water | GEE `MERIT/Hydro/v1_0_1` |
| **Sentinel-2 L2A** | Optical validation (NDWI) on clear days | GEE `COPERNICUS/S2_SR_HARMONIZED` |
| **CHIRPS / GPM IMERG** | Rainfall anomalies (context) | GEE `UCSB-CHG/CHIRPS/DAILY`, NASA GES DISC |
| **SWOT LakeSP** | Lake water surface elevation (stretch) | [PO.DAAC](https://podaac.jpl.nasa.gov/SWOT) |
| **Al Maa Dialna** (Moroccan Ministry of Equipment and Water) | Official dam fill rates → ground truth | Public platform |
| **Basin boundaries** (HydroBASINS / national river basin agencies) | Basin aggregation | HydroSHEDS |

> **Accounts needed:** NASA Earthdata Login (free), Google Earth Engine (free for non-commercial use).

---

## 🔬 Methodology

### 1. Reservoir identification
1. Load GDW reservoir polygons and HydroLAKES lakes for Morocco.
2. Merge, deduplicate (spatial overlap), and add recent dams from OSM.
3. Attach attributes: name, basin, capacity (Mm³), dam year, polygon area.
4. Build an **analysis zone** for each water body = polygon ∪ JRC maximum water extent, buffered by ~500 m, so the water can be measured even when it rises above the original outline.
5. Flag small reservoirs (< ~0.5 km²) as **low confidence**, since too few radar pixels cover them.

### 2. Radar preprocessing (per scene, per reservoir)
1. Search NISAR GCOV scenes that intersect the analysis zone (`asf_search`).
2. Read HH and HV backscatter from the HDF5 file (e.g. `/science/LSAR/GCOV/grids/frequencyA/HHHH`; verify with `h5ls -r`).
3. Clip to the analysis zone plus a land buffer (needed so the histogram has both water and land peaks).
4. Convert linear power to decibels: `dB = 10·log10(σ⁰)`.
5. Apply a speckle filter (Lee or 5×5 median).
6. Mask layover/shadow pixels using the GCOV mask layer (important for mountain dams in the Atlas and Rif).
7. Prefer a consistent orbit direction (ascending or descending) per reservoir.

### 3. Water detection
1. **Otsu thresholding** on HH (dB) within the clip to find the water/land split automatically.
2. **False-positive filters:**
   - Search zone (JRC max extent + buffer).
   - **HAND > 15–20 m** → not water.
   - **HV check** to reject dry sand, smooth soil and tarmac (critical in arid southern basins).
3. **Morphological cleanup** (opening/closing), remove small isolated blobs, keep connected components that intersect the reservoir.
4. Output: binary water mask per scene + water area (km²).

### 4. Monthly compositing
- **Majority vote** per pixel across all scenes in a month (water if detected in ≥ 50% of observations).
- Removes one-off errors (wind roughening, noise).
- Output: one water-extent GeoTIFF + one area value per reservoir per month.

### 5. Baseline & status
1. Run the same method on **Sentinel-1 (2015 → present)** to build a long-term monthly baseline.
2. **Harmonize sensors:** in overlapping months, compare NISAR and Sentinel-1 areas and correct for any consistent offset.
3. For each reservoir and calendar month, compute the mean and standard deviation of area.
4. **Anomaly:** `percent_of_normal = area / mean_area_for_month × 100` and `z = (area − mean) / std`.
5. Classify status using the thresholds in [Key features](#-key-features).
6. Compute the **trend** (change vs previous month and vs same month last year).

### 6. Area → storage (stretch goal)
- For reservoirs with official fill-rate data, fit an **area–storage curve** (e.g. power law `V = a·Aᵇ`) between SAR area and official stored volume.
- Use it to estimate **% full** for reservoirs without official data.
- Add SWOT water-height changes where available: `ΔV ≈ ((A₁ + A₂) / 2) × Δh`.

---

## 🏗️ System architecture

```
┌─────────────────────────── OFFLINE PROCESSING (Python) ───────────────────────────┐
│                                                                                    │
│  Polygons (GDW, HydroLAKES, OSM)                                                   │
│            │                                                                       │
│            ▼                                                                       │
│  Reservoir catalog ──► NISAR / Sentinel-1 search & download ──► Preprocess         │
│                                                                    │               │
│                                                                    ▼               │
│                 Status & anomaly ◄── Monthly composite ◄── Water detection         │
│                        │                                                           │
└────────────────────────┼───────────────────────────────────────────────────────────┘
                         ▼
           Static outputs: reservoirs.geojson / PMTiles,
           water extents (COG / PNG), timeseries/*.json
                         │
                         ▼
┌────────────────────────────── WEB APP (static hosting) ───────────────────────────┐
│  MapLibre GL map · layer control · time slider · swipe · charts · explainer        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

- **Prototype:** all processing runs offline; the website is fully static (GitHub Pages / Netlify). No server or database needed.
- **Automation:** a scheduled GitHub Actions workflow can rerun the pipeline monthly.

---

## 🧰 Tech stack

| Layer | Tools |
|---|---|
| Data access | `asf_search`, `earthaccess`, Google Earth Engine Python API (`earthengine-api`, `geemap`) |
| Processing | Python 3.11+, `numpy`, `h5py`, `xarray`, `rioxarray`, `rasterio`, `geopandas`, `shapely`, `scikit-image`, `scipy` |
| Geodata formats | GeoJSON, GeoPackage, PMTiles, Cloud-Optimized GeoTIFF (COG) |
| Frontend | HTML/CSS/JavaScript (or React + Vite), **MapLibre GL JS**, `maplibre-gl-compare` (swipe), **Chart.js** or Plotly, `pmtiles` |
| Hosting / CI | GitHub, GitHub Pages or Netlify, GitHub Actions |
| Validation | `pandas`, `scikit-learn` (metrics), Jupyter notebooks |

---

## 📁 Repository structure

```
aquapulse/
├── README.md
├── LICENSE
├── environment.yml              # Conda environment
├── requirements.txt
├── .env.example                 # EARTHDATA_USER, EARTHDATA_PASS, GEE_PROJECT
├── contracts/                   # Shared file schemas + examples (agreed at kickoff)
├── config/
│   └── settings.yaml            # AOI, dates, thresholds, paths
├── data/
│   ├── raw/                     # Downloaded scenes (git-ignored)
│   ├── interim/                 # Clipped / preprocessed rasters (git-ignored)
│   ├── reference/               # Polygons, JRC, HAND, basins, official fill rates
│   └── processed/               # Monthly masks, areas, status tables
├── pipeline/
│   ├── 01_build_catalog.py      # Polygons → reservoir catalog
│   ├── 02_search_download.py    # NISAR search & download
│   ├── 03_preprocess.py         # dB, speckle filter, masks, clip
│   ├── 04_detect_water.py       # Otsu + filters + cleanup
│   ├── 05_monthly_composite.py  # Majority vote per month
│   ├── 06_baseline_s1_gee.py    # Sentinel-1 baseline in Earth Engine
│   ├── 07_status_anomaly.py     # % of normal, z-score, classes, trends
│   ├── 08_export_web.py         # GeoJSON/PMTiles, COG/PNG, JSON time series
│   └── utils/
│       ├── io.py
│       ├── sar.py
│       └── geo.py
├── notebooks/
│   ├── 00_explore_gcov.ipynb
│   ├── 01_water_detection_tests.ipynb
│   └── 02_validation.ipynb
├── web/
│   ├── index.html
│   ├── src/
│   │   ├── main.js
│   │   ├── map.js
│   │   ├── panel.js
│   │   ├── charts.js
│   │   └── timeslider.js
│   ├── styles/
│   ├── public/data/             # Exported outputs from pipeline/08
│   └── content/                 # Explainer text & images (Track E)
├── docs/
│   ├── methodology.md
│   ├── validation_report.md
│   └── images/
└── .github/workflows/
    └── monthly_update.yml
```

---

## 🚀 Getting started

```bash
# 1. Clone
git clone https://github.com/<your-org>/aquapulse.git
cd aquapulse

# 2. Environment
conda env create -f environment.yml
conda activate aquapulse

# 3. Credentials
cp .env.example .env          # add your Earthdata login + GEE project
earthengine authenticate

# 4. Run the pipeline (example: one reservoir, test mode)
python pipeline/01_build_catalog.py --country MAR
python pipeline/02_search_download.py --reservoir al_massira --start 2026-06-01 --end 2026-11-01
python pipeline/03_preprocess.py --reservoir al_massira
python pipeline/04_detect_water.py --reservoir al_massira
python pipeline/05_monthly_composite.py --reservoir al_massira
python pipeline/07_status_anomaly.py
python pipeline/08_export_web.py

# 5. Run the web app locally
cd web && npx serve .          # or: python -m http.server 8000
```

---

## 👥 Team workstreams

We work as **5 parallel tracks**, all starting at hour 0. Nobody waits for another track, for three reasons:

1. **Contract-first:** in the kickoff we agree on the exact files each track produces and consumes ([Interface contracts](#-interface-contracts)).
2. **Mock-first:** every track publishes a *fake but correctly formatted* version of its output within the first hours, so downstream tracks can build against it right away.
3. **Independent data paths:** the NISAR track (B) and the Sentinel-1 track (C) each detect water on their own from the same written algorithm spec, with no code handoff between them.

| Track | Name | Owner | Produces | Consumes (mock until real) |
|---|---|---|---|---|
| **A** | Reservoir catalog & data plumbing | Data engineer | `reservoirs.geojson`, scene inventory, web exports | `monthly_area.csv`, `status.csv` |
| **B** | NISAR water detection | SAR analyst | NISAR rows of `monthly_area.csv`, water-extent PNGs | analysis zones (or a hand-drawn bbox) |
| **C** | Sentinel-1 baseline, analytics & validation | Baseline analyst | Sentinel-1 rows of `monthly_area.csv`, `status.csv`, validation report | `reservoirs.geojson` (or a hand-drawn list) |
| **D** | Web GIS | Frontend dev | Live web app | `reservoirs.geojson`, `timeseries/*.json`, PNG overlays |
| **E** | Story, design & submission | Storyteller (or shared) | Explainer content, slides, video, project page | Screenshots and figures from all tracks |

> **4-person team?** Split Track E: D does the in-app explainer, everyone records their own part of the video, and A writes the project page.

```
Hour:   0   2        8              20             32          42    48
        │Kick│                                                  │Freeze│
A  Data ├────┤mock geojson──►real catalog──►exports & automation──┤      │
B  NISAR├────┤1 scene by hand──►detection──►all priority dams──────┤      │
C  S-1  ├────┤GEE detection──►baseline──►status──►validation───────┤      │
D  Web  ├────┤map on mocks──►panel+charts──►slider+swipe──►polish──┤      │
E  Story├────┤storyline──►explainer──►slides──►video───────────────┤      │
        │ ◆ │         ◆ CP1          ◆ CP2          ◆ CP3      ◆ CP4│
```

### Folder ownership (avoids merge conflicts)

| Track | Owns these paths | Git branch |
|---|---|---|
| A | `pipeline/01_*`, `02_*`, `08_*`, `pipeline/utils/io.py`, `pipeline/utils/geo.py`, `data/reference/` | `track-a-data` |
| B | `pipeline/03_*`, `04_*`, `05_*`, `pipeline/utils/sar.py`, `notebooks/00_*`, `01_*` | `track-b-nisar` |
| C | `pipeline/06_*`, `07_*`, `notebooks/02_validation.ipynb`, `docs/validation_report.md` | `track-c-baseline` |
| D | `web/` (except `web/public/data/`) | `track-d-web` |
| E | `docs/` (except validation report), `web/content/`, `slides/`, `video/` | `track-e-story` |
| Shared | `config/settings.yaml`, `contracts/`, `README.md` | small PRs, announce in chat |

- Merge to `main` **at every checkpoint** (and whenever something works).
- Only Track A writes into `web/public/data/` (through `08_export_web.py`), so data drops never collide with frontend code.

---

## 🔗 Interface contracts

Agreed in the kickoff and saved in `contracts/` with one example file each. **A contract changes only if all affected track owners agree.**

### Contract 1: `reservoirs.geojson` (A → B, C, D)
```json
{
  "type": "Feature",
  "properties": {
    "reservoir_id": "MAR_0001",
    "name": "Al Massira",
    "basin": "Oum Er-Rbia",
    "capacity_mcm": 2657,
    "dam_year": 1979,
    "polygon_area_km2": 100.5,
    "priority": true,
    "confidence": "high"
  },
  "geometry": { "type": "Polygon", "coordinates": [[[-7.6, 32.4], "..."]] }
}
```
- `reservoir_id`: format `MAR_####`, **never changes** once assigned. It is the join key everywhere.
- `confidence`: `high` | `low` (low = area < 0.5 km²).
- A separate file, `analysis_zones.geojson`, has the same IDs with buffered geometries.
- *(Example values are illustrative only; real values come from GDW.)*

### Contract 2: `monthly_area.csv` (B, C → C, A)
```csv
reservoir_id,month,sensor,area_km2,n_obs,quality
MAR_0001,2026-07,NISAR,48.2,3,good
MAR_0001,2026-07,S1,46.9,5,good
```
- `month`: `YYYY-MM`. `sensor`: `NISAR` | `S1`. `quality`: `good` | `partial` | `bad`.
- B writes `data/processed/monthly_area_nisar.csv`, C writes `monthly_area_s1.csv`. C merges them.

### Contract 3: `status.csv` (C → A)
```csv
reservoir_id,month,area_km2,normal_km2,pct_of_normal,z_score,status,mom_change_pct,yoy_change_pct,official_fill_pct
MAR_0001,2026-07,48.2,52.0,92.7,-0.4,normal,-3.1,+210.5,41.6
```
- `status`: `above_normal` | `normal` | `watch` | `drought` | `severe` | `no_data`.

### Contract 4: web data (A → D)
```
web/public/data/
├── reservoirs.geojson              # Contract 1 + latest status fields merged in
├── basins.geojson
├── months.json                     # ["2025-01", ..., "2026-10"]
├── timeseries/MAR_0001.json        # see below
└── extents/MAR_0001_2026-07.png    # + extents/index.json with bounds per image
```
`timeseries/MAR_0001.json`:
```json
{
  "reservoir_id": "MAR_0001",
  "series": [
    { "month": "2026-07", "area_km2": 48.2, "normal_km2": 52.0, "p10_km2": 30.1,
      "p90_km2": 70.3, "status": "normal", "sensor": "NISAR", "official_fill_pct": 41.6 }
  ]
}
```
`extents/index.json`: `{ "MAR_0001_2026-07": { "bounds": [[minLon, minLat], [maxLon, maxLat]] } }`

### Contract 5: water-detection algorithm spec (B ↔ C)
A single written spec in `contracts/water_detection_spec.md`, which B implements in Python (NISAR) and C in Earth Engine (Sentinel-1):
1. Clip to analysis zone + 1 km land buffer.
2. Convert to dB, then 5×5 median filter.
3. Mask layover/shadow (NISAR) / border noise (S1).
4. Otsu threshold on the co-pol band (HH for NISAR, VV for S1). If the histogram isn't bimodal, use a fixed fallback (agreed value per sensor).
5. Keep pixels below the threshold that are inside the JRC max extent **and** have HAND < 15 m.
6. Morphological opening (3×3), drop blobs < 10 pixels.
7. Monthly composite: water if detected in ≥ 50% of the month's scenes.

---

## ✅ Task list

> **Priorities:** P0 = must have for the demo · P1 = should have · P2 = stretch
> **Tags:** 🧪 = works on mock data · 🔁 = swap mock → real when the upstream drop lands
> **Time blocks** assume a 48-hour hackathon. Adjust to your actual schedule.

### 🟣 Kickoff, all together (H0–H2)
- [ ] **P0** Create repo, branches per track, project board with one column per track.
- [ ] **P0** Everyone creates NASA Earthdata + Google Earth Engine accounts; install environment.
- [ ] **P0** Agree on and commit **Contracts 1–5** to `contracts/`, each with an example file.
- [ ] **P0** Agree on the **5 demo reservoirs** now so nobody waits for the catalog. Suggested: Al Wahda, Al Massira, Bin El Ouidane, Idriss I, Mansour Eddahbi (north, centre, mountain, arid south).
- [ ] **P0** Hand-draw rough bounding boxes for those 5 (geojson.io) → `contracts/demo_bboxes.geojson`. Tracks B and C start from this immediately.
- [ ] **P0** Agree on checkpoint times and a chat channel for "contract change" announcements.

---

### 🅰️ Track A: Reservoir catalog & data plumbing

**Block 1 (H2–H8): mocks out fast**
- [ ] **P0 🧪** Publish `web/public/data/reservoirs.geojson` mock (5 demo polygons from bboxes, fake attributes) **by H3**. This unblocks Track D.
- [ ] **P0 🧪** Generate mock `timeseries/*.json`, `months.json`, and 2 mock extent PNGs + `index.json` **by H4**.
- [ ] **P0** Download GDW v1.0 reservoirs + HydroLAKES; filter to Morocco.
- [ ] **P0** Download reference rasters for Morocco: JRC max water extent, MERIT Hydro HAND. **Share them with B and C.**

**Block 2 (H8–H20): real catalog**
- [ ] **P0** Merge + deduplicate GDW/HydroLAKES; assign stable `reservoir_id`s.
- [ ] **P1** Add recent dams from OpenStreetMap.
- [ ] **P0** Attach basin names (HydroBASINS / national basins) and attributes.
- [ ] **P0** Build `analysis_zones.geojson` (polygon ∪ JRC max extent + 500 m).
- [ ] **P0** Rank by capacity; mark the top 15–25 as `priority: true`.
- [ ] **P0 🔁** Replace the mock `reservoirs.geojson` with the real catalog (same schema). Notify D.
- [ ] **P0** Build the NISAR scene inventory for priority reservoirs (`asf_search`) → share with B.

**Block 3 (H20–H32): export pipeline**
- [ ] **P0** Write `08_export_web.py`: reads `status.csv` + `monthly_area.csv` + extent PNGs and writes Contract 4 files.
- [ ] **P0 🔁** First real export at **CP2** using whatever B and C have finished.
- [ ] **P1** Build `basins.geojson` with aggregated status.
- [ ] **P1** Convert polygons to PMTiles if the GeoJSON is too heavy.

**Block 4 (H32–H42): automation & support**
- [ ] **P1** One command `make all` (or `run_pipeline.py`) that chains every step.
- [ ] **P2** GitHub Actions monthly workflow (demo of automation).
- [ ] **P0** Re-export at every new data drop from B and C; final export at **CP4**.
- [ ] **P1** Help E: data-source table and architecture diagram.

---

### 🅱️ Track B: NISAR water detection

**Block 1 (H2–H8): one scene, by hand**
- [ ] **P0** Manually download **one** NISAR GCOV scene over Al Massira from Vertex (don't wait for the inventory).
- [ ] **P0** Inspect it (`h5ls -r`); document dataset paths, pixel size, CRS, mask layer in `contracts/gcov_notes.md`.
- [ ] **P0** Read HH/HV into `xarray`, clip to the demo bbox, convert to dB, filter.
- [ ] **P0** Implement Otsu + masks (Contract 5) on this one scene; save a quick-look PNG.
- [ ] **P0 🧪** Send Track D one real water-extent PNG + bounds **by H8** (proves the overlay works end to end).

**Block 2 (H8–H20): robust detection**
- [ ] **P0** Package as functions in `pipeline/utils/sar.py`: `load_gcov()`, `preprocess()`, `detect_water()`.
- [ ] **P0** Test on the hard cases: Mansour Eddahbi (arid, dry-sand false positives) and Bin El Ouidane (mountain, layover).
- [ ] **P1** Add HV filter for dry sand / smooth soil.
- [ ] **P0** Implement the monthly majority-vote composite (`05_monthly_composite.py`).
- [ ] **P0** Output NISAR rows of `monthly_area.csv` for the 5 demo reservoirs **by CP2**.

**Block 3 (H20–H32): scale up**
- [ ] **P0 🔁** Switch from demo bboxes to `analysis_zones.geojson` + scene inventory from A.
- [ ] **P0** Batch-process all priority reservoirs (subset downloads / S3 streaming to save time).
- [ ] **P0** Export monthly extent PNGs (transparent, blue water) for every reservoir-month.
- [ ] **P1** Record `quality` per month (few scenes, high masked fraction → `partial` / `bad`).

**Block 4 (H32–H42): QA & figures**
- [ ] **P0** Visual QA: flip through quick-looks and fix or flag bad months.
- [ ] **P1** Produce 2–3 "hero" figures for the story (e.g. Al Massira radar image + water mask, before/after).
- [ ] **P1** Write the method section of `docs/methodology.md`.

---

### 🅲 Track C: Sentinel-1 baseline, analytics & validation

**Block 1 (H2–H8): independent detection in GEE**
- [ ] **P0** Implement Contract 5 in Earth Engine for Sentinel-1 VV, using the demo bboxes.
- [ ] **P0** Monthly water area 2015 → present for Al Massira; plot it and sanity-check (2025 low → 2026 recovery).
- [ ] **P0** Start collecting **official fill rates** from *Al Maa Dialna* for the 5 demo dams (monthly values, 2025–2026) → `data/reference/official_fill.csv`.

**Block 2 (H8–H20): baseline + status**
- [ ] **P0** Run S1 monthly areas for all 5 demo reservoirs → `monthly_area_s1.csv`.
- [ ] **P0** Compute climatology per reservoir and calendar month (mean, std, p10, p90).
- [ ] **P0** Write `07_status_anomaly.py`: % of normal, z-score, status class, month-over-month and year-over-year change → `status.csv` (Contract 3).
- [ ] **P0 🧪** Deliver a first real `status.csv` (S1 only) to A **by CP2**.

**Block 3 (H20–H32): merge sensors + validate**
- [ ] **P0 🔁** Merge NISAR rows from B; harmonize NISAR vs S1 in overlapping months (bias correction).
- [ ] **P0 🔁** Extend to all priority reservoirs once A's real `analysis_zones.geojson` lands.
- [ ] **P0** Validation: SAR area vs official fill rate (scatter + R²) for the 5 demo dams.
- [ ] **P1** Sentinel-2 NDWI comparison on clear-sky dates (IoU).
- [ ] **P1** Basin-level aggregation; CHIRPS rainfall anomaly per basin.

**Block 4 (H32–H42): numbers for the pitch**
- [ ] **P0** Write `docs/validation_report.md`: key metrics + 2 charts.
- [ ] **P0** Give E the 3 headline numbers (e.g. R², national change in water area, number of reservoirs in drought).
- [ ] **P2** Fit area–storage curves; estimate % full for reservoirs without official data.

---

### 🅳 Track D: Web GIS

**Block 1 (H2–H8): map on mock data**
- [ ] **P0** Scaffold `web/` (plain JS or Vite), MapLibre map centred on Morocco, basemap switcher.
- [ ] **P0 🧪** Load mock `reservoirs.geojson`; style polygons by `status` with a legend.
- [ ] **P0 🧪** Click → side panel with name, basin, capacity, status.
- [ ] **P0** Deploy an early version to GitHub Pages / Netlify (catch deployment issues early).

**Block 2 (H8–H20): core interactions**
- [ ] **P0 🧪** Time-series chart in the panel (area line, normal band p10–p90, official fill rate on a second axis).
- [ ] **P0 🧪** Monthly time slider: changes status colors + swaps extent PNG overlays.
- [ ] **P0 🔁** Test with B's first real PNG (bounds and alignment check).
- [ ] **P1** Layer control (reservoirs, basins, water extents, basemaps).

**Block 3 (H20–H32): GIS features**
- [ ] **P0 🔁** Swap to the first real data export from A at **CP2**; fix any contract mismatches.
- [ ] **P1** Swipe comparison (two months side by side).
- [ ] **P1** Search & filter (name, basin, status, size).
- [ ] **P1** Basin summary view.
- [ ] **P1** Embed E's "How radar sees water" explainer panel.

**Block 4 (H32–H42): polish**
- [ ] **P1** Responsive layout; loading states; "no data" handling.
- [ ] **P1** Story mode: guided tour (national view → Al Massira recovery → southern drought).
- [ ] **P2** Language toggle (EN / FR / AR); CSV / GeoJSON download buttons.
- [ ] **P0** Final deploy with real data at **CP4**; test on phone and laptop.

---

### 🅴 Track E: Story, design & submission

**Block 1 (H2–H8)**
- [ ] **P0** Draft the storyline and demo script: *"From 4% to 42%: how radar watched Morocco's reservoirs come back, and where drought still holds."*
- [ ] **P0** Define the visual identity: name, logo text, status color palette (share with D).
- [ ] **P0** Research context: Morocco's water situation, basins, why reservoirs matter (with sources).

**Block 2 (H8–H20)**
- [ ] **P0** Write the "How radar sees water" explainer (short text + simple diagrams) → `web/content/`.
- [ ] **P0** Write the physical-drivers section: rainfall recovery, evaporation, irrigation demand, dam releases.
- [ ] **P1** Write future NISAR applications + global roadmap section.

**Block 3 (H20–H32)**
- [ ] **P0** Build the slide deck (≤ 10 slides) with placeholders for real figures.
- [ ] **P0** Draft the Space Apps project page text.
- [ ] **P1** Collect screenshots and figures from B, C and D as they land.

**Block 4 (H32–H42)**
- [ ] **P0** Record and edit the 2–3 min demo video using the live app.
- [ ] **P0** Insert final numbers from C; final pass on slides.
- [ ] **P0** Submit the project page (links: repo, live app, video, slides).

---

### 🔶 Sync checkpoints (all tracks)

Short meetings (15 min max). Each track answers: *what works, what's blocked, any contract change?*

| Checkpoint | When | Integration goal |
|---|---|---|
| **CP1** | ~H8 | All mocks published; web app deployed on mocks; one real NISAR water mask and one S1 time series exist |
| **CP2** | ~H20 | **First end-to-end run on real data** for the 5 demo reservoirs: B + C → `status.csv` → A export → D displays it |
| **CP3** | ~H32 | All priority reservoirs processed; validation numbers ready; feature freeze on new P1s |
| **CP4** | ~H42 | **Code freeze.** Final export + deploy; video recorded from the live app |
| **Submit** | H42–H48 | Buffer for fixes, submission, rest |

### Fallback rules (so one stuck track never blocks the demo)
- **NISAR detection not ready by CP2:** ship the app with Sentinel-1 results and show NISAR on 1–2 hero reservoirs.
- **Real catalog late:** keep the 5 demo reservoirs; it's still a complete story.
- **Official fill rates hard to get:** validate with Sentinel-2 NDWI only.
- **Swipe or story mode unfinished:** cut them; the map + slider + panel is the MVP.
- **Rule of thumb:** after **CP3**, only fix bugs and polish. No new features.

---

## 🧪 Validation plan

| Test | Reference | Metric | Target |
|---|---|---|---|
| SAR area vs official storage | *Al Maa Dialna* fill rates | R² / Pearson r | r ≥ 0.85 |
| Water mask accuracy | Sentinel-2 NDWI (clear days) | IoU, precision, recall | IoU ≥ 0.80 |
| Sensor consistency | NISAR vs Sentinel-1 same month | Mean area difference | ≤ 10% |
| Temporal sanity | Known events (2025 lows → 2026 recovery) | Visual + trend direction | Correct direction |

---

## ⚠️ Known limitations & risks

| Risk | Impact | Mitigation |
|---|---|---|
| Short NISAR record (archive still being backfilled) | Weak baseline | Use Sentinel-1 (2015 →) for climatology; NISAR for recent detail |
| Dry sand / smooth surfaces look like water (arid south) | Overestimated area | HAND mask, search zone, HV check, test early in the south |
| Wind-roughened water looks bright | Underestimated area | Monthly majority vote, HV, multiple dates |
| Layover/shadow in mountain valleys | Corrupted shorelines | GCOV mask, prefer best-viewing orbit direction |
| Flooded vegetation appears bright at L-band | Missed water at margins | Treat as separate class; document |
| Small reservoirs (< 0.5 km²) | Unreliable area | Flag as low confidence |
| Missing / outdated polygons | Reservoirs not monitored | Add OSM; use JRC max extent; manual check for new dams |
| Surface area ≠ volume | Misleading % full | Present area-based status; calibrate with official data; SWOT later |
| Large file sizes | Slow downloads | Spatial subsetting, S3 streaming, process only priority reservoirs |
| Over-scoping in 48 h | Unfinished demo | Strict P0/P1/P2 priorities; MVP first |

---

## 🌍 Roadmap: from Morocco to the world

| Stage | Scope | Key additions |
|---|---|---|
| **v0.1 – Hackathon** | Morocco, top 15–25 reservoirs | MVP web GIS, validation on 3–5 dams |
| **v0.2** | All Moroccan reservoirs & lakes | Basin dashboard, rainfall, area→storage curves |
| **v0.3** | North Africa / Mediterranean | Cloud processing, automated 12-day updates |
| **v1.0** | Global | All GDW + HydroLAKES, PostGIS + tiles, public API, SWOT volumes, alerts |

---

## 📄 License

Code: **MIT License**. Derived data products follow the licenses of their sources (e.g. GDW: CC BY 4.0; NISAR & Sentinel data: free and open). See `LICENSE`.

---

## 🙏 Acknowledgments & references

- **NASA-ISRO NISAR mission**, data from the [Alaska Satellite Facility DAAC](https://asf.alaska.edu/) and the [NISAR data user documentation](https://nisar-docs.asf.alaska.edu/).
- **NASA Space Apps Challenge 2026**: *Dancing with the SARs*.
- **Copernicus Sentinel-1 & Sentinel-2** (ESA / European Commission).
- Lehner, B. et al. (2024). *The Global Dam Watch database of river barrier and reservoir information for large-scale applications.* Scientific Data 11, 1069. https://doi.org/10.1038/s41597-024-03752-9
- Messager, M.L. et al. (2016). *Estimating the volume and age of water stored in global lakes using a geo-statistical approach.* Nature Communications (HydroLAKES).
- Pekel, J.-F. et al. (2016). *High-resolution mapping of global surface water and its long-term changes.* Nature (JRC Global Surface Water).
- Yamazaki, D. et al. (2019). *MERIT Hydro: a high-resolution global hydrography map.* Water Resources Research.
- Funk, C. et al. (2015). *The climate hazards infrared precipitation with stations (CHIRPS).* Scientific Data.
- Otsu, N. (1979). *A threshold selection method from gray-level histograms.* IEEE Trans. SMC.
- Moroccan Ministry of Equipment and Water, *Al Maa Dialna* platform (official dam fill rates).

---


