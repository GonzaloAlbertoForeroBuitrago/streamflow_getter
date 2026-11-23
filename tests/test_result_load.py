"""Regression tests for comparison export loading."""

import json

import numpy as np
import pandas as pd
import pytest

from streamflow_getter import ComparisonResult


@pytest.fixture
def result():
    frame = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(
                [
                    "2025-07-04T06:00:00Z",
                    "2025-07-04T07:00:00Z",
                ],
                utc=True,
            ),
            "usgs_streamflow_m3s": [1.25, 0.0],
            "analysis_assim_streamflow_m3s": [np.nan, 1.2],
        }
    )

    return ComparisonResult(
        {
            "table": frame,
            "metadata": {
                "schema": "streamflow_getter.station_comparison.v19",
                "ids": {
                    "usgs": "08165500",
                    "nwm": 3586192,
                    "geoglows": None,
                },
                "nwm": {
                    "gage_crosswalk_verified_for_version": False,
                    "hydrofabric_network_compatibility_verified": False,
                },
                "geoglows": {"selection_error": None},
                "hydrologic_equivalence_verified": False,
                "units": "m3/s",
            },
            "nwm_geojson": {
                "type": "FeatureCollection",
                "features": [],
            },
            "geoglows_geometry": None,
            "folder": None,
        }
    )


def test_parquet_roundtrip(tmp_path, result):
    pytest.importorskip("pyarrow")

    data, _ = result.export(tmp_path / "study.parquet")
    loaded = ComparisonResult.load(data)

    pd.testing.assert_frame_equal(
        loaded.table,
        result.table,
        check_exact=True,
    )
    assert loaded.ids == result.ids
    assert loaded.geometries == result.geometries
    assert loaded.warnings == result.warnings


def test_csv_roundtrip_preserves_utc_zeros_and_nulls(tmp_path, result):
    data, _ = result.export(tmp_path / "study.csv")
    loaded = ComparisonResult.load(data)

    assert str(loaded.table["valid_time"].dt.tz) == "UTC"
    assert loaded.table["usgs_streamflow_m3s"].iloc[1] == 0.0

    np.testing.assert_allclose(
        loaded.table["analysis_assim_streamflow_m3s"].to_numpy(),
        result.table["analysis_assim_streamflow_m3s"].to_numpy(),
        equal_nan=True,
    )


def test_rejects_wrong_schema(tmp_path, result):
    data, manifest = result.export(tmp_path / "study.csv")

    payload = json.loads(manifest.read_text())
    payload["schema"] = "unknown.schema"
    manifest.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="schema"):
        ComparisonResult.load(data)


def test_rejects_wrong_data_filename(tmp_path, result):
    data, manifest = result.export(tmp_path / "study.csv")

    payload = json.loads(manifest.read_text())
    payload["data_file"] = "another.csv"
    manifest.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="filename"):
        ComparisonResult.load(data)


def test_rejects_inconsistent_warnings(tmp_path, result):
    data, manifest = result.export(tmp_path / "study.csv")

    payload = json.loads(manifest.read_text())
    payload["warnings"] = []
    manifest.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="warnings"):
        ComparisonResult.load(data)


def test_missing_manifest_is_not_silently_accepted(tmp_path, result):
    data, manifest = result.export(tmp_path / "study.csv")
    manifest.unlink()

    with pytest.raises(FileNotFoundError):
        ComparisonResult.load(data)
