# SaddSAR shortcuts. On Windows without make, use: python run_pipeline.py [...]
PY ?= python
R ?= priority

.PHONY: all catalog nisar s1 status export validate rainfall web test lint

all:
	$(PY) run_pipeline.py --reservoir $(R)

catalog:
	$(PY) pipeline/01_build_catalog.py --country MAR

nisar:
	$(PY) pipeline/02_search_download.py --reservoir $(R)
	$(PY) pipeline/03_preprocess.py --reservoir $(R)
	$(PY) pipeline/04_detect_water.py --reservoir $(R)
	$(PY) pipeline/05_monthly_composite.py --reservoir $(R)

s1:
	$(PY) pipeline/06_baseline_s1_pc.py --reservoir $(R)

rainfall:
	$(PY) pipeline/10_rainfall.py

status:
	$(PY) pipeline/07_status_anomaly.py

export:
	$(PY) pipeline/08_export_web.py

validate:
	$(PY) pipeline/09_validate.py

web:
	cd web && npm install && npm run build

test:
	$(PY) -m pytest -q
