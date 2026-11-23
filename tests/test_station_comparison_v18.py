"""Offline integration-contract tests for the optional v18 workflow modules."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from streamflow_getter import station_comparison as sc


@pytest.fixture
def settings(tmp_path, monkeypatch):
    routelink = tmp_path / "RouteLink_CONUS.nc"
    routelink.touch()
    hydrofabric = tmp_path / "NWM_v3_hydrofabric.gdb"
    hydrofabric.mkdir()
    monkeypatch.setattr(sc, "validate_hydrofabric_crs", lambda _: None)
    monkeypatch.setattr(sc, "resolve_operational_nwm_version", lambda _: "3.0")
    monkeypatch.setattr(
        sc,
        "load_gage_index_with_provenance",
        lambda path, **_: (
            {"08165500": 3586192},
            {"network_version": "3.1", "crosswalk_sha256": "mock-sha"},
        ),
    )
    monkeypatch.setattr(
        sc,
        "build_nwm_to_usgs_index",
        lambda index: {value: key for key, value in index.items()},
    )

    def version_guard(requested, actual):
        if requested != (actual,):
            raise ValueError("Network versions differ")

    monkeypatch.setattr(sc, "validate_routelink_compatibility", version_guard)
    return {
        "workspace": str(tmp_path / "workspace"),
        "routelink": str(routelink),
        "hydrofabric": str(hydrofabric),
    }


def test_hunt_lookup_requires_no_hardcoded_nwm_id(settings, monkeypatch):
    station = {
        "latitude": 30.07,
        "longitude": -99.32,
        "drainage_area_km2": 200.0,
    }
    monkeypatch.setattr(sc, "fetch_usgs_monitoring_location", lambda *_a, **_k: station)
    study = sc.StreamflowStudy(
        settings,
        reference_utc="2025-07-04T06:00:00Z",
        cross_version_policy="exploratory",
    )
    monkeypatch.setattr(study, "_retrieve", lambda **kwargs: kwargs)
    result = study.compare_station("08165500")
    assert result["nwm_id"] == 3586192
    assert result["method"] == "routelink_cross_version_provisional"
    assert "INCOMPATIBLE" in study.network_message


def test_strict_policy_never_assumes_31_is_30(settings, monkeypatch):
    monkeypatch.setattr(
        sc,
        "fetch_usgs_monitoring_location",
        lambda *_a, **_k: {"longitude": -99.32, "latitude": 30.07},
    )
    study = sc.StreamflowStudy(settings, reference_utc="2025-07-04T06:00:00Z")
    monkeypatch.setattr(study, "_retrieve", lambda **kwargs: kwargs)
    result = study.compare_station("08165500")
    assert result["nwm_id"] is None
    assert result["usgs_id"] == "08165500"


def test_compatible_30_routelink_is_preferred(settings, monkeypatch, tmp_path):
    path30 = tmp_path / "RouteLink_3_0.nc"
    path30.touch()
    settings["routelink_3_0"] = str(path30)

    def read_version(path, **_kwargs):
        if Path(path) == path30:
            return {"08165500": 123}, {"network_version": "3.0"}
        return {"08165500": 3586192}, {"network_version": "3.1"}

    monkeypatch.setattr(sc, "load_gage_index_with_provenance", read_version)
    study = sc.StreamflowStudy(settings, reference_utc="2025-07-04T06:00:00Z")
    assert study.crosswalk_compatible
    assert study.gages["08165500"] == 123
    assert study.routelink == path30


def test_retrieval_saves_drainage_area_comparison(settings, monkeypatch):
    study = sc.StreamflowStudy(
        settings,
        reference_utc="2025-07-04T06:00:00Z",
        cross_version_policy="exploratory",
    )
    monkeypatch.setattr(
        sc,
        "nearest_geoglows_reach",
        lambda *_a, **_k: {
            "river_id": 12345,
            "distance_m": 92.0,
            "upstream_area_km2": 300.0,
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        },
    )
    times = pd.to_datetime(["2025-07-04T06:00:00Z", "2025-07-04T07:00:00Z"])
    response = SimpleNamespace(
        series={
            "USGS": pd.DataFrame({"valid_time": times, "streamflow_m3s": [2, 4]}),
            "GEOGLOWS retrospective": pd.DataFrame(
                {"valid_time": times, "streamflow_m3s": [1, 3]}
            ),
        },
        source_timings_seconds={"USGS": 0.1},
        total_elapsed_seconds=0.25,
    )
    monkeypatch.setattr(sc, "fetch_multi_source_streamflow", lambda *_a, **_k: response)
    monkeypatch.setattr(sc, "_read_geojson", lambda *_a, **_k: None)
    monkeypatch.setattr(
        sc,
        "build_exact_time_comparison",
        lambda *_a, **_k: pd.DataFrame(
            {
                "valid_time": times,
                "USGS_streamflow_m3s": [2.0, 4.0],
                "GEOGLOWS retrospective_streamflow_m3s": [1.0, 3.0],
            }
        ),
    )
    monkeypatch.setattr(
        sc,
        "write_timeseries",
        lambda frame, path, **_kwargs: Path(path).write_text("test parquet"),
    )
    output = study._retrieve(
        longitude=-99.32,
        latitude=30.07,
        nwm_id=3586192,
        usgs_id="08165500",
        station={"drainage_area_km2": 200.0},
        method="routelink_cross_version_provisional",
        nwm_distance_m=None,
    )
    area = output["metadata"]["drainage_area_comparison"]
    assert area["available"]
    assert area["reference_area_km2"] == 200.0
    assert area["candidate_area_km2"] == 300.0
    assert area["relative_difference_pct"] == pytest.approx(50.0)
    assert not output["metadata"]["nwm"]["gage_crosswalk_verified_for_version"]
    assert (output["folder"] / "streamflow.parquet").is_file()
    assert (output["folder"] / "metadata.json").is_file()
    figure = sc.plot_comparison(output)
    assert {trace.name for trace in figure.data} == {"usgs", "geoglows"}
    assert all(trace.mode == "lines" for trace in figure.data)
    assert {trace.name: trace.line.color for trace in figure.data} == {
        "usgs": "#111111",
        "geoglows": "#2563EB",
    }


def test_click_without_associated_gage_preserves_nwm(settings, monkeypatch):
    study = sc.StreamflowStudy(
        settings,
        reference_utc="2025-07-04T06:00:00Z",
        cross_version_policy="exploratory",
    )
    monkeypatch.setattr(sc, "load_nearby_reaches", lambda *_a, **_k: object())
    monkeypatch.setattr(
        sc,
        "nearest_reaches",
        lambda *_a, **_k: [{"feature_id": 999, "distance_m": 120}],
    )
    monkeypatch.setattr(study, "_retrieve", lambda **kwargs: kwargs)
    item = study.compare_point(-99.31, 30.07)
    assert item["nwm_id"] == 999
    assert item["usgs_id"] is None
    assert item["method"] == "local_hydrofabric_point"


def test_full_five_trace_colors_and_line_modes():
    times = pd.to_datetime(["2025-07-04T06:00:00Z", "2025-07-04T07:00:00Z"])
    payload = {
        "table": pd.DataFrame(
            {
                "valid_time": times,
                "USGS_streamflow_m3s": [5, 6],
                "GEOGLOWS retrospective_streamflow_m3s": [1, 2],
                "NWM analysis_assim_no_da_streamflow_m3s": [2, 3],
                "NWM analysis_assim_streamflow_m3s": [3, 4],
                "NWM short_range_streamflow_m3s": [4, 5],
            }
        )
    }
    figure = sc.plot_comparison(payload)
    assert len(figure.data) == 5
    assert {trace.name: trace.line.color for trace in figure.data} == sc.LINE_COLORS
    assert all(trace.mode == "lines" for trace in figure.data)


def test_clickable_map_replaces_plot_and_omits_missing_usgs(monkeypatch):
    """The v18 viewer entrypoint still works with the independent v19 maps."""
    import asyncio

    from _widget_test_support import install_fake_widgets, map_result
    from streamflow_getter import interactive_map as viewer_module

    install_fake_widgets(monkeypatch)
    from plotly import graph_objects as go

    monkeypatch.setattr(
        viewer_module,
        "plot_comparison",
        lambda *_args: go.Figure(
            data=[
                go.Scatter(
                    x=[0, 1],
                    y=[1, 2],
                    mode="lines",
                    name="NWM",
                )
            ]
        ),
    )

    class Study:
        def compare_point(self, longitude, latitude):
            assert (longitude, latitude) == (-99.32, 30.07)
            return map_result(None, 77)

    viewer = viewer_module.StreamflowMap(Study(), map_result("08165500", 77))
    assert len(viewer.station_rivers.layers) == 3
    assert viewer.rivers.layers == ()

    async def click():
        viewer._on_interaction(type="click", coordinates=(30.07, -99.32))
        await viewer.task

    asyncio.run(click())
    assert viewer.result["metadata"]["ids"]["usgs"] is None
    assert len(viewer.hydrograph.data) == 1
    assert viewer.hydrograph.data[0].mode == "lines"
    assert "not associated" in viewer.status.value
    assert len(viewer.rivers.layers) == 3
    assert viewer.station_result["metadata"]["ids"]["usgs"] == "08165500"
    viewer.close()
    assert viewer.widget.closed
