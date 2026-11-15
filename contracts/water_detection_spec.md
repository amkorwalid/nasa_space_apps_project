# Contract 5: water-detection algorithm spec (Tracks B and C)

One written algorithm, implemented once in `pipeline/utils/sar.py` and called by both the NISAR
steps (03–05) and the Sentinel-1 step (06). `pipeline/06_baseline_s1_gee.py` implements the same
steps in Earth Engine. Parameters live in `config/settings.yaml` under `detection:`.

| # | Step | NISAR (L-band) | Sentinel-1 (C-band) |
|---|---|---|---|
| 1 | Clip | analysis zone + 1 km land | same |
| 2 | dB + speckle | 10·log10, 5×5 median | same |
| 3 | Invalid pixels | GCOV `mask` ∈ {0, 255} | RTC nodata / ≤ 0 |
| 4 | Threshold | Otsu on HH **inside the search zone**, plausible [-30, -18] dB | Otsu on VV over the clip, plausible [-24, -13] dB |
|   | Outside the range | darker → fallback -18 dB; brighter and dark-class mean ≤ -18.5 dB (HV ≤ -23.5) → capped at the limit; else fallback | brighter and dark-class mean ≤ -15.5 dB → capped at -13 dB; else fallback -18 dB |
|   | VV found no water mode | — | re-detect on VH (search-zone Otsu, [-30, -19] dB, dark mean ≤ -22 dB); keep if water-like |
| 5 | Keep | below threshold ∩ search zone ((JRC max ∪ outline) + 500 m) ∩ height above max level < 15 m; HV also below its threshold (≤ -23 dB) | same, without the cross-pol check (`use_vh: false`) |
| 6 | Cleanup | 3×3 opening, blobs < 10 px dropped, only blobs touching the reservoir | same |
| 7 | Monthly composite | water if detected in ≥ 50 % of valid scenes | same (≤ 3 scenes; ≤ 2 before 2023) |

Outputs follow Contract 2 (`monthly_area_nisar.csv`, `monthly_area_s1.csv`):
`reservoir_id,month,sensor,area_km2,n_obs,quality` with quality `good | partial | bad`
(see `pipeline/utils/sar.py: month_quality`).

## Change log

* 2026-11-14: NISAR thresholds tuned on real GCOV data. At L-band the dry lake bed is almost as
  dark as water, so Otsu runs on the search zone only and is capped at -18 dB HH / -23 dB HV. The
  "capped" rule requires a water-like dark class (mean below a per-sensor limit).
* 2026-11-14: the same capped rule applied to Sentinel-1 after Al Wahda (wind-roughened) was found
  at 16 km² instead of ~104 km² with the plain fallback. Baseline re-run with `--force`.
* 2026-11-14: Sentinel-1 VH rescue for wind-roughened scenes (Al Wahda / Idriss I, Jul–Aug 2026).
