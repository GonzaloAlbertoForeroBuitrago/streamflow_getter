"""Checksum and backward-compatibility tests for comparison exports."""

import json
from hashlib import sha256

import pandas as pd
import pytest

from streamflow_getter import ComparisonResult
from streamflow_getter.output import manifest_path_for


@pytest.fixture
def result():
    table = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(
                ["2025-07-04T06:00:00Z", "2025-07-04T07:00:00Z"],
                utc=True,
            ),
            "usgs_streamflow_m3s": [1.25, 0.0],
            "analysis_assim_streamflow_m3s": [1.20, None],
        }
    )

    return ComparisonResult(
        {
            "table": table,
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


def test_v2_manifest_contains_actual_file_integrity(tmp_path, result):
    data, manifest = result.export(tmp_path / "study.csv")
    payload = json.loads(manifest.read_text())
    integrity = payload["data_integrity"]

    assert payload["schema"] == "streamflow_getter.comparison_export.v2"
    assert integrity["algorithm"] == "sha256"
    assert integrity["size_bytes"] == data.stat().st_size
    assert integrity["sha256"] == sha256(data.read_bytes()).hexdigest()


def test_v2_parquet_roundtrip_preserves_science(tmp_path, result):
    pytest.importorskip("pyarrow")

    data, _ = result.export(tmp_path / "study.parquet")
    recovered = ComparisonResult.load(data)

    pd.testing.assert_frame_equal(recovered.table, result.table)
    assert recovered.ids == result.ids
    assert recovered.geometries == result.geometries


def test_v2_detects_same_size_corruption(tmp_path, result):
    data, _ = result.export(tmp_path / "study.csv")
    content = data.read_bytes()

    data.write_bytes(bytes([content[0] ^ 1]) + content[1:])

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ComparisonResult.load(data)


def test_v2_rejects_missing_integrity(tmp_path, result):
    data, manifest = result.export(tmp_path / "study.csv")
    payload = json.loads(manifest.read_text())

    payload.pop("data_integrity")
    manifest.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="integrity"):
        ComparisonResult.load(data)


def test_legacy_v1_stays_readable(tmp_path, result):
    data, manifest = result.export(tmp_path / "study.csv")
    payload = json.loads(manifest.read_text())

    payload["schema"] = "streamflow_getter.comparison_export.v1"
    payload.pop("data_integrity")
    manifest.write_text(json.dumps(payload))

    recovered = ComparisonResult.load(data)

    pd.testing.assert_frame_equal(recovered.table, result.table)
    assert recovered.ids == result.ids


def test_hash_failure_rolls_back_data(tmp_path, result, monkeypatch):
    import streamflow_getter.integrity as integrity

    def fail_checksum(path):
        raise OSError("Simulated checksum failure")

    monkeypatch.setattr(integrity, "file_integrity", fail_checksum)

    destination = tmp_path / "study.csv"

    with pytest.raises(OSError, match="Simulated"):
        result.export(destination)

    assert not destination.exists()
    assert not manifest_path_for(destination).exists()
