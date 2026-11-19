"""GEOGLOWS retrospective streamflow retrieval.

Experimental integration. This adapter reads the RFS V2 hourly
retrospective directly from the public Zarr store. River matching remains
separate so retrieval is independent from spatial and hydrologic QA.
"""

from __future__ import annotations

from functools import lru_cache
from threading import Lock
import numbers

import numpy as np
import pandas as pd
import xarray as xr


GEOGLOWS_V2_HOURLY_ZARR = (
    "s3://geoglows-v2/"
    "retrospective/hourly.zarr"
)

GEOGLOWS_RETROSPECTIVE_COLUMNS = [
    "source",
    "series",
    "source_id",
    "geoglows_river_id",
    "valid_time",
    "interval_start",
    "interval_end",
    "time_support",
    "aggregation",
    "streamflow_m3s",
    "unit",
    "method",
    "model_version",
    "dataset",
]

_ACCEPTED_DISCHARGE_UNITS = {
    "m3 s-1",
    "m3/s",
    "m^3/s",
    "m³/s",
}


def _river_id(value: int) -> int:
    """Return a validated positive GEOGLOWS river identifier."""
    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Integral)
        or int(value) <= 0
    ):
        raise ValueError(
            "GEOGLOWS river ID must be a positive integer"
        )

    return int(value)


