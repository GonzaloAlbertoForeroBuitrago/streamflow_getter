import pandas as pd
import pytest

from streamflow_getter.streamflow_alignment import (
    build_exact_time_comparison,
    summarize_temporal_support,
)


def source_frame(
    *,
    times,
    values,
    time_support,
    aggregation,
    intervals=False,
):
    valid_time = pd.to_datetime(
        times,
        utc=True,
    )

    if intervals:
        interval_start = valid_time
        interval_end = valid_time + pd.Timedelta(hours=1)
    else:
        interval_start = pd.Series(
            pd.NaT,
            index=range(len(valid_time)),
            dtype="datetime64[ns, UTC]",
        )
        interval_end = pd.Series(
            pd.NaT,
            index=range(len(valid_time)),
            dtype="datetime64[ns, UTC]",
        )

    return pd.DataFrame(
        {
            "valid_time": valid_time,
            "streamflow_m3s": values,
            "unit": "m3/s",
            "time_support": (time_support),
            "aggregation": aggregation,
            "interval_start": (interval_start),
            "interval_end": (interval_end),
        }
    )


def test_temporal_support_summary():
    frame = source_frame(
        times=[
            "2025-07-04T07:00:00Z",
            "2025-07-04T08:00:00Z",
        ],
        values=[
            1.85,
            1.77,
        ],
        time_support="hourly_mean",
        aggregation="mean",
        intervals=True,
    )

    summary = summarize_temporal_support(
        frame,
        label="geoglows",
    )

    assert summary == {
        "label": "geoglows",
        "rows": 2,
        "time_support": "hourly_mean",
        "aggregation": "mean",
        "interval_metadata_available": True,
        "first_valid_time": pd.Timestamp("2025-07-04T07:00:00Z"),
        "last_valid_time": pd.Timestamp("2025-07-04T08:00:00Z"),
    }


def test_exact_time_alignment_preserves_values():
    nwm = source_frame(
        times=[
            "2025-07-04T09:00:00Z",
            "2025-07-04T10:00:00Z",
        ],
        values=[
            1271.43,
            2890.46,
        ],
        time_support="model_valid_time",
        aggregation="native",
    )

    usgs = source_frame(
        times=[
            "2025-07-04T09:00:00Z",
            "2025-07-04T09:05:00Z",
        ],
        values=[
            1274.26,
            1444.16,
        ],
        time_support="instantaneous",
        aggregation="native",
    )

    geoglows = source_frame(
        times=[
            "2025-07-04T09:00:00Z",
            "2025-07-04T10:00:00Z",
        ],
        values=[
            1.83,
            3.76,
        ],
        time_support="hourly_mean",
        aggregation="mean",
        intervals=True,
    )

    result = build_exact_time_comparison(
        {
            "nwm": nwm,
            "usgs": usgs,
            "geoglows": geoglows,
        },
        how="inner",
    )

    assert len(result) == 1

    row = result.iloc[0]

    assert row["valid_time"] == pd.Timestamp("2025-07-04T09:00:00Z")

    assert row["nwm_streamflow_m3s"] == pytest.approx(1271.43)

    assert row["usgs_streamflow_m3s"] == pytest.approx(1274.26)

    assert row["geoglows_streamflow_m3s"] == pytest.approx(1.83)

    assert row["all_sources_present"] is True or row["all_sources_present"] == True

    assert (
        row["temporal_support_compatible"] is False
        or row["temporal_support_compatible"] == False
    )


def test_compatible_hourly_sources_are_flagged():
    left = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[10.0],
        time_support="hourly_mean",
        aggregation="mean",
        intervals=True,
    )

    right = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[11.0],
        time_support="hourly_mean",
        aggregation="mean",
        intervals=True,
    )

    result = build_exact_time_comparison(
        {
            "left": left,
            "right": right,
        }
    )

    assert bool(
        result.loc[
            0,
            "temporal_support_compatible",
        ]
    )


def test_outer_alignment_preserves_missing_sources():
    nwm = source_frame(
        times=[
            "2025-07-04T09:00:00Z",
            "2025-07-04T10:00:00Z",
        ],
        values=[
            1,
            2,
        ],
        time_support="model_valid_time",
        aggregation="native",
    )

    usgs = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[
            3,
        ],
        time_support="instantaneous",
        aggregation="native",
    )

    result = build_exact_time_comparison(
        {
            "nwm": nwm,
            "usgs": usgs,
        },
        how="outer",
    )

    assert len(result) == 2

    at_ten = result.loc[
        result["valid_time"] == pd.Timestamp("2025-07-04T10:00:00Z")
    ].iloc[0]

    assert pd.isna(at_ten["usgs_streamflow_m3s"])

    assert not bool(at_ten["all_sources_present"])


