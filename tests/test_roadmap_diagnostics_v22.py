"""Offline, deterministic checks for the v22 live Texas demonstrations."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from streamflow_getter import roadmap_diagnostics as diag


@pytest.fixture
def fake_operational(monkeypatch):
    api = ModuleType("streamflow_getter.operational_nwm")

    class ForecastConfig:
        def __init__(self, *, date, cycle, product, domain):
            self.date, self.cycle = date, cycle
            self.product, self.domain = product, domain

        def forecast_hours(self, first, last):
            if first < 1 or last < first:
                raise ValueError("Bad forecast lead")
            return list(range(first, last + 1))

    def kerchunk(_config, _hour, ids, **_kwargs):
        return {"method": "kerchunk", "streamflow_m3s": {ids[0]: 1.25}}

    def native(_config, _hour, ids):
        return {"method": "native_remote", "streamflow_m3s": {ids[0]: 1.25}}

    api.ForecastConfig = ForecastConfig
    api.read_kerchunk_forecast = kerchunk
    api.read_native_forecast = native
    api.fetch_operational_forecast = kerchunk
    monkeypatch.setitem(sys.modules, api.__name__, api)
    return api


def test_live_access_compares_same_hour_without_fabricating_values(fake_operational):
    outcome = diag.benchmark_access(
        "2025-07-04T06:00:00Z", 3586192, cache_dir="/tmp/reference-cache"
    )
    assert outcome["comparable"]
    assert outcome["equal_within_tolerance"] is True
    assert outcome["absolute_difference_m3s"] == 0
    assert outcome["kerchunk"]["streamflow_m3s"] == 1.25
    assert outcome["native"]["streamflow_m3s"] == 1.25
    assert outcome["kerchunk"]["seconds"] >= 0
    assert outcome["kerchunk"]["rss_increment_mb"] >= 0


def test_remote_reference_missing_is_reported_not_faked(fake_operational):
    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("reference missing")

    fake_operational.read_kerchunk_forecast = unavailable
    outcome = diag.benchmark_access("2025-07-04T06:00:00Z", 3586192)
    assert not outcome["comparable"]
    assert outcome["equal_within_tolerance"] is None
    assert "reference missing" in outcome["kerchunk"]["error"]
    assert outcome["native"]["ok"]


def test_conflicting_real_readers_are_detected(fake_operational):
    def native(_config, _hour, ids):
        return {"method": "native_remote", "streamflow_m3s": {ids[0]: 5.0}}

    fake_operational.read_native_forecast = native
    outcome = diag.benchmark_access("2025-07-04T06:00:00Z", 3586192)
    assert outcome["comparable"]
    assert outcome["equal_within_tolerance"] is False
    assert outcome["absolute_difference_m3s"] == pytest.approx(3.75)


def test_live_cache_same_data_two_calls(fake_operational):
    outcome = diag.benchmark_cache(
        "2025-07-04T06:00:00Z", 3586192, cache_dir="/tmp/reference-cache"
    )
    assert len(outcome["requests"]) == 2
    assert outcome["equal_within_tolerance"] is True
    assert all(item["method"] == "kerchunk" for item in outcome["requests"])


def test_naive_utc_is_rejected(fake_operational):
    with pytest.raises(ValueError, match="UTC offset"):
        diag.benchmark_access("2025-07-04T06:00:00", 3586192)


def test_reach_distances_use_consistent_projected_crs(monkeypatch):
    spatial = ModuleType("streamflow_getter.spatial_resolution")
    spatial.validate_hydrofabric_crs = lambda *_a: None
    spatial.load_nearby_reaches = lambda *_a, **_k: object()
    spatial.nearest_reaches = lambda *_a, **_k: [
        {"feature_id": 3586192, "distance_m": 91.0}
    ]
    monkeypatch.setitem(sys.modules, spatial.__name__, spatial)
    import pyogrio

    def fake_read_dataframe(*_args, **_kwargs):
        return gpd.GeoDataFrame(
            {"ID": [3586192]},
            geometry=[LineString([(-99.3219, 30.069), (-99.3217, 30.071)])],
            crs="EPSG:4269",
        )

    monkeypatch.setattr(pyogrio, "read_dataframe", fake_read_dataframe)
    study = SimpleNamespace(
        hydrofabric="fake.gdb",
        gages={"08165500": 3586192},
        provenance={"network_version": "3.1"},
        version="3.0",
        crosswalk_compatible=False,
    )
    record = {
        "metadata": {
            "point_epsg4326": {"longitude": -99.3217, "latitude": 30.0699},
            "geoglows": {"distance_m": 106.79},
            "drainage_area_comparison": {"message": "+5.7%"},
        },
        "geoglows_geometry": {
            "type": "LineString",
            "coordinates": [[-99.322, 30.069], [-99.322, 30.071]],
        },
    }
    report = diag.diagnose_reaches(study, record, "08165500", 3000)
    assert report["feature_id"] == 3586192
    assert report["crosswalk_compatible"] is False
    assert report["nwm_reach_count"] == 1
    assert report["usgs_to_nwm_m"] >= 0
    assert report["usgs_to_geoglows_m"] >= 0
    assert report["nwm_to_geoglows_m"] >= 0
    assert report["geoglows_service_distance_m"] == 106.79
    assert report["nearby"][0]["feature_id"] == 3586192


def test_map_has_v22_explorer_date_interface():
    import ast
    from pathlib import Path

    source = Path(diag.__file__).with_name("interactive_map.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    view = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StreamflowMap"
    )
    assert any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "INTERFACE_VERSION"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value >= 22
        for node in view.body
    )
