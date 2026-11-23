"""Tests for the lightweight public API."""

import json
import sys
from types import ModuleType

import pytest

from streamflow_getter import StreamflowClient


def test_client_configuration_is_not_modified():
    settings = {"routelink": "original.nc"}
    client = StreamflowClient(settings)

    settings["routelink"] = "changed.nc"

    assert client.settings["routelink"] == "original.nc"
    assert client._options["auto_save"] is False


def test_client_loads_json_configuration(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"workspace": "/tmp/study"}))

    client = StreamflowClient.from_config(path)

    assert client.settings["workspace"] == "/tmp/study"


def test_client_rejects_invalid_configuration(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("[]")

    with pytest.raises(ValueError, match="JSON object"):
        StreamflowClient.from_config(path)


def test_client_delegates_to_existing_backend(monkeypatch):
    calls = []

    class FakeStudy:
        def __init__(self, settings, **kwargs):
            calls.append(("init", settings, kwargs))

        def compare_station(self, gage_id):
            return {"gage": gage_id}

        def compare_point(self, lon, lat, *, include_usgs=True):
            return {
                "longitude": lon,
                "latitude": lat,
                "include_usgs": include_usgs,
            }

    fake_module = ModuleType("streamflow_getter.station_comparison")
    fake_module.StreamflowStudy = FakeStudy

    monkeypatch.setitem(
        sys.modules,
        "streamflow_getter.station_comparison",
        fake_module,
    )

    client = StreamflowClient({"workspace": "test"})
    reference = "2025-07-04T06:00:00Z"

    station = client.compare_station("08165500", reference_utc=reference)
    point = client.compare_point(
        -99.32, 30.07, reference_utc=reference, include_usgs=False
    )

    assert station == {"gage": "08165500"}
    assert point["include_usgs"] is False
    assert all(call[2]["reference_utc"] == reference for call in calls)
    assert all(call[2]["auto_save"] is False for call in calls)
