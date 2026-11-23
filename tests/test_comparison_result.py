"""Tests for the non-copying scientific result interface."""

import pandas as pd
import pytest

from streamflow_getter import ComparisonResult, StreamflowClient


@pytest.fixture
def record():
    table = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(["2025-07-04T06:00:00Z"], utc=True),
            "usgs_streamflow_m3s": [1.25],
            "analysis_assim_streamflow_m3s": [1.20],
        }
    )

    return {
        "table": table,
        "metadata": {
            "schema": "streamflow_getter.station_comparison.v19",
            "ids": {
                "usgs": "08165500",
                "nwm": 3586192,
                "geoglows": 770586851,
            },
            "nwm": {
                "gage_crosswalk_verified_for_version": False,
                "hydrofabric_network_compatibility_verified": False,
            },
            "geoglows": {
                "selection_error": "Invalid remote geometry",
            },
            "hydrologic_equivalence_verified": False,
            "source_rows": {"usgs": 1, "analysis_assim": 1},
            "units": "m3/s",
        },
        "nwm_geojson": {"type": "FeatureCollection", "features": []},
        "geoglows_geometry": None,
        "folder": None,
    }


def test_result_preserves_original_data(record):
    result = ComparisonResult(record)

    assert result.raw is record
    assert result.table is record["table"]
    assert result.metadata is record["metadata"]
    assert result.ids is record["metadata"]["ids"]
    assert result.table["usgs_streamflow_m3s"].iloc[0] == 1.25
    assert result.source_rows["usgs"] == 1


def test_result_preserves_network_evidence(record):
    result = ComparisonResult(record)

    assert result.network["nwm"] is record["metadata"]["nwm"]
    assert result.network["hydrologic_equivalence_verified"] is False
    assert result.geometries["nwm"] is record["nwm_geojson"]
    assert len(result.warnings) == 4
    assert any("GEOGLOWS selection error" in w for w in result.warnings)


def test_result_rejects_invalid_contract():
    with pytest.raises(TypeError, match="DataFrame"):
        ComparisonResult({"table": None, "metadata": {"ids": {}}})

    with pytest.raises(ValueError, match="valid_time"):
        ComparisonResult(
            {
                "table": pd.DataFrame({"flow": [1]}),
                "metadata": {"ids": {}},
            }
        )


def test_client_result_methods_reuse_existing_study(monkeypatch, record):
    references = []

    class FakeStudy:
        def compare_station(self, gage_id):
            assert gage_id == "08165500"
            return record

        def compare_point(self, lon, lat, *, include_usgs=True):
            assert (lon, lat) == (-99.32, 30.07)
            assert include_usgs is False
            return record

    def fake_study(self, reference_utc):
        references.append(reference_utc)
        return FakeStudy()

    monkeypatch.setattr(StreamflowClient, "study", fake_study)

    client = StreamflowClient({"workspace": "test"})
    reference = "2025-07-04T06:00:00Z"

    station = client.compare_station_result("08165500", reference_utc=reference)
    point = client.compare_point_result(
        -99.32,
        30.07,
        reference_utc=reference,
        include_usgs=False,
    )

    assert isinstance(station, ComparisonResult)
    assert station.raw is record
    assert point.raw is record
    assert references == [reference, reference]
