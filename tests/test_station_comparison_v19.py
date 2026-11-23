"""Offline v19 regressions: optional exports, timed retrieval, isolated maps."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from streamflow_getter import station_comparison as sc
from _widget_test_support import install_fake_widgets, map_result


@pytest.fixture
def study_settings(tmp_path, monkeypatch):
    route = tmp_path / "RouteLink_CONUS.nc"
    route.touch()
    hydro = tmp_path / "NWM_v3_hydrofabric.gdb"
    hydro.mkdir()
    monkeypatch.setattr(sc, "validate_hydrofabric_crs", lambda *_a: None)
    monkeypatch.setattr(sc, "resolve_operational_nwm_version", lambda *_a: "3.0")
    monkeypatch.setattr(
        sc,
        "load_gage_index_with_provenance",
        lambda *_a, **_k: (
            {"08165500": 3586192},
            {"network_version": "3.1", "crosswalk_sha256": "test-only"},
        ),
    )
    monkeypatch.setattr(
        sc, "build_nwm_to_usgs_index", lambda index: {v: k for k, v in index.items()}
    )

    def guard(requested, actual):
        if requested != (actual,):
            raise ValueError("Incompatible RouteLink network")

    monkeypatch.setattr(sc, "validate_routelink_compatibility", guard)
    return {
        "routelink": str(route),
        "hydrofabric": str(hydro),
        "workspace": str(tmp_path / "workspace"),
    }


@pytest.fixture
def mock_retrieval(monkeypatch):
    times = pd.to_datetime(["2025-07-04T06:00:00Z", "2025-07-04T07:00:00Z"])
    names = {
        "USGS": [5.0, 6.0],
        "GEOGLOWS retrospective": [1.0, 2.0],
        "NWM analysis_assim_no_da": [2.0, 3.0],
        "NWM analysis_assim": [3.0, 4.0],
        "NWM short_range": [4.0, 5.0],
    }
    response = SimpleNamespace(
        series={
            name: pd.DataFrame({"valid_time": times, "streamflow_m3s": values})
            for name, values in names.items()
        },
        source_timings_seconds={"USGS": 0.05, "NWM short_range": 0.11},
        total_elapsed_seconds=0.13,
    )
    monkeypatch.setattr(sc, "fetch_multi_source_streamflow", lambda *_a, **_k: response)
    monkeypatch.setattr(
        sc,
        "nearest_geoglows_reach",
        lambda *_a, **_k: {
            "river_id": 2025,
            "distance_m": 91.0,
            "upstream_area_km2": 788.3,
            "geometry": {
                "type": "LineString",
                "coordinates": [[-99.34, 30.06], [-99.31, 30.08]],
            },
        },
    )
    monkeypatch.setattr(
        sc,
        "fetch_usgs_monitoring_location",
        lambda *_a, **_k: {
            "longitude": -99.32,
            "latitude": 30.07,
            "drainage_area_km2": 745.9,
        },
    )
    monkeypatch.setattr(sc, "_read_geojson", lambda *_a, **_k: None)
    monkeypatch.setattr(
        sc,
        "build_exact_time_comparison",
        lambda frames, **_kwargs: pd.DataFrame(
            {
                "valid_time": times,
                **{
                    f"{name}_streamflow_m3s": frame["streamflow_m3s"]
                    for name, frame in frames.items()
                },
            }
        ),
    )
    monkeypatch.setattr(
        sc,
        "write_timeseries",
        lambda frame, path, **_k: Path(path).write_bytes(
            f"simulated rows: {len(frame)}".encode()
        ),
    )
    return response


def test_station_without_save_keeps_all_data_in_memory(study_settings, mock_retrieval):
    study = sc.StreamflowStudy(
        study_settings,
        reference_utc="2025-07-04T06:00:00Z",
        auto_save=False,
        cross_version_policy="exploratory",
    )
    item = study.compare_station("08165500")
    assert item["folder"] is None
    assert not (Path(study_settings["workspace"]) / "results").exists()
    assert len(item["table"].columns) == 6
    assert item["metadata"]["ids"]["nwm"] == 3586192
    assert not item["metadata"]["nwm"]["gage_crosswalk_verified_for_version"]
    assert item["metadata"]["drainage_area_comparison"]["available"]
    area = item["metadata"]["drainage_area_comparison"]
    assert area["reference_area_km2"] == pytest.approx(745.9)
    assert area["candidate_area_km2"] == pytest.approx(788.3)
    assert area["relative_difference_pct"] == pytest.approx(42.4 / 745.9 * 100)


def test_timing_metadata_records_backend_stages(study_settings, mock_retrieval):
    study = sc.StreamflowStudy(
        study_settings,
        reference_utc="2025-07-04T06:00:00Z",
        auto_save=False,
        cross_version_policy="exploratory",
    )
    item = study.compare_station("08165500")
    metrics = item["metadata"]["timings_seconds"]
    expected = (
        "study_initialization",
        "station_metadata",
        "geoglows_reach_resolution",
        "drainage_area_comparison",
        "source_retrieval_wall",
        "alignment",
        "nwm_geometry",
        "total_request_wall",
    )
    assert all(metrics[name] >= 0 for name in expected)
    assert metrics["per_source"]["USGS"] == 0.05
    assert item["metadata"]["source_rows"]["USGS"] == 2
    assert metrics["source_retrieval_wall"] == 0.13


def test_opt_in_named_export_contains_areas_and_is_idempotent(
    study_settings, mock_retrieval
):
    study = sc.StreamflowStudy(
        study_settings,
        reference_utc="2025-07-04T06:00:00Z",
        auto_save=False,
        cross_version_policy="exploratory",
        save_csv=True,
    )
    item = study.compare_station("08165500")
    target = study.save_record(item)
    assert (target / "08165500.parquet").is_file()
    assert (target / "08165500.csv").is_file()
    metadata = json.loads((target / "08165500.json").read_text())
    assert metadata["drainage_area_comparison"]["reference_area_km2"] == 745.9
    assert metadata["drainage_area_comparison"]["candidate_area_km2"] == 788.3
    assert metadata["ids"]["usgs"] == "08165500"
    assert metadata["saved"] is True
    assert metadata["timings_seconds"]["save"] >= 0
    assert study.save_record(item) == target
    assert len(list(target.parent.iterdir())) == 1


def test_click_queries_without_any_usgs_metadata(study_settings, monkeypatch):
    study = sc.StreamflowStudy(
        study_settings,
        reference_utc="2025-07-04T06:00:00Z",
        auto_save=False,
    )
    monkeypatch.setattr(sc, "load_nearby_reaches", lambda *_a, **_k: object())
    monkeypatch.setattr(
        sc,
        "nearest_reaches",
        lambda *_a, **_k: [{"feature_id": 3586192, "distance_m": 53.0}],
    )
    monkeypatch.setattr(
        sc,
        "fetch_usgs_monitoring_location",
        lambda *_a, **_k: pytest.fail("USGS must not be queried for map clicks"),
    )
    monkeypatch.setattr(study, "_retrieve", lambda **kwargs: kwargs)
    item = study.compare_point(-99.30, 30.08, include_usgs=False)
    assert item["nwm_id"] == 3586192
    assert item["usgs_id"] is None
    assert item["station"] is None
    assert item["resolution_seconds"] >= 0


def test_click_near_gage_can_include_usgs_but_far_click_cannot(
    study_settings, monkeypatch
):
    study = sc.StreamflowStudy(
        study_settings,
        reference_utc="2025-07-04T06:00:00Z",
        cross_version_policy="exploratory",
        auto_save=False,
    )
    monkeypatch.setattr(sc, "load_nearby_reaches", lambda *_a, **_k: object())
    monkeypatch.setattr(
        sc,
        "nearest_reaches",
        lambda *_a, **_k: [{"feature_id": 3586192, "distance_m": 10}],
    )
    monkeypatch.setattr(
        sc,
        "fetch_usgs_monitoring_location",
        lambda *_a, **_k: {"longitude": -99.32, "latitude": 30.07},
    )
    monkeypatch.setattr(study, "_retrieve", lambda **kwargs: kwargs)
    near = study.compare_point(-99.32, 30.07)
    far = study.compare_point(-99.30, 30.07)
    assert near["usgs_id"] == "08165500"
    assert far["usgs_id"] is None
    assert far["station"] is None


@pytest.fixture
def fake_widget_library(monkeypatch):
    install_fake_widgets(monkeypatch)


def test_station_and_click_maps_are_independent(fake_widget_library, monkeypatch):
    from streamflow_getter import interactive_map as module

    plots = []
    monkeypatch.setattr(module, "plot_comparison", lambda result: plots.append(result))
    station = map_result("08165500", 3586192)
    retrieved = []

    class Study:
        def compare_point(self, longitude, latitude):
            retrieved.append((longitude, latitude))
            return map_result(None, 101 + len(retrieved))

        def save_record(self, record):
            record["folder"] = Path("/fake/saved")
            return record["folder"]

    view = module.StreamflowMap(Study(), station)
    assert view.station_result is station
    assert view.result is None
    assert len(view.station_rivers.layers) == 3
    assert view.rivers.layers == ()
    assert view.click_save.disabled
    assert len(plots) == 1 and plots[0] is station

    async def exercise():
        view._on_interaction(type="click", coordinates=(30.07, -99.30))
        assert view.result is None
        await view.task
        first = view.result
        view._on_interaction(type="click", coordinates=(30.08, -99.29))
        assert view.result is None
        await view.task
        return first

    first = asyncio.run(exercise())
    assert retrieved == [(-99.30, 30.07), (-99.29, 30.08)]
    assert first["metadata"]["ids"]["usgs"] is None
    assert view.result["metadata"]["ids"]["nwm"] == 103
    assert "not associated" in view.status.value
    assert view.station_result["metadata"]["ids"]["usgs"] == "08165500"
    assert len(view.station_rivers.layers) == 3
    assert len(view.rivers.layers) == 3
    assert plots[0] is station
    assert plots[-1] is view.result
    assert not view.click_save.disabled
    view._on_save_click(None)
    assert view.result["folder"] == Path("/fake/saved")
    assert station["folder"] is None
    view._on_save_station(None)
    assert station["folder"] == Path("/fake/saved")
    view.close()
    assert view.widget.closed


def test_click_error_does_not_restore_stale_plot(fake_widget_library, monkeypatch):
    from streamflow_getter import interactive_map as module

    monkeypatch.setattr(module, "plot_comparison", lambda *_args: object())

    class Study:
        def compare_point(self, *_args):
            raise RuntimeError("source offline")

    view = module.StreamflowMap(Study(), map_result("08165500", 3586192))

    async def click():
        view._on_interaction(type="click", coordinates=(30.08, -99.28))
        await view.task

    asyncio.run(click())
    assert view.result is None
    assert view.rivers.layers == ()
    assert view.click_save.disabled
    assert "source offline" in view.status.value
    assert view.station_result["metadata"]["ids"]["usgs"] == "08165500"
    view.close()