def test_alignment_does_not_mutate_inputs():
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[1.0],
        time_support="instantaneous",
        aggregation="native",
    )

    original = frame.copy(deep=True)

    build_exact_time_comparison(
        {
            "a": frame,
        }
    )

    pd.testing.assert_frame_equal(
        frame,
        original,
    )


def test_duplicate_valid_time_is_rejected():
    frame = source_frame(
        times=[
            "2025-07-04T09:00:00Z",
            "2025-07-04T09:00:00Z",
        ],
        values=[
            1,
            2,
        ],
        time_support="instantaneous",
        aggregation="native",
    )

    with pytest.raises(
        ValueError,
        match="duplicate valid_time",
    ):
        build_exact_time_comparison(
            {
                "usgs": frame,
            }
        )


def test_non_m3s_unit_is_rejected():
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[
            1,
        ],
        time_support="instantaneous",
        aggregation="native",
    )

    frame["unit"] = "ft3/s"

    with pytest.raises(
        ValueError,
        match="normalized m3/s",
    ):
        build_exact_time_comparison(
            {
                "usgs": frame,
            }
        )


def test_mixed_support_summary_is_rejected():
    frame = source_frame(
        times=[
            "2025-07-04T09:00:00Z",
            "2025-07-04T10:00:00Z",
        ],
        values=[
            1,
            2,
        ],
        time_support="instantaneous",
        aggregation="native",
    )

    frame.loc[1, "time_support"] = "hourly_mean"

    with pytest.raises(
        ValueError,
        match="mixed time_support",
    ):
        summarize_temporal_support(
            frame,
            label="mixed",
        )


@pytest.mark.parametrize(
    "how",
    [
        "left",
        "right",
        "invalid",
    ],
)
def test_invalid_join_mode(
    how,
):
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[
            1,
        ],
        time_support="instantaneous",
        aggregation="native",
    )

    with pytest.raises(
        ValueError,
        match="inner.*outer",
    ):
        build_exact_time_comparison(
            {
                "usgs": frame,
            },
            how=how,
        )


def test_empty_series_mapping_is_rejected():
    with pytest.raises(
        ValueError,
        match="at least one source",
    ):
        build_exact_time_comparison({})


def test_summary_returns_python_bool():
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[1.0],
        time_support="model_valid_time",
        aggregation="native",
    )

    summary = summarize_temporal_support(
        frame,
        label="nwm",
    )

    assert type(summary["interval_metadata_available"]) is bool


def test_partial_interval_metadata_is_incompatible():
    left = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[1.0],
        time_support="hourly_mean",
        aggregation="mean",
        intervals=True,
    )

    right = left.copy(deep=True)

    right.loc[0, "interval_end"] = pd.NaT

    result = build_exact_time_comparison(
        {
            "left": left,
            "right": right,
        }
    )

    assert not bool(
        result.loc[
            0,
            "temporal_support_compatible",
        ]
    )


def test_invalid_interval_timestamp_is_rejected():
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[1.0],
        time_support="hourly_mean",
        aggregation="mean",
        intervals=True,
    )

    # Cast to object so malformed external input can reach the
    # package validator instead of being rejected by pandas assignment.
    frame["interval_end"] = frame["interval_end"].astype(object)

    frame.loc[0, "interval_end"] = "not-a-time"

    with pytest.raises(
        ValueError,
        match="invalid interval_end",
    ):
        summarize_temporal_support(
            frame,
            label="source",
        )


def test_missing_temporal_metadata_is_rejected():
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[1.0],
        time_support="instantaneous",
        aggregation="native",
    )

    frame.loc[0, "time_support"] = None

    with pytest.raises(
        ValueError,
        match="missing time_support",
    ):
        summarize_temporal_support(
            frame,
            label="source",
        )


def test_nonfinite_streamflow_is_rejected():
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[float("inf")],
        time_support="instantaneous",
        aggregation="native",
    )

    with pytest.raises(
        ValueError,
        match="non-finite",
    ):
        build_exact_time_comparison(
            {
                "source": frame,
            }
        )


def test_trimmed_label_collision_is_rejected():
    frame = source_frame(
        times=["2025-07-04T09:00:00Z"],
        values=[1.0],
        time_support="instantaneous",
        aggregation="native",
    )

    with pytest.raises(
        ValueError,
        match="unique after trimming",
    ):
        build_exact_time_comparison(
            {
                "nwm": frame,
                "nwm ": frame,
            }
        )