def _utc_hour(
    value,
    *,
    name: str,
) -> pd.Timestamp:
    """Return an explicit whole-hour UTC timestamp."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{name} must be a valid datetime"
        ) from exc

    if timestamp.tzinfo is None:
        raise ValueError(
            f"{name} must include an explicit timezone"
        )

    timestamp = timestamp.tz_convert(
        "UTC"
    )

    if timestamp != timestamp.floor("h"):
        raise ValueError(
            f"{name} must fall on a whole UTC hour"
        )

    return timestamp


_DATASET_OPEN_LOCK = Lock()


@lru_cache(maxsize=2)
def _cached_open_geoglows_retrospective_dataset(
    dataset_uri: str = GEOGLOWS_V2_HOURLY_ZARR,
) -> xr.Dataset:
    """Open and cache a remote GEOGLOWS hourly retrospective dataset."""
    if (
        not isinstance(dataset_uri, str)
        or not dataset_uri.strip()
    ):
        raise ValueError(
            "dataset_uri must be a nonempty string"
        )

    dataset = xr.open_dataset(
        dataset_uri,
        engine="zarr",
        storage_options={
            "anon": True,
        },
    )

    try:
        if "Q" not in dataset:
            raise ValueError(
                "GEOGLOWS dataset does not contain Q"
            )

        discharge = dataset["Q"]

        if not {
            "time",
            "river_id",
        }.issubset(discharge.dims):
            raise ValueError(
                "GEOGLOWS Q must use time and river_id dimensions"
            )

        units = str(
            discharge.attrs.get(
                "units",
                "",
            )
        ).strip()

        if units not in _ACCEPTED_DISCHARGE_UNITS:
            raise ValueError(
                "Unexpected GEOGLOWS discharge units: "
                f"{units!r}"
            )

        aggregation = str(
            discharge.attrs.get(
                "aggregation_method",
                "",
            )
        ).strip().casefold()

        if aggregation != "mean":
            raise ValueError(
                "Unexpected GEOGLOWS aggregation method: "
                f"{aggregation!r}"
            )

    except Exception as validation_error:
        try:
            dataset.close()
        except Exception as cleanup_error:
            validation_error.add_note(
                "GEOGLOWS dataset cleanup failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        raise

    return dataset



def open_geoglows_retrospective_dataset(
    dataset_uri: str = GEOGLOWS_V2_HOURLY_ZARR,
) -> xr.Dataset:
    """Reuse one validated dataset per cached URI under concurrency."""
    with _DATASET_OPEN_LOCK:
        return _cached_open_geoglows_retrospective_dataset(
            dataset_uri
        )


def _clear_cached_geoglows_datasets() -> None:
    """Invalidate cached handles without closing active datasets."""
    with _DATASET_OPEN_LOCK:
        _cached_open_geoglows_retrospective_dataset.cache_clear()


# Preserve existing cache inspection and invalidation interfaces.
open_geoglows_retrospective_dataset.cache_info = (
    _cached_open_geoglows_retrospective_dataset.cache_info
)
open_geoglows_retrospective_dataset.cache_clear = (
    _clear_cached_geoglows_datasets
)


def clear_geoglows_dataset_cache() -> None:
    """Clear cached remote dataset handles, mainly for tests/restarts."""
    open_geoglows_retrospective_dataset.cache_clear()


def fetch_geoglows_retrospective(
    river_id: int,
    start_time,
    end_time,
    *,
    dataset_uri: str = GEOGLOWS_V2_HOURLY_ZARR,
) -> pd.DataFrame:
    """Retrieve RFS V2 hourly-mean discharge in UTC over [start, end).

    Each GEOGLOWS timestamp is treated as the beginning of the represented
    one-hour mean interval. The adapter preserves the source values and
    does not perform temporal interpolation or cross-source alignment.
    """
    river = _river_id(
        river_id
    )

    start = _utc_hour(
        start_time,
        name="start_time",
    )
    end = _utc_hour(
        end_time,
        name="end_time",
    )

    if end <= start:
        raise ValueError(
            "end_time must be after start_time"
        )

    dataset = (
        open_geoglows_retrospective_dataset(
            dataset_uri
        )
    )

    discharge = dataset["Q"]

    # xarray's public GEOGLOWS time coordinate is timezone-naive but
    # semantically UTC. Use a half-open selection to avoid reading the
    # value at end_time.
    start_naive = start.tz_localize(
        None
    )
    end_naive = (
        end.tz_localize(None)
        - pd.Timedelta(
            nanoseconds=1
        )
    )

    try:
        selected = discharge.sel(
            river_id=river,
            time=slice(
                start_naive,
                end_naive,
            ),
        ).load()
    except KeyError as exc:
        raise ValueError(
            "GEOGLOWS river ID not found: "
            f"{river}"
        ) from exc

    frame = (
        selected
        .to_dataframe(
            name="streamflow_m3s"
        )
        .reset_index()
    )

    if frame.empty:
        raise ValueError(
            "No GEOGLOWS hourly retrospective data "
            "inside the requested window"
        )

    frame["valid_time"] = pd.to_datetime(
        frame["time"],
        utc=True,
        errors="raise",
    )

    inside_window = (
        frame["valid_time"]
        .ge(start)
        & frame["valid_time"]
        .lt(end)
    )

    frame = (
        frame.loc[
            inside_window
        ]
        .reset_index(drop=True)
    )

    if frame.empty:
        raise ValueError(
            "No GEOGLOWS hourly retrospective data "
            "inside the requested window"
        )

    if frame["valid_time"].duplicated().any():
        raise ValueError(
            "Duplicate GEOGLOWS retrospective timestamps"
        )

    if not (
        frame["streamflow_m3s"]
        .pipe(np.isfinite)
        .all()
    ):
        raise ValueError(
            "GEOGLOWS streamflow contains "
            "non-finite values"
        )

    frame["source"] = "geoglows"
    frame["series"] = "retrospective_hourly"
    frame["source_id"] = river
    frame["geoglows_river_id"] = river

    frame["interval_start"] = (
        frame["valid_time"]
    )
    frame["interval_end"] = (
        frame["valid_time"]
        + pd.Timedelta(hours=1)
    )

    frame["time_support"] = "hourly_mean"
    frame["aggregation"] = "mean"
    frame["unit"] = "m3/s"
    frame["method"] = "geoglows_zarr"
    frame["model_version"] = "rfs-v2"
    frame["dataset"] = (
        "retrospective_hourly"
    )

    return (
        frame[
            GEOGLOWS_RETROSPECTIVE_COLUMNS
        ]
        .sort_values(
            "valid_time"
        )
        .reset_index(drop=True)
    )
