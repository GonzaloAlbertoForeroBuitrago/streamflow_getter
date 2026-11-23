"""Focused regression tests for UTC axes and recoverable map interactions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd

from _widget_test_support import install_fake_widgets, map_result
from streamflow_getter import interactive_map as ui
from streamflow_getter.station_comparison import plot_comparison


def test_click_plot_uses_utc_iso_strings_not_nanosecond_epoch():
    table = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(
                ["2025-07-04T06:00:00Z", "2025-07-04T07:00:00Z"]
            ),
            "usgs_streamflow_m3s": [4.5, 5.5],
            "geoglows_streamflow_m3s": [3.2, 5.0],
        }
    )
    figure = plot_comparison({"table": table})
    assert figure.layout.xaxis.type == "date"
    assert len(figure.data) == 2
    for trace in figure.data:
        assert trace.mode == "lines"
        assert all(isinstance(value, str) and value.endswith("Z") for value in trace.x)
        assert trace.x[0].startswith("2025-07-04T06:00:00")


def test_unclosed_polygon_is_not_forwarded_to_leaflet():
    malformed = {
        "type": "Polygon",
        "coordinates": [[[-99.32, 30.07], [-99.31, 30.08], [-99.33, 30.09]]],
    }
    assert ui.StreamflowMap._river_geojson(malformed) is None
    valid = {
        "type": "LineString",
        "coordinates": [[-99.33, 30.07], [-99.31, 30.08]],
    }
    assert len(ui.StreamflowMap._river_geojson(valid)["features"]) == 1


def test_failed_click_does_not_disable_future_hydrographs(monkeypatch):
    from shapely.errors import GEOSException

    install_fake_widgets(monkeypatch)
    monkeypatch.setattr(
        ui,
        "plot_comparison",
        lambda *_args: SimpleNamespace(
            data=(SimpleNamespace(name="NWM, current click"),),
            layout=SimpleNamespace(to_plotly_json=lambda: {}),
        ),
    )

    class Study:
        reference = datetime(2025, 7, 4, 6, tzinfo=UTC)
        attempts = 0

        def compare_point(self, longitude, latitude):
            self.attempts += 1
            if self.attempts == 1:
                raise GEOSException(
                    "Points of LinearRing do not form a closed linestring"
                )
            return map_result(None, 1234)

        def for_reference(self, _utc):
            return self

    viewer = ui.StreamflowMap(Study(), map_result("08165500", 3586192))

    async def exercise():
        viewer._on_interaction(type="click", coordinates=(30.07, -99.32))
        await viewer.task
        assert viewer.result is None
        assert not viewer.busy
        assert "Click failed" in viewer.status.value
        viewer._on_interaction(type="click", coordinates=(30.08, -99.31))
        await viewer.task

    asyncio.run(exercise())
    assert viewer.result["metadata"]["ids"]["usgs"] is None
    assert viewer.result["metadata"]["ids"]["nwm"] == 1234
    assert len(viewer.hydrograph.data) == 1
    assert not viewer.click_save.disabled
    assert viewer.station_result["metadata"]["ids"]["usgs"] == "08165500"
    viewer.close()


def test_invalid_remote_polygon_does_not_prevent_next_plot(monkeypatch):
    install_fake_widgets(monkeypatch)
    monkeypatch.setattr(
        ui,
        "plot_comparison",
        lambda *_args: SimpleNamespace(
            data=(SimpleNamespace(name="GEOGLOWS"),),
            layout=SimpleNamespace(to_plotly_json=lambda: {}),
        ),
    )

    class Study:
        reference = datetime(2025, 7, 4, 6, tzinfo=UTC)

        def compare_point(self, longitude, latitude):
            result = map_result(None, 777)
            result["geoglows_geometry"] = {
                "type": "Polygon",
                "coordinates": [[[-99.32, 30.07], [-99.31, 30.08]]],
            }
            return result

        def for_reference(self, _utc):
            return self

    view = ui.StreamflowMap(Study(), map_result("08165500", 3586192))

    async def exercise():
        view._on_interaction(type="click", coordinates=(30.08, -99.31))
        await view.task

    asyncio.run(exercise())
    assert len(view.hydrograph.data) == 1
    assert view.result is not None
    assert view.status.value.startswith("<b>USGS:</b>")
    assert not view.busy
    view.close()


def test_optional_geoglows_geos_error_preserves_nwm_and_usgs(monkeypatch, tmp_path):
    from shapely.errors import GEOSException

    from streamflow_getter import station_comparison as sc

    study = object.__new__(sc.StreamflowStudy)
    study.reference = pd.Timestamp("2025-07-04T06:00:00Z")
    study.start = study.reference - pd.Timedelta(hours=3)
    study.end = study.reference + pd.Timedelta(hours=6)
    study.version = "3.0"
    study.radius_m = 3000
    study.max_workers = 5
    study.workspace = tmp_path
    study.hydrofabric = tmp_path / "nwm.gdb"
    study.initialization_seconds = 0.1
    study.auto_save = False
    study.backend_revision = "offline-test"
    study.crosswalk_compatible = False
    study.policy = "exploratory"
    study.routelink = tmp_path / "RouteLink_CONUS.nc"
    study.provenance = {"network_version": "3.1"}

    def fail_geoglows(*_a, **_k):
        raise GEOSException("Points of LinearRing do not form a closed linestring")

    monkeypatch.setattr(sc, "nearest_geoglows_reach", fail_geoglows)
    times = pd.to_datetime(["2025-07-04T06:00:00Z"])
    frames = {
        "USGS": pd.DataFrame({"valid_time": times, "streamflow_m3s": [3.0]}),
        "NWM analysis_assim": pd.DataFrame(
            {"valid_time": times, "streamflow_m3s": [2.0]}
        ),
    }
    monkeypatch.setattr(
        sc,
        "fetch_multi_source_streamflow",
        lambda *_a, **_k: SimpleNamespace(
            series=frames,
            source_timings_seconds={"USGS": 0.01, "NWM analysis_assim": 0.02},
            total_elapsed_seconds=0.03,
        ),
    )
    monkeypatch.setattr(
        sc,
        "build_exact_time_comparison",
        lambda *_a, **_k: pd.DataFrame(
            {
                "valid_time": times,
                "usgs_streamflow_m3s": [3.0],
                "analysis_assim_streamflow_m3s": [2.0],
            }
        ),
    )
    monkeypatch.setattr(sc, "_read_geojson", lambda *_a, **_k: None)
    monkeypatch.setattr(
        sc,
        "compare_drainage_areas",
        lambda *_a, **_k: {"available": False, "message": "area unavailable"},
    )
    outcome = study._retrieve(
        longitude=-99.32,
        latitude=30.07,
        nwm_id=3586192,
        usgs_id="08165500",
        station={"drainage_area_km2": 745.9},
        method="routelink_cross_version_provisional",
        nwm_distance_m=98.7,
    )
    assert outcome["metadata"]["ids"]["nwm"] == 3586192
    assert outcome["metadata"]["ids"]["usgs"] == "08165500"
    assert outcome["metadata"]["ids"]["geoglows"] is None
    assert "GEOSException" in outcome["metadata"]["geoglows"]["selection_error"]
    assert "analysis_assim_streamflow_m3s" in outcome["table"]
