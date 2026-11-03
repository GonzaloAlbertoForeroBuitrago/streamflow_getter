
"""Offline tests for operational NWM native NetCDF retrieval."""

from unittest.mock import MagicMock

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    read_native_forecast,
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
            "feature_id": [1122645, 3586192, 7144704],
            "time": [np.datetime64("2026-04-19T01:00:00")],
            "reference_time": [
                np.datetime64("2026-04-19T00:00:00")
            ],
        },
    )


@pytest.fixture
def mock_native(monkeypatch, sample_dataset):
    import fsspec

    remote_context = MagicMock()
    remote_context.__enter__.return_value = MagicMock()

    monkeypatch.setattr(
        fsspec,
        "open",
        lambda *args, **kwargs: remote_context,
    )

    dataset_context = MagicMock()
    dataset_context.__enter__.return_value = sample_dataset

    monkeypatch.setattr(
        xr,
        "open_dataset",
        lambda *args, **kwargs: dataset_context,
    )

    return {
        "remote_context": remote_context,
        "dataset_context": dataset_context,
    }


def test_native_success(mock_native):
    result = read_native_forecast(
        ForecastConfig(),
        1,
        [3586192, 1122645],
    )

    assert result["method"] == "native_remote"
    assert result["streamflow_m3s"] == {
        3586192: 0.41,
        1122645: 7.08,
    }

    assert result["valid_time"].startswith("2026-04-19T01:00:00")
    assert result["reference_time"].startswith("2026-04-19T00:00:00")

    mock_native["dataset_context"].__exit__.assert_called_once()
    mock_native["remote_context"].__exit__.assert_called_once()


def test_native_missing_reach(mock_native):
    with pytest.raises(ValueError, match="Missing reaches"):
        read_native_forecast(
            ForecastConfig(),
            1,
            [999999],
        )

    mock_native["dataset_context"].__exit__.assert_called_once()
    mock_native["remote_context"].__exit__.assert_called_once()


def test_native_wrong_timestamp(mock_native, sample_dataset):
    sample_dataset.coords["time"] = [
        np.datetime64("2026-04-19T02:00:00")
    ]

    with pytest.raises(ValueError, match="valid time"):
        read_native_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_native["dataset_context"].__exit__.assert_called_once()
    mock_native["remote_context"].__exit__.assert_called_once()


def test_native_nonfinite_streamflow(mock_native, sample_dataset):
    sample_dataset["streamflow"].values[1] = np.nan

    with pytest.raises(ValueError, match="Non-finite"):
        read_native_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_native["dataset_context"].__exit__.assert_called_once()
    mock_native["remote_context"].__exit__.assert_called_once()


def test_native_invalid_hour(monkeypatch):
    import fsspec

    remote_open = MagicMock()

    monkeypatch.setattr(
        fsspec,
        "open",
        remote_open,
    )

    with pytest.raises(ValueError, match="positive"):
        read_native_forecast(
            ForecastConfig(),
            0,
            [3586192],
        )

    remote_open.assert_not_called()
