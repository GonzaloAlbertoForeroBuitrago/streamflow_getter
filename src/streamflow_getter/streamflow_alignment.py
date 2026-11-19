"""Temporal alignment utilities for streamflow comparisons.

Source values retain their native scientific meaning. Alignment is based
only on exact UTC valid times; this module does not interpolate, resample,
or silently change temporal aggregation.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

_SOURCE_COLUMNS = [
    "valid_time",
    "streamflow_m3s",
    "unit",
    "time_support",
    "aggregation",
    "interval_start",
    "interval_end",
]

_ALLOWED_JOIN_MODES = {"inner", "outer"}
_PARTIAL_INTERVAL = object()


def _normalized_label(label: str) -> str:
    """Return a validated comparison-source label."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Source labels must be nonempty strings")

    return label.strip()


def _optional_utc_series(
    series: pd.Series,
    *,
    label: str,
    column: str,
) -> pd.Series:
    """Parse optional UTC datetimes without hiding malformed values."""
    originally_missing = series.isna()

    parsed = pd.to_datetime(
        series,
        utc=True,
        errors="coerce",
    )

    invalid = parsed.isna() & ~originally_missing

    if invalid.any():
        raise ValueError(f"{label} contains invalid {column} values")

    return parsed


def _validated_source_frame(
    label: str,
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Return a validated, normalized copy of one source."""
    label = _normalized_label(label)

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")

    missing_columns = set(_SOURCE_COLUMNS).difference(frame.columns)

    if missing_columns:
        raise ValueError(
            f"{label} is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    result = frame[_SOURCE_COLUMNS].copy()

    result["valid_time"] = pd.to_datetime(
        result["valid_time"],
        utc=True,
        errors="coerce",
    )

    if result["valid_time"].isna().any():
        raise ValueError(f"{label} contains invalid or missing valid_time values")

    if result["valid_time"].duplicated().any():
        raise ValueError(f"{label} contains duplicate valid_time values")

    for column in (
        "interval_start",
        "interval_end",
    ):
        result[column] = _optional_utc_series(
            result[column],
            label=label,
            column=column,
        )

    values = pd.to_numeric(
        result["streamflow_m3s"],
        errors="coerce",
    )

    if not np.isfinite(
        values.to_numpy(
            dtype=float,
        )
    ).all():
        raise ValueError(f"{label} contains non-finite streamflow values")

    result["streamflow_m3s"] = values

    if not result["unit"].eq("m3/s").all():
        raise ValueError(f"{label} must use normalized m3/s units")

    for column in (
        "time_support",
        "aggregation",
    ):
        if result[column].isna().any():
            raise ValueError(f"{label} contains missing {column} values")

    return result.sort_values("valid_time").reset_index(drop=True)


def _single_metadata_value(
    frame: pd.DataFrame,
    column: str,
    *,
    label: str,
) -> str:
    """Return one required source-level metadata value."""
    values = frame[column].astype(str).unique().tolist()

    if len(values) != 1:
        raise ValueError(f"{label} contains mixed {column} values")

    return values[0]


def summarize_temporal_support(
    frame: pd.DataFrame,
    *,
    label: str,
) -> dict:
    """Summarize source timing semantics without altering values."""
    label = _normalized_label(label)

    source = _validated_source_frame(
        label,
        frame,
    )

    return {
        "label": label,
        "rows": len(source),
        "time_support": _single_metadata_value(
            source,
            "time_support",
            label=label,
        ),
        "aggregation": _single_metadata_value(
            source,
            "aggregation",
            label=label,
        ),
        "interval_metadata_available": bool(
            source["interval_start"].notna().all()
            and source["interval_end"].notna().all()
        ),
        "first_valid_time": source["valid_time"].min(),
        "last_valid_time": source["valid_time"].max(),
    }


def _namespaced_frame(
    label: str,
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Namespace source columns while retaining shared valid_time."""
    label = _normalized_label(label)

    source = _validated_source_frame(
        label,
        frame,
    )

    rename = {
        column: f"{label}_{column}"
        for column in _SOURCE_COLUMNS
        if column != "valid_time"
    }

    return source.rename(columns=rename)


def _interval_signature(
    row: pd.Series,
    label: str,
):
    """Return complete interval identity or its missing/partial state."""
    start = row[f"{label}_interval_start"]
    end = row[f"{label}_interval_end"]

    if pd.isna(start) and pd.isna(end):
        return None

    if pd.notna(start) and pd.notna(end):
        return (
            start,
            end,
        )

    return _PARTIAL_INTERVAL


def _row_support_compatible(
    row: pd.Series,
    labels: list[str],
) -> bool:
    """Return whether all sources describe the same temporal statistic."""
    if not all(pd.notna(row[f"{label}_streamflow_m3s"]) for label in labels):
        return False

    if len({row[f"{label}_time_support"] for label in labels}) != 1:
        return False

    if len({row[f"{label}_aggregation"] for label in labels}) != 1:
        return False

    intervals = [
        _interval_signature(
            row,
            label,
        )
        for label in labels
    ]

    if _PARTIAL_INTERVAL in intervals:
        return False

    if all(interval is None for interval in intervals):
        return True

    if any(interval is None for interval in intervals):
        return False

    return len(set(intervals)) == 1


def _vectorized_support_compatible(
    comparison: pd.DataFrame,
    labels: list[str],
) -> pd.Series:
    """Check temporal compatibility across entire columns."""

    def columns_for(suffix: str) -> pd.DataFrame:
        return comparison[[f"{label}_{suffix}" for label in labels]]

    def same_values(columns: pd.DataFrame) -> pd.Series:
        return columns.eq(columns.iloc[:, 0], axis=0).fillna(False).all(
            axis=1
        ) | columns.isna().all(axis=1)

    present = columns_for("streamflow_m3s").notna().all(axis=1)

    same_support = same_values(columns_for("time_support"))
    same_aggregation = same_values(columns_for("aggregation"))

    starts = columns_for("interval_start")
    ends = columns_for("interval_end")

    all_absent = starts.isna().all(axis=1) & ends.isna().all(axis=1)

    all_complete = starts.notna().all(axis=1) & ends.notna().all(axis=1)

    matching_intervals = all_absent | (
        all_complete & same_values(starts) & same_values(ends)
    )

    return (present & same_support & same_aggregation & matching_intervals).astype(bool)


def _comparison_labels(
    series: Mapping[
        str,
        pd.DataFrame,
    ],
) -> list[str]:
    """Validate labels and prevent namespace collisions."""
    labels = [_normalized_label(label) for label in series]

    if len(labels) != len(set(labels)):
        raise ValueError("Source labels must remain unique after trimming whitespace")

    return labels


def build_exact_time_comparison(
    series: Mapping[
        str,
        pd.DataFrame,
    ],
    *,
    how: str = "inner",
) -> pd.DataFrame:
    """Align sources using identical UTC valid_time values only.

    Matching timestamps do not imply matching temporal support. The
    temporal_support_compatible field records that distinction explicitly.
    """
    if not isinstance(series, Mapping) or not series:
        raise ValueError("series must contain at least one source")

    if how not in _ALLOWED_JOIN_MODES:
        raise ValueError("how must be 'inner' or 'outer'")

    labels = _comparison_labels(series)

    frames = [
        _namespaced_frame(
            normalized_label,
            series[original_label],
        )
        for original_label, normalized_label in zip(
            series.keys(),
            labels,
            strict=True,
        )
    ]

    comparison = frames[0]

    for frame in frames[1:]:
        comparison = comparison.merge(
            frame,
            on="valid_time",
            how=how,
            validate="one_to_one",
            sort=True,
        )

    value_columns = [f"{label}_streamflow_m3s" for label in labels]

    comparison["all_sources_present"] = comparison[value_columns].notna().all(axis=1)

    comparison["temporal_support_compatible"] = _vectorized_support_compatible(
        comparison,
        labels,
    )

    comparison["temporal_comparison_note"] = np.where(
        comparison["temporal_support_compatible"],
        ("Sources share the same UTC timestamp and compatible temporal support."),
        (
            "Sources may share a UTC timestamp but "
            "do not necessarily represent the same "
            "temporal statistic."
        ),
    )

    return comparison.sort_values("valid_time").reset_index(drop=True)
