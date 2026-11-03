
"""Offline tests for operational NWM Kerchunk retrieval."""

import json
from unittest.mock import MagicMock

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    read_kerchunk_forecast,
)


@pytest.fixture
def sample_dataset():
    return xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [7.08, 0.41, 0.0],
            ),
        },
        coords={
            "feature_id": [
                1122645,
                3586192,
                7144704,
            ],
            "time": [np.datetime64("2026-04-19T01:00:00")],
            "reference_time": [
                np.datetime64("2026-04-19T00:00:00")
            ],
        },
    )


@pytest.fixture
def valid_reference():
    url = ForecastConfig().native_url(1)

    return {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }


@pytest.fixture
def mock_kerchunk(monkeypatch, sample_dataset, valid_reference):
    """Replace network and dataset opening with local mocks."""
    import fsspec
    import s3fs

    reference_bytes = json.dumps(valid_reference).encode("utf-8")

    remote_file = MagicMock()
    remote_file.__enter__.return_value.read.return_value = reference_bytes

    s3 = MagicMock()
    s3.open.return_value = remote_file

    monkeypatch.setattr(
        s3fs,
        "S3FileSystem",
        lambda **kwargs: s3,
    )

    filesystem = MagicMock()
    filesystem.get_mapper.return_value = {}

    monkeypatch.setattr(
        fsspec,
        "filesystem",
        lambda *args, **kwargs: filesystem,
    )

    dataset_context = MagicMock()
    dataset_context.__enter__.return_value = sample_dataset

    monkeypatch.setattr(
        xr,
        "open_zarr",
        lambda *args, **kwargs: dataset_context,
    )

    return {
        "s3": s3,
        "filesystem": filesystem,
        "dataset_context": dataset_context,
    }


def test_kerchunk_success(mock_kerchunk):
    result = read_kerchunk_forecast(
        ForecastConfig(),
        1,
        [3586192, 1122645],
    )

    assert result["method"] == "kerchunk"
    assert result["lead_hour"] == 1
    assert result["streamflow_m3s"] == {
        3586192: 0.41,
        1122645: 7.08,
    }

    assert result["valid_time"].startswith("2026-04-19T01:00:00")
    assert result["reference_time"].startswith("2026-04-19T00:00:00")

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()


def test_kerchunk_missing_reach(mock_kerchunk):
    with pytest.raises(ValueError, match="Missing reaches"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [999999],
        )

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()


def test_kerchunk_invalid_reference(
    mock_kerchunk, monkeypatch
):
    from streamflow_getter import reference_validation

    monkeypatch.setattr(
        reference_validation,
        "validate_reference",
        lambda reference: False,
    )

    with pytest.raises(ValueError, match="Invalid Kerchunk"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["s3"].open.assert_called_once()
    mock_kerchunk["dataset_context"].__enter__.assert_not_called()


def test_kerchunk_wrong_source(
    mock_kerchunk, monkeypatch
):
    from streamflow_getter import reference_validation

    monkeypatch.setattr(
        reference_validation,
        "valid_source_identity",
        lambda reference, expected_url: False,
    )

    with pytest.raises(ValueError, match="source identity"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["dataset_context"].__enter__.assert_not_called()


def test_kerchunk_wrong_timestamp(
    mock_kerchunk, sample_dataset
):
    sample_dataset.coords["time"] = [
        np.datetime64("2026-04-19T02:00:00")
    ]

    with pytest.raises(ValueError, match="valid time"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()


def test_kerchunk_nonfinite_streamflow(
    mock_kerchunk, sample_dataset
):
    sample_dataset["streamflow"].values[1] = np.nan

    with pytest.raises(ValueError, match="Non-finite"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()



def test_kerchunk_analysis_t0(
    mock_kerchunk,
    sample_dataset,
):
    """Retrieve analysis t0 and preserve its original reference time."""
    import json

    config = ForecastConfig()

    sample_dataset.coords["time"] = [
        np.datetime64("2026-04-19T00:00:00")
    ]
    sample_dataset.coords["reference_time"] = [
        np.datetime64("2026-04-18T21:00:00")
    ]

    url = config.analysis_native_url()

    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }

    mock_kerchunk["s3"].open.return_value.__enter__.return_value.read.return_value = (
        json.dumps(reference).encode()
    )

    result = read_kerchunk_forecast(
        config,
        0,
        [3586192],
    )

    assert result["product"] == "analysis_assim"
    assert result["lead_hour"] == 0
    assert result["streamflow_m3s"][3586192] == 0.41
    assert result["valid_time"].startswith("2026-04-19T00:00:00")
    assert result["reference_time"].startswith("2026-04-18T21:00:00")

    mock_kerchunk["s3"].open.assert_called_once_with(
        config.analysis_reference_path(),
        "rb",
    )


def test_kerchunk_analysis_t0_rejects_wrong_valid_time(
    mock_kerchunk,
    sample_dataset,
):
    """Reject an analysis file whose valid time differs from the cycle."""
    import json

    config = ForecastConfig()
    url = config.analysis_native_url()

    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }

    mock_kerchunk["s3"].open.return_value.__enter__.return_value.read.return_value = (
        json.dumps(reference).encode()
    )

    sample_dataset.coords["reference_time"] = [
        np.datetime64("2026-04-18T21:00:00")
    ]

    with pytest.raises(ValueError, match="analysis t0 valid time"):
        read_kerchunk_forecast(
            config,
            0,
            [3586192],
        )
