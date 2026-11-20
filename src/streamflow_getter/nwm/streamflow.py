"""High-level operational NWM streamflow access.

Application-facing time-window helpers live here while the validated
operational engine continues to own product definitions, schedules,
source resolution, Kerchunk/native retrieval, cache behavior, and
source/timestamp validation.
"""

from __future__ import annotations

import numbers

import pandas as pd

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    PRODUCT_SPECS,
    fetch_operational_series,
)


ANALYSIS_PRODUCTS = frozenset(
    {
        "analysis_assim",
        "analysis_assim_no_da",
    }
)

NWM_COMMON_COLUMNS = [
    "source",
    "series",
    "source_id",
    "feature_id",
    "valid_time",
    "interval_start",
    "interval_end",
    "time_support",
    "aggregation",
    "streamflow_m3s",
    "unit",
    "method",
    "product",
    "domain",
    "forecast_date",
    "forecast_cycle",
    "lead_hour",
    "reference_time",
]


def _feature_id(value: int) -> int:
    """Return a validated positive NWM feature ID."""
    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Integral)
        or int(value) <= 0
    ):
        raise ValueError("NWM feature ID must be a positive integer")

    return int(value)


def _utc_hour(value, *, name: str) -> pd.Timestamp:
    """Return an explicit whole-hour UTC timestamp."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a valid datetime") from exc

    if timestamp.tzinfo is None:
        raise ValueError(f"{name} must include an explicit timezone")

    timestamp = timestamp.tz_convert("UTC")

    if timestamp != timestamp.floor("h"):
        raise ValueError(f"{name} must fall on a whole UTC hour")

    return timestamp


def _normalize_nwm_frame(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize a validated operational frame for application use."""
    required = {
        "forecast_date",
        "forecast_cycle",
        "product",
        "domain",
        "lead_hour",
        "feature_id",
        "valid_time",
        "reference_time",
        "streamflow_m3s",
        "method",
    }

    missing = required.difference(frame.columns)

    if missing:
        raise ValueError(
            "Operational NWM frame is missing columns: " + ", ".join(sorted(missing))
        )

    result = frame.copy()

    result["valid_time"] = pd.to_datetime(
        result["valid_time"],
        utc=True,
        errors="raise",
    )

    result["reference_time"] = pd.to_datetime(
        result["reference_time"],
        utc=True,
        errors="raise",
    )

    if result["valid_time"].isna().any():
        raise ValueError("NWM valid_time contains missing values")

    if result["reference_time"].isna().any():
        raise ValueError("NWM reference_time contains missing values")

    if result["streamflow_m3s"].isna().any():
        raise ValueError("NWM streamflow contains missing values")

    result["source"] = "nwm"
    result["series"] = result["product"]
    result["source_id"] = result["feature_id"]
    result["unit"] = "m3/s"

    # The product gives a validated model value at valid_time. Its exact
    # temporal support will be established later in the alignment review;
    # do not silently label it instantaneous or hourly mean here.
    result["interval_start"] = pd.NaT
    result["interval_end"] = pd.NaT
    result["time_support"] = "model_valid_time"
    result["aggregation"] = "native"

    return (
        result[NWM_COMMON_COLUMNS]
        .sort_values(
            [
                "valid_time",
                "feature_id",
            ]
        )
        .reset_index(drop=True)
    )


def _latest_forecast_initialization(
    reference_time: pd.Timestamp,
    product: str,
) -> pd.Timestamp:
    """Return the latest supported product cycle at or before reference."""
    if product not in PRODUCT_SPECS:
        raise ValueError(f"Unsupported operational NWM product: {product}")

    spec = PRODUCT_SPECS[product]

    if spec.analysis_only:
        raise ValueError(f"{product} is an analysis product, not a forecast product")

    candidates = [
        day + pd.Timedelta(hours=cycle)
        for day in (
            reference_time.normalize() - pd.Timedelta(days=1),
            reference_time.normalize(),
        )
        for cycle in spec.cycles
    ]

    eligible = [candidate for candidate in candidates if candidate <= reference_time]

    if not eligible:
        raise ValueError(f"No supported initialization found for {product}")

    return max(eligible)


