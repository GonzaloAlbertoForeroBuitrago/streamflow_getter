"""Tests for operational NWM forecast configuration and extraction."""

import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.operational_nwm import ForecastConfig, extract_streamflow


def test_forecast_source_identity():
    config = ForecastConfig()
    assert config.date_folder == "nwm.20260419"
    assert config.cycle_name == "t00z"
    assert config.filename(1) == "nwm.t00z.short_range.channel_rt.f001.conus.nc"
    assert config.native_url(1).endswith(
        "/nwm.20260419/short_range/nwm.t00z.short_range.channel_rt.f001.conus.nc"
    )
    assert config.reference_path(1).endswith(
        "/nwm.20260419/short_range/nwm.t00z.short_range.channel_rt.f001.conus.nc.json"
    )


def test_forecast_timestamps():
    ForecastConfig(date="2026-04-20", cycle=12).validate_timestamps(
        1, "2026-04-20T13:00:00", "2026-04-20T12:00:00"
    )


def test_wrong_forecast_reference_time():
    with pytest.raises(ValueError, match="reference time"):
        ForecastConfig(date="2026-04-20", cycle=12).validate_timestamps(
            1, "2026-04-19T01:00:00", "2026-04-19T00:00:00"
        )


def test_wrong_forecast_valid_time():
    with pytest.raises(ValueError, match="valid time"):
        ForecastConfig(date="2026-04-20", cycle=12).validate_timestamps(
            1, "2026-04-20T14:00:00", "2026-04-20T12:00:00"
        )


@pytest.mark.parametrize("kwargs", [
    {"date": "2026-02-30"}, {"cycle": -1}, {"cycle": 24},
    {"cycle": True}, {"product": "medium_range"}, {"domain": "alaska"},
])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        ForecastConfig(**kwargs)


@pytest.mark.parametrize("hour", [-1, 0, 1.5, True])
def test_invalid_forecast_hour(hour):
    with pytest.raises(ValueError):
        ForecastConfig().filename(hour)


@pytest.mark.parametrize("forecast_date, cycle, hour", [
    ("2026-04-19", 0, 1), ("2026-04-19", 0, 6),
    ("2026-04-19", 12, 18), ("2026-04-20", 6, 3),
])
def test_forecast_config_matches_benchmark(forecast_date, cycle, hour):
    benchmark_dir = Path(__file__).resolve().parents[1] / "benchmarks"
    if str(benchmark_dir) not in sys.path:
        sys.path.insert(0, str(benchmark_dir))
    from repeated_benchmark import ForecastConfig as BenchmarkConfig
    original = BenchmarkConfig(date=forecast_date, cycle=cycle)
    production = ForecastConfig(date=forecast_date, cycle=cycle)
    assert production.filename(hour) == original.filename(hour)
    assert production.native_url(hour) == original.native_url(hour)
    assert production.reference_path(hour) == original.reference_path(hour)


@pytest.fixture
def operational_dataset():
    return xr.Dataset(
        {"streamflow": ("feature_id", [7.08, 0.41, 0.0])},
        coords={"feature_id": [1122645, 3586192, 7144704]},
    )


def test_extract_streamflow_multiple_reaches(operational_dataset):
    result = extract_streamflow(operational_dataset, [3586192, 1122645])
    assert list(result) == [3586192, 1122645]
    assert result == {3586192: 0.41, 1122645: 7.08}


def test_extract_streamflow_missing_reach(operational_dataset):
    with pytest.raises(ValueError, match="Missing reaches"):
        extract_streamflow(operational_dataset, [999999])


def test_extract_streamflow_duplicate_request(operational_dataset):
    with pytest.raises(ValueError, match="Duplicate"):
        extract_streamflow(operational_dataset, [3586192, 3586192])


def test_extract_streamflow_nonfinite(operational_dataset):
    operational_dataset["streamflow"].values[1] = np.nan
    with pytest.raises(ValueError, match="Non-finite"):
        extract_streamflow(operational_dataset, [3586192])


def test_extract_streamflow_duplicate_dataset_id(operational_dataset):
    invalid = operational_dataset.assign_coords(feature_id=[3586192, 3586192, 7144704])
    with pytest.raises(ValueError, match="Duplicate feature ID"):
        extract_streamflow(invalid, [3586192])


def test_extract_streamflow_invalid_request(operational_dataset):
    with pytest.raises(ValueError, match="positive integers"):
        extract_streamflow(operational_dataset, [3586192.5])


def test_extract_streamflow_invalid_shape():
    ds = xr.Dataset(
        {"streamflow": (("time", "feature_id"), [[7.08, 0.41, 0.0]])},
        coords={"time": [0], "feature_id": [1122645, 3586192, 7144704]},
    )
    with pytest.raises(ValueError, match="shape"):
        extract_streamflow(ds, [3586192])



def test_extraction_matches_existing_benchmark():
    """Preserve James's validated batch extraction behavior."""
    import sys
    from pathlib import Path

    import numpy as np
    import xarray as xr

    from streamflow_getter.operational_nwm import extract_streamflow

    benchmark_dir = (
        Path(__file__).resolve().parents[1] / "benchmarks"
    )

    sys.path.insert(0, str(benchmark_dir))

    from repeated_benchmark import extract_batch

    ds = xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [7.08, 0.41, 0.0, 16062.71, 0.01],
            ),
        },
        coords={
            "feature_id": [
                1122645,
                3586192,
                7144704,
                14191043,
                23610484,
            ],
        },
    )

    requested = [14191043, 1122645, 3586192]
    indices = [3, 0, 1]

    original = extract_batch(ds, indices, requested)
    production = extract_streamflow(ds, requested)

    actual = np.array(list(production.values()))

    np.testing.assert_allclose(
        actual,
        original,
        rtol=0,
        atol=0,
    )

    assert list(production) == requested
