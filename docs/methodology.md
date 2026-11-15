# SaddSAR methodology

This document describes what the pipeline in `pipeline/` actually does. Parameters live in
`config/settings.yaml`; the shared algorithm is `pipeline/utils/sar.py`.

## 1. Reservoir catalog (step 01)

* **Input.** `geo_data/{dams,lakes,ponds}.geojson`: 316 Moroccan water bodies (232 reservoirs,
  28 natural lakes, 56 small ponds). These came from the polygon-extraction track: JRC maximum water
  extent merged with OpenStreetMap, plus dam attributes from Wikidata, GeoDAR and OSM. Their
  geometry is a **region of interest** (`roi_km2`), not the water outline.
* **Outline.** The maximum water outline is traced from the JRC Global Surface Water `extent`
  layer (water seen at least once between 1984 and 2021) inside each region, at 30 m. The area
  matches the source `area_max_km2` to within about 3 %. Ten dams that filled after 2021
  (e.g. M'Dez, 2025; Tiddas, 2022) are invisible to JRC; they keep the source region and area.
* **Deduplication.** A polygon covered more than 50 % by a higher-ranked one is dropped
  (rank: reservoir > lake > pond, then capacity).
* **IDs.** `MAR_####` is assigned once and stored in `data/reference/id_map.csv`. It is
  append-only, so IDs never change. Reservoirs are numbered first (MAR_0001 = Al Massira).
* **Attributes.** Name (French prefix such as "Barrage" removed), Arabic name, basin, river,
  capacity (Mm³), year, polygon area, `priority` (20 largest by capacity plus the 5 demo dams),
  `confidence` (`low` below 0.5 km² or when the source flags the body as too small for SAR).
* **Analysis zone.** Region of interest ∪ (outline + 500 m).
* **Basins.** HydroBASINS level-6 units whose `MAIN_BAS` hosts reservoirs of a national basin,
  dissolved per basin name. This gives the 10 national basins.

## 2. Radar inputs

| Sensor | Product | Access | Grid used |
|---|---|---|---|
| NISAR (L-band, HH + HV) | L2 GCOV (provisional), gamma0 power | `asf_search` + `earthaccess`; window read from the remote HDF5, no full download (step 02) | native 10 m, UTM |
| Sentinel-1 (C-band, VV) | RTC (terrain-corrected gamma0) | Microsoft Planetary Computer STAC, COG overviews (step 06) | 40 m, UTM |
| Sentinel-1 (alternative) | GRD | Google Earth Engine (`06_baseline_s1_gee.py`) | 40 m |

Verified GCOV paths, pixel spacing and mask semantics are recorded in `contracts/gcov_notes.md`.
The GCOV `mask` layer marks the valid subswath (0 = partially focused, 255 = fill). It does
**not** flag layover or shadow, so mountain reservoirs rely on the terrain filter below.

## 3. Water detection (Contract 5, both sensors)

For each scene:

1. **Clip** to the analysis zone + 1 km of land (step 02 window / step 06 grid).
2. **dB + speckle filter:** `10·log10(γ⁰)`, then a 5×5 median filter that ignores invalid pixels.
3. **Validity:** finite backscatter; NISAR mask ∉ {0, 255}; Sentinel-1 nodata removed.
4. **Threshold:** Otsu on the co-polarised band.
   * Sentinel-1 VV: Otsu over the clip (water + land). Plausible range [-24, -13] dB; outside it
     the fixed fallback of -18 dB is used.
   * NISAR HH: at L-band the exposed, dry lake bed and smooth soil are almost as dark as water.
     On Al Massira (Oct 2026) the water peak is about -19.5 dB HH and the bed spans -17 to -11 dB.
     Otsu is therefore computed **inside the search zone** and capped at -18 dB HH.
   * When Otsu lands on the bright side of the plausible range, the mean of the darker class
     decides. If it is water-like (≤ -15.5 dB VV, ≤ -18.5 dB NISAR HH, ≤ -23.5 dB HV), the
     threshold is **capped** at the limit. Otherwise the **fallback** is used.
     This handles two real cases. Wind-roughened Al Wahda (Oct 2026) has Otsu at -12.7 dB and a
     dark mean of -16.7 dB: capping gives 104 km² instead of 16 km². Nearly empty Al Massira
     (Aug 2024) has a dark mean of -11.7 dB: fallback, so no false water on the exposed bed.
   * **VH rescue (Sentinel-1).** When wind roughens the whole lake, VV has no water mode at all and
     falls back (Al Wahda, July–August 2026, evening passes: ~0 km²). Such scenes are re-detected on
     VH, which wind affects much less: Otsu inside the search zone, plausible [-30, -19] dB, kept
     only if the dark class mean is ≤ -22 dB. Windy full lakes measure -23.4 to -24.1 dB; an empty
     bed measures -19.3 dB and stays empty. Method recorded as `vh` in `scene_areas_s1.csv`.
5. **Masks:**
   * search zone = (JRC max extent ∪ outline) dilated by 500 m, inside the analysis zone;
   * terrain filter (HAND proxy) = pixel more than 15 m above the reservoir's maximum level
     (90th percentile of the Copernicus DEM inside the max extent) is never water;
   * HV check (NISAR): HV must also be below its own Otsu threshold, capped at -23 dB (water HV
     sits on the ~-24 dB noise floor). This removes dry sand and smooth soil.
6. **Cleanup:** 3×3 opening; blobs under 10 pixels removed; only blobs touching the reservoir kept.
7. **Monthly composite:** a pixel is water if it is detected in ≥ 50 % of the month's scenes in
   which it is valid. Sentinel-1 uses up to 3 evenly spaced scenes per month (2 before 2023) from a
   single relative orbit chosen for full coverage and the most dates. Windy scenes, where calm water
   turns bright, are outvoted.

**Quality** per month: `bad` if under 70 % of the search zone is valid; `partial` if there is
1 scene, under 90 % valid, or a fallback threshold was used (typical when a reservoir is almost
empty, so the histogram has no water mode); otherwise `good`.

## 4. Baseline, anomaly, status (step 07)

* **Harmonization:** NISAR areas are scaled onto Sentinel-1 by k = median(S1 / NISAR) over
  months where both exist (per reservoir; pooled if there are fewer than 2 overlapping months).
* **Normal:** per reservoir and calendar month, from Sentinel-1 over 2015–2024: mean, standard
  deviation, p10, p90, number of years (at least 3 required).
* **Monthly value:** NISAR (harmonized) when usable, else Sentinel-1.
* **Anomaly:** `pct_of_normal = area / normal × 100`, `z = (area − normal) / std`.
* **Status:** above normal > 110 % ≥ normal ≥ 90 % > watch ≥ 75 % > drought ≥ 50 % > severe.
  `no_data` for bad months, low-confidence reservoirs, or too few baseline years.
* **Trends:** change against the previous month and against the same month one year earlier.
* **Area → storage (stretch):** where at least 6 official fill values exist
  (`data/reference/official_fill.csv`), `V = a·Aᵇ` is fitted in log space and gives `est_fill_pct`.

## 5. Rainfall context (step 10, stretch)

CHIRPS v2.0 monthly rainfall (0.05°) comes from the IRI Data Library and is averaged per basin
(cos-latitude weights). Each month and each 12-month total is compared with the 2015–2024
mean for that calendar month. This separates a rain deficit (climate) from releases and
irrigation (human).

## 6. Export (step 08)

The web dataset follows Contract 4 (see `contracts/`). Overlays use NISAR when that month is
usable, otherwise Sentinel-1. Geometry is simplified to about 20 m with 5-decimal coordinates.
The export also writes `national.json`, `alerts.json` (status changes), `rainfall.json`,
`downloads/*.csv` and `api/latest.json`.

## 7. Known limitations

* NISAR GCOV is a provisional product (since Oct 2025), so the record is short. The long-term
  normal therefore comes from Sentinel-1.
* NISAR thresholds were tuned on one reservoir. Arid southern reservoirs need more checks.
* A normal computed over 2015–2024 includes the 2022–2024 drought, so a "normal" 2026 is wetter
  than a pre-2018 normal would be.
* Surface area is not volume. `est_fill_pct` exists only where official data calibrate it.
* 40 m Sentinel-1 pixels (0.0016 km²) are coarse for reservoirs under about 2 km². These are
  flagged as low confidence.
