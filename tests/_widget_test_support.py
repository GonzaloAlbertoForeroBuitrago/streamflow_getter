"""Headless widget doubles shared by the v18/v19 map regression tests."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from types import ModuleType

import pandas as pd


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.value = kwargs.get("value", "")
        self.disabled = kwargs.get("disabled", False)
        self.kwargs = kwargs
        self.children = args[0] if args else []
        self.closed = False
        self.click_callback = None

    def close(self):
        self.closed = True

    def on_click(self, callback):
        self.click_callback = callback


class FakeMap(FakeWidget):
    def add(self, layer):
        self.layer = layer

    def on_interaction(self, callback, remove=False):
        self.callback = None if remove else callback


class FakeLayerGroup(FakeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.layers = ()


class FakeFigureWidget(FakeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = ()
        self.layout = SimpleNamespace(title=None)
        self.layout_options = {}

    def batch_update(self):
        return nullcontext()

    def add_traces(self, traces):
        self.data += tuple(traces)

    def update_layout(self, **kwargs):
        self.layout_options.update(kwargs)


class FakeOutput(FakeWidget):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def install_fake_widgets(monkeypatch):
    """Replace optional ipyleaflet/ipywidgets only during one test."""
    import IPython.display as output_module

    leaflet = ModuleType("ipyleaflet")
    for name, cls in {
        "Map": FakeMap,
        "LayerGroup": FakeLayerGroup,
        "GeoJSON": FakeWidget,
        "CircleMarker": FakeWidget,
    }.items():
        setattr(leaflet, name, cls)
    widgets = ModuleType("ipywidgets")
    for name, cls in {
        "HTML": FakeWidget,
        "Layout": FakeWidget,
        "Output": FakeOutput,
        "VBox": FakeWidget,
        "Button": FakeWidget,
        "Text": FakeWidget,
    }.items():
        setattr(widgets, name, cls)
    import plotly.graph_objects as go

    monkeypatch.setattr(go, "FigureWidget", FakeFigureWidget)
    monkeypatch.setitem(sys.modules, "ipyleaflet", leaflet)
    monkeypatch.setitem(sys.modules, "ipywidgets", widgets)
    monkeypatch.setattr(output_module, "display", lambda *_a: None)
    monkeypatch.setattr(output_module, "clear_output", lambda **_k: None)


def map_result(site_id: str | None, nwm_id: int):
    return {
        "table": pd.DataFrame({"valid_time": [datetime.now(UTC)]}),
        "metadata": {
            "ids": {"usgs": site_id, "nwm": nwm_id, "geoglows": 99},
            "point_epsg4326": {"longitude": -99.32, "latitude": 30.07},
            "nwm": {
                "selection_method": "local_hydrofabric_point",
                "gage_crosswalk_verified_for_version": False,
            },
            "drainage_area_comparison": {
                "available": bool(site_id),
                "message": "USGS area: 745.9 km²; GEOGLOWS area: 788.3 km²",
            },
            "timings_seconds": {"total_request_wall": 0.18},
        },
        "nwm_geojson": {"type": "FeatureCollection", "features": []},
        "geoglows_geometry": {
            "type": "LineString",
            "coordinates": [[-99.34, 30.06], [-99.31, 30.08]],
        },
        "folder": None,
    }
