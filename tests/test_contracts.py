"""Interface contracts (README section 'Interface contracts'): the example files in contracts/
and the real outputs (when present) must match the JSON schemas / CSV headers in contracts/."""
import csv
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "contracts"
WEB = ROOT / "web" / "public" / "data"
PROC = ROOT / "data" / "processed"


def schema(name):
    return json.loads((C / name).read_text(encoding="utf-8"))


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def csv_header(p):
    with open(p, newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def test_example_files_match_schemas():
    jsonschema.validate(load(C / "examples" / "reservoirs.example.geojson"), schema("reservoirs.schema.json"))
    jsonschema.validate(load(C / "examples" / "timeseries.example.json"), schema("timeseries.schema.json"))
    jsonschema.validate(load(C / "examples" / "extents_index.example.json"), schema("extents_index.schema.json"))


def test_example_csv_headers():
    assert csv_header(C / "examples" / "monthly_area.example.csv") == \
        ["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"]
    assert csv_header(C / "examples" / "status.example.csv")[:10] == \
        ["reservoir_id", "month", "area_km2", "normal_km2", "pct_of_normal", "z_score", "status",
         "mom_change_pct", "yoy_change_pct", "official_fill_pct"]


@pytest.mark.skipif(not (PROC / "reservoirs.geojson").is_file(), reason="catalog not built")
def test_catalog_matches_contract_1():
    data = load(PROC / "reservoirs.geojson")
    jsonschema.validate(data, schema("reservoirs.schema.json"))
    ids = [f["properties"]["reservoir_id"] for f in data["features"]]
    assert len(ids) == len(set(ids))


@pytest.mark.skipif(not (WEB / "reservoirs.geojson").is_file(), reason="web data not exported")
def test_web_export_matches_contract_4():
    res = load(WEB / "reservoirs.geojson")
    jsonschema.validate(res, schema("reservoirs.schema.json"))
    months = load(WEB / "months.json")
    assert months == sorted(months) and all(len(m) == 7 for m in months)
    idx = load(WEB / "extents" / "index.json")
    jsonschema.validate(idx, schema("extents_index.schema.json"))
    for key in list(idx)[:50]:
        assert (WEB / "extents" / f"{key}.png").is_file()
    ts_schema = schema("timeseries.schema.json")
    files = sorted((WEB / "timeseries").glob("*.json"))
    for p in files:
        jsonschema.validate(load(p), ts_schema)


@pytest.mark.skipif(not (PROC / "status.csv").is_file(), reason="status not computed")
def test_status_csv_matches_contract_3():
    assert csv_header(PROC / "status.csv")[:10] == \
        ["reservoir_id", "month", "area_km2", "normal_km2", "pct_of_normal", "z_score", "status",
         "mom_change_pct", "yoy_change_pct", "official_fill_pct"]
    with open(PROC / "status.csv", newline="", encoding="utf-8") as f:
        statuses = {r["status"] for r in csv.DictReader(f)}
    assert statuses <= {"above_normal", "normal", "watch", "drought", "severe", "no_data"}
