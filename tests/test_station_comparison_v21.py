"""v21: persistent hydrology plot, independent UTC date, no cross-click USGS leak."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from _widget_test_support import install_fake_widgets, map_result
from streamflow_getter import station_comparison as sc


@pytest.fixture
def fake_widgets(monkeypatch):
    install_fake_widgets(monkeypatch)


def test_persistent_chart_updates_after_click_and_clears_old_usgs(
    fake_widgets, monkeypatch
):
    from streamflow_getter import interactive_map as ui

    initial = map_result("08165500", 3586192)
    clicks = []

    class Study:
        reference = datetime(2025, 7, 4, 6, tzinfo=UTC)

        def compare_point(self, longitude, latitude):
            clicks.append((longitude, latitude))
            return map_result(None, 400 + len(clicks))

        def for_reference(self, _value):
            return self

    # An actual plotly-like Figure is passed directly into the live widget,
    # never displayed asynchronously using IPython Output() or display().
    figures = []

    def plot(item):
        figures.append(item)
        return SimpleNamespace(
            data=(SimpleNamespace(name=f"NWM_{item['metadata']['ids']['nwm']}"),),
            layout=SimpleNamespace(to_plotly_json=lambda: {"title": "Current flow"}),
        )

    monkeypatch.setattr(ui, "plot_comparison", plot)
    view = ui.StreamflowMap(Study(), initial)
    assert view.hydrograph.data == ()
    assert view.reference_input.value == "2025-07-04T06:00:00Z"

    async def exercise():
        view._on_interaction(type="click", coordinates=(30.07, -99.30))
        await view.task
        assert [trace.name for trace in view.hydrograph.data] == ["NWM_401"]
        assert view.result["metadata"]["ids"]["usgs"] is None
        view._on_interaction(type="click", coordinates=(30.08, -99.29))
        assert view.result is None
        assert view.hydrograph.data == ()
        await view.task

    asyncio.run(exercise())
    assert [trace.name for trace in view.hydrograph.data] == ["NWM_402"]
    assert view.station_result["metadata"]["ids"]["usgs"] == "08165500"
    assert clicks == [(-99.30, 30.07), (-99.29, 30.08)]
    assert figures[-1] is view.result
    view.close()


def test_new_utc_date_is_independent_and_reused_across_clicks(
    fake_widgets, monkeypatch
):
    from streamflow_getter import interactive_map as ui

    switched = []
    compared = []

    class Study:
        reference = datetime(2025, 7, 4, 6, tzinfo=UTC)

        def for_reference(self, timestamp):
            switched.append(timestamp)
            return DateStudy(timestamp)

        def compare_point(self, *_args):
            raise AssertionError("The old study must not query the new date")

    class DateStudy:
        def __init__(self, timestamp):
            self.timestamp = timestamp

        def compare_point(self, longitude, latitude):
            compared.append((self.timestamp, longitude, latitude))
            item = map_result(None, 700 + len(compared))
            item["metadata"]["utc_window"] = {
                "start": self.timestamp,
                "end": self.timestamp,
            }
            return item

    monkeypatch.setattr(
        ui,
        "plot_comparison",
        lambda *_a: SimpleNamespace(
            data=(SimpleNamespace(name="GEOGLOWS"),),
            layout=SimpleNamespace(to_plotly_json=lambda: {}),
        ),
    )
    view = ui.StreamflowMap(Study(), map_result("08165500", 3586192))
    view.reference_input.value = "2026-09-10T06:00:00Z"

    async def exercise():
        view._on_interaction(type="click", coordinates=(30.08, -99.30))
        await view.task
        view._on_interaction(type="click", coordinates=(30.09, -99.29))
        await view.task

    asyncio.run(exercise())
    assert switched == ["2026-09-10T06:00:00Z"]
    assert len(compared) == 2
    assert len(view.hydrograph.data) == 1
    assert "UTC:" in view.status.value
    assert view.station_result["metadata"]["ids"]["usgs"] == "08165500"
    view.close()


def test_invalid_date_reports_error_without_old_plot(fake_widgets, monkeypatch):
    from streamflow_getter import interactive_map as ui

    class Study:
        reference = datetime(2025, 7, 4, 6, tzinfo=UTC)

        def for_reference(self, value):
            raise ValueError(f"Expected hourly UTC, got {value}")

    monkeypatch.setattr(
        ui,
        "plot_comparison",
        lambda *_a: SimpleNamespace(
            data=(), layout=SimpleNamespace(to_plotly_json=lambda: {})
        ),
    )
    view = ui.StreamflowMap(Study(), map_result("08165500", 3586192))
    view.reference_input.value = "bad date"

    async def exercise():
        view._on_interaction(type="click", coordinates=(30.08, -99.28))
        await view.task

    asyncio.run(exercise())
    assert "Expected hourly UTC" in view.status.value
    assert view.result is None
    assert view.hydrograph.data == ()
    assert view.click_save.disabled
    view.close()


def test_study_reference_clone_preserves_original_and_avoids_route_reload(monkeypatch):
    monkeypatch.setattr(sc, "_window_nwm_version", lambda *_a: "3.0")
    study = object.__new__(sc.StreamflowStudy)
    study.reference = sc.pd.Timestamp("2025-07-04T06:00:00Z")
    study.start = study.reference - sc.pd.Timedelta(hours=3)
    study.end = study.reference + sc.pd.Timedelta(hours=6)
    study.version = "3.0"
    study._hours_before = 3
    study._hours_after = 6
    study._requested_version = "auto"
    study.gages = {"08165500": 3586192}
    study.crosswalk_compatible = False

    later = study.for_reference("2025-07-05T06:00:00Z")
    assert later.reference == sc.pd.Timestamp("2025-07-05T06:00:00Z")
    assert study.reference == sc.pd.Timestamp("2025-07-04T06:00:00Z")
    assert later.gages is study.gages
    assert later is not study
    assert later.start == sc.pd.Timestamp("2025-07-05T03:00:00Z")
    assert later.end == sc.pd.Timestamp("2025-07-05T12:00:00Z")


def test_same_utc_reference_does_not_rebuild_study():
    study = object.__new__(sc.StreamflowStudy)
    study.reference = sc.pd.Timestamp("2025-07-04T06:00:00Z")
    assert study.for_reference("2025-07-04T06:00:00Z") is study


def test_date_only_reuses_existing_reference_hour(monkeypatch):
    monkeypatch.setattr(sc, "_window_nwm_version", lambda *_a: "3.0")
    study = object.__new__(sc.StreamflowStudy)
    study.reference = sc.pd.Timestamp("2025-07-04T06:00:00Z")
    study.version = "3.0"
    study._hours_before = 3
    study._hours_after = 6
    study._requested_version = "auto"
    cloned = study.for_reference("2025-07-05")
    assert cloned.reference == sc.pd.Timestamp("2025-07-05T06:00:00Z")
