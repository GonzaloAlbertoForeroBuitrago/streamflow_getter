"""Tests of the versioned comparison export."""

import json

import pandas as pd
import pytest

from streamflow_getter import ComparisonResult
from streamflow_getter.output import manifest_path_for


@pytest.fixture
def record():
    table = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(
                [
                    "2025-07-04T06:00:00Z",
                    "2025-07-04T07:00:00Z",
                ],
                utc=True,
            ),
            "usgs_streamflow_m3s": [1.25, 1.50],
            "analysis_assim_streamflow_m3s": [1.20, None],
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
            "geoglows": {"selection_error": None},
            "hydrologic_equivalence_verified": False,
            "units": "m3/s",
            "source_rows": {"usgs": 2, "analysis_assim": 1},
            "saved": False,
        },
        "nwm_geojson": {
            "type": "FeatureCollection",
            "features": [],
        },
        "geoglows_geometry": {
            "type": "LineString",
            "coordinates": [
                [-99.32, 30.07],
                [-99.31, 30.08],
            ],
        },
        "folder": None,
    }


def test_csv_export_and_manifest(tmp_path, record):
    result = ComparisonResult(record)

    data, manifest = result.export(tmp_path / "comparison.csv")

    assert data.is_file()
    assert manifest.is_file()
    assert manifest == manifest_path_for(data)

    payload = json.loads(manifest.read_text())

    assert payload["schema"] == "streamflow_getter.comparison_export.v1"
    assert payload["data_file"] == "comparison.csv"
    assert payload["data_format"] == "csv"
    assert payload["metadata"]["ids"] == record["metadata"]["ids"]
    assert payload["metadata"]["units"] == "m3/s"
    assert payload["geometries"]["nwm"] == record["nwm_geojson"]
    assert payload["geometries"]["geoglows"] == record["geoglows_geometry"]
    assert payload["warnings"]

    assert len(pd.read_csv(data)) == 2
    assert result.table is record["table"]
    assert record["metadata"]["saved"] is False
    assert record["folder"] is None


def test_parquet_preserves_utc_and_missing_values(tmp_path, record):
    pytest.importorskip("pyarrow")

    result = ComparisonResult(record)
    data, _ = result.export(tmp_path / "comparison.parquet")

    recovered = pd.read_parquet(data)

    pd.testing.assert_frame_equal(
        recovered,
        record["table"],
        check_exact=True,
    )


def test_export_refuses_overwrite(tmp_path, record):
    result = ComparisonResult(record)

    data, manifest = result.export(tmp_path / "comparison.csv")

    before_data = data.read_bytes()
    before_manifest = manifest.read_bytes()

    with pytest.raises(FileExistsError):
        result.export(data)

    assert data.read_bytes() == before_data
    assert manifest.read_bytes() == before_manifest


def test_invalid_geometry_creates_no_files(tmp_path, record):
    record["geoglows_geometry"] = object()

    result = ComparisonResult(record)
    destination = tmp_path / "comparison.csv"

    with pytest.raises(TypeError, match="GEOGLOWS geometry"):
        result.export(destination)

    assert not destination.exists()
    assert not manifest_path_for(destination).exists()


def test_geo_interface_is_supported(tmp_path, record):
    class Geometry:
        __geo_interface__ = {
            "type": "LineString",
            "coordinates": [[-99.32, 30.07], [-99.31, 30.08]],
        }

    record["geoglows_geometry"] = Geometry()

    result = ComparisonResult(record)
    _, manifest = result.export(tmp_path / "comparison.csv")

    payload = json.loads(manifest.read_text())

    assert payload["geometries"]["geoglows"] == Geometry.__geo_interface__
