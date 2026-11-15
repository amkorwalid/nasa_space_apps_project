"""Run the whole SaddSAR pipeline with one command (README task A, block 4).

    python run_pipeline.py                         # catalog -> NISAR -> S1 -> status -> web -> validation
    python run_pipeline.py --reservoir demo --skip-nisar
    python run_pipeline.py --from 07               # re-run analytics + export only
    python run_pipeline.py --backend gee           # Sentinel-1 on Google Earth Engine instead of Planetary Computer

Each step is also a standalone script in pipeline/ (see --help on each).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="priority", help="ID, name slug, comma list, demo, priority or all")
    ap.add_argument("--country", default="MAR")
    ap.add_argument("--backend", choices=["pc", "gee"], default="pc", help="Sentinel-1 baseline backend")
    ap.add_argument("--start", default=None, help="first Sentinel-1 month (YYYY-MM)")
    ap.add_argument("--from", dest="from_step", default="01", help="first step number to run")
    ap.add_argument("--to", dest="to_step", default="10", help="last step number to run")
    ap.add_argument("--skip-nisar", action="store_true", help="skip steps 02-05 (no Earthdata login)")
    ap.add_argument("--skip-s1", action="store_true", help="skip step 06")
    ap.add_argument("--skip-validation", action="store_true")
    ap.add_argument("--skip-rainfall", action="store_true")
    a = ap.parse_args()

    r = ["--reservoir", a.reservoir]
    s1_start = ["--start", a.start] if a.start else []
    steps = [
        ("01", ["pipeline/01_build_catalog.py", "--country", a.country]),
        ("02", ["pipeline/02_search_download.py", *r]),
        ("03", ["pipeline/03_preprocess.py", *r]),
        ("04", ["pipeline/04_detect_water.py", *r]),
        ("05", ["pipeline/05_monthly_composite.py", *r]),
        ("06", [f"pipeline/06_baseline_s1_{a.backend}.py", *r, *s1_start]),
        ("10", ["pipeline/10_rainfall.py"]),
        ("07", ["pipeline/07_status_anomaly.py"]),
        ("08", ["pipeline/08_export_web.py"]),
        ("09", ["pipeline/09_validate.py"]),
    ]
    skip = set()
    if a.skip_nisar:
        skip |= {"02", "03", "04", "05"}
    if a.skip_s1:
        skip.add("06")
    if a.skip_validation:
        skip.add("09")
    if a.skip_rainfall:
        skip.add("10")
    t0 = time.time()
    for num, cmd in steps:
        if num in skip or not (a.from_step <= num <= a.to_step):
            continue
        print(f"\n=== step {num}: {' '.join(cmd)}", flush=True)
        rc = subprocess.call([PY, "-u", *cmd], cwd=ROOT)
        if rc != 0:
            if num in {"02", "03", "04", "05", "09", "10"}:
                print(f"!!! step {num} failed (exit {rc}); continuing (optional for the demo)")
                continue
            sys.exit(f"step {num} failed (exit {rc})")
    print(f"\nPipeline finished in {(time.time() - t0) / 60:.1f} min. Web data in web/public/data/.")


if __name__ == "__main__":
    main()