def _forecast_leads_in_window(
    config: ForecastConfig,
    reference_time: pd.Timestamp,
    end_time: pd.Timestamp,
) -> list[int]:
    """Return scheduled leads whose valid times fall in (reference, end]."""
    lead_hours = config.forecast_hours(
        1,
        config.spec.max_hour,
    )

    initialization = pd.Timestamp(f"{config.date}T{config.cycle:02d}:00:00Z")

    selected = [
        lead
        for lead in lead_hours
        if (
            initialization + pd.Timedelta(hours=lead) > reference_time
            and initialization + pd.Timedelta(hours=lead) <= end_time
        )
    ]

    if not selected:
        raise ValueError(
            "No scheduled forecast valid times inside the requested window"
        )

    return selected


def fetch_nwm_analysis_streamflow(
    feature_id: int,
    start_time,
    end_time,
    *,
    product: str = "analysis_assim",
    cache_dir=None,
) -> pd.DataFrame:
    """Retrieve an inclusive hourly NWM analysis window.

    Each requested valid hour uses the corresponding operational analysis
    cycle and tm00 value. This reproduces the current notebook experiment
    while moving all retrieval logic into the package backend.
    """
    reach = _feature_id(feature_id)

    if product not in ANALYSIS_PRODUCTS:
        raise ValueError(
            "Analysis product must be one of: " + ", ".join(sorted(ANALYSIS_PRODUCTS))
        )

    start = _utc_hour(
        start_time,
        name="start_time",
    )
    end = _utc_hour(
        end_time,
        name="end_time",
    )

    if end < start:
        raise ValueError("end_time must not be before start_time")

    frames = []

    for valid_time in pd.date_range(
        start,
        end,
        freq="h",
    ):
        config = ForecastConfig(
            date=valid_time.strftime("%Y-%m-%d"),
            cycle=int(valid_time.hour),
            product=product,
            domain="conus",
        )

        frames.append(
            fetch_operational_series(
                config,
                [reach],
                start_hour=1,
                end_hour=1,
                include_t0=True,
                cache_dir=cache_dir,
            )
        )

    return _normalize_nwm_frame(
        pd.concat(
            frames,
            ignore_index=True,
        )
    )


def fetch_nwm_forecast_streamflow(
    feature_id: int,
    reference_time,
    end_time,
    *,
    product: str = "short_range",
    cache_dir=None,
) -> pd.DataFrame:
    """Retrieve forecast values after a selected reference time.

    The latest product initialization at or before reference_time is used.
    Only scheduled forecast values in (reference_time, end_time] are
    returned. Analysis t0 remains separate from this forecast API.
    """
    reach = _feature_id(feature_id)

    reference = _utc_hour(
        reference_time,
        name="reference_time",
    )
    end = _utc_hour(
        end_time,
        name="end_time",
    )

    if end <= reference:
        raise ValueError("end_time must be after reference_time")

    initialization = _latest_forecast_initialization(
        reference,
        product,
    )

    config = ForecastConfig(
        date=initialization.strftime("%Y-%m-%d"),
        cycle=int(initialization.hour),
        product=product,
        domain="conus",
    )

    leads = _forecast_leads_in_window(
        config,
        reference,
        end,
    )

    frame = fetch_operational_series(
        config,
        [reach],
        start_hour=leads[0],
        end_hour=leads[-1],
        include_t0=False,
        cache_dir=cache_dir,
    )

    normalized = _normalize_nwm_frame(frame)

    inside_window = normalized["valid_time"].gt(reference) & normalized[
        "valid_time"
    ].le(end)

    result = normalized.loc[inside_window].reset_index(drop=True)

    if result.empty:
        raise ValueError(
            "Operational NWM retrieval returned "
            "no forecast rows inside the requested window"
        )

    return result
