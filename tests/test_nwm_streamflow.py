import numpy as np
import pandas as pd
import pytest

from streamflow_getter.nwm import streamflow as nwm_streamflow


def operational_frame(
    *,
    date,
    cycle,
    product,
    feature_id=3586192,
    lead_hour=0,
    valid_time=None,
    reference_time=None,
    streamflow=1.25,
):
    if valid_time is None:
        valid_time = pd.Timestamp(
            date,
            tz="UTC",
        ) + pd.Timedelta(hours=cycle)

    if reference_time is None:
        reference_time = valid_time

    return pd.DataFrame(
        [
            {
                "forecast_date": date,
                "forecast_cycle": cycle,
                "product": product,
                "domain": "conus",
                "lead_hour": lead_hour,
                "feature_id": feature_id,
                "valid_time": np.datetime64(pd.Timestamp(valid_time).tz_convert(None)),
                "reference_time": np.datetime64(
                    pd.Timestamp(reference_time).tz_convert(None)
                ),
                "streamflow_m3s": streamflow,
                "method": "kerchunk",
            }
        ]
    )


def test_analysis_window_matches_notebook_pattern(
    monkeypatch,
):
    calls = []

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0,
        cache_dir,
    ):
        calls.append(
            (
                config.date,
                config.cycle,
                config.product,
                reach_ids,
                include_t0,
            )
        )

        valid = pd.Timestamp(
            config.date,
            tz="UTC",
        ) + pd.Timedelta(hours=config.cycle)

        return operational_frame(
            date=config.date,
            cycle=config.cycle,
            product=config.product,
            valid_time=valid,
            reference_time=(valid - pd.Timedelta(hours=3)),
            streamflow=float(config.cycle),
        )

    monkeypatch.setattr(
        nwm_streamflow,
        "fetch_operational_series",
        fake_fetch,
    )

    frame = nwm_streamflow.fetch_nwm_analysis_streamflow(
        3586192,
        "2025-07-04T07:00:00Z",
        "2025-07-04T10:00:00Z",
        product="analysis_assim",
    )

    assert [(date, cycle) for date, cycle, *_ in calls] == [
        ("2025-07-04", 7),
        ("2025-07-04", 8),
        ("2025-07-04", 9),
        ("2025-07-04", 10),
    ]

    assert all(
        product == "analysis_assim" and reaches == [3586192] and include_t0 is True
        for _, _, product, reaches, include_t0 in calls
    )

    assert frame["source"].eq("nwm").all()

    assert frame["unit"].eq("m3/s").all()

    assert frame["time_support"].eq("model_valid_time").all()


def test_analysis_window_crosses_midnight(
    monkeypatch,
):
    configs = []

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0,
        cache_dir,
    ):
        configs.append(
            (
                config.date,
                config.cycle,
            )
        )

        valid = pd.Timestamp(
            config.date,
            tz="UTC",
        ) + pd.Timedelta(hours=config.cycle)

        return operational_frame(
            date=config.date,
            cycle=config.cycle,
            product=config.product,
            valid_time=valid,
        )

    monkeypatch.setattr(
        nwm_streamflow,
        "fetch_operational_series",
        fake_fetch,
    )

    (
        nwm_streamflow.fetch_nwm_analysis_streamflow(
            3586192,
            "2025-07-04T23:00:00Z",
            "2025-07-05T01:00:00Z",
        )
    )

    assert configs == [
        ("2025-07-04", 23),
        ("2025-07-05", 0),
        ("2025-07-05", 1),
    ]


def test_analysis_no_da_is_supported(
    monkeypatch,
):
    observed = []

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0,
        cache_dir,
    ):
        observed.append(config.product)

        return operational_frame(
            date=config.date,
            cycle=config.cycle,
            product=config.product,
        )

    monkeypatch.setattr(
        nwm_streamflow,
        "fetch_operational_series",
        fake_fetch,
    )

    frame = nwm_streamflow.fetch_nwm_analysis_streamflow(
        3586192,
        "2025-07-04T09:00:00Z",
        "2025-07-04T09:00:00Z",
        product="analysis_assim_no_da",
    )

    assert observed == ["analysis_assim_no_da"]

    assert frame["series"].tolist() == ["analysis_assim_no_da"]


def test_analysis_rejects_forecast_product():
    with pytest.raises(
        ValueError,
        match="Analysis product",
    ):
        nwm_streamflow.fetch_nwm_analysis_streamflow(
            3586192,
            "2025-07-04T09:00:00Z",
            "2025-07-04T10:00:00Z",
            product="short_range",
        )


@pytest.mark.parametrize(
    ("reference", "product", "expected"),
    [
        (
            "2025-07-04T10:00:00Z",
            "short_range",
            "2025-07-04T10:00:00Z",
        ),
        (
            "2025-07-04T10:00:00Z",
            "medium_range_blend",
            "2025-07-04T06:00:00Z",
        ),
        (
            "2025-07-04T10:00:00Z",
            "medium_range_no_da",
            "2025-07-04T06:00:00Z",
        ),
        (
            "2025-07-04T23:00:00Z",
            "long_range_mem1",
            "2025-07-04T18:00:00Z",
        ),
    ],
)
def test_latest_forecast_initialization(
    reference,
    product,
    expected,
):
    actual = nwm_streamflow._latest_forecast_initialization(
        pd.Timestamp(reference),
        product,
    )

    assert actual == pd.Timestamp(expected)


def test_short_range_returns_values_after_reference(
    monkeypatch,
):
    observed = {}

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0,
        cache_dir,
    ):
        observed.update(
            {
                "date": config.date,
                "cycle": config.cycle,
                "product": config.product,
                "start": start_hour,
                "end": end_hour,
                "include_t0": include_t0,
            }
        )

        initialization = pd.Timestamp(f"{config.date}T{config.cycle:02d}:00:00Z")

        return pd.concat(
            [
                operational_frame(
                    date=config.date,
                    cycle=config.cycle,
                    product=config.product,
                    lead_hour=hour,
                    valid_time=(initialization + pd.Timedelta(hours=hour)),
                    reference_time=initialization,
                    streamflow=hour / 10,
                )
                for hour in range(
                    start_hour,
                    end_hour + 1,
                )
            ],
            ignore_index=True,
        )

    monkeypatch.setattr(
        nwm_streamflow,
        "fetch_operational_series",
        fake_fetch,
    )

    frame = nwm_streamflow.fetch_nwm_forecast_streamflow(
        3586192,
        "2025-07-04T10:00:00Z",
        "2025-07-04T12:00:00Z",
        product="short_range",
    )

    assert observed == {
        "date": "2025-07-04",
        "cycle": 10,
        "product": "short_range",
        "start": 1,
        "end": 2,
        "include_t0": False,
    }

    assert frame["valid_time"].tolist() == [
        pd.Timestamp("2025-07-04T11:00:00Z"),
        pd.Timestamp("2025-07-04T12:00:00Z"),
    ]


def test_medium_range_uses_prior_cycle_and_window(
    monkeypatch,
):
    observed = {}

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0,
        cache_dir,
    ):
        observed.update(
            {
                "date": config.date,
                "cycle": config.cycle,
                "start": start_hour,
                "end": end_hour,
            }
        )

        initialization = pd.Timestamp(f"{config.date}T{config.cycle:02d}:00:00Z")

        return pd.concat(
            [
                operational_frame(
                    date=config.date,
                    cycle=config.cycle,
                    product=config.product,
                    lead_hour=hour,
                    valid_time=(initialization + pd.Timedelta(hours=hour)),
                    reference_time=initialization,
                )
                for hour in range(
                    start_hour,
                    end_hour + 1,
                )
            ],
            ignore_index=True,
        )

    monkeypatch.setattr(
        nwm_streamflow,
        "fetch_operational_series",
        fake_fetch,
    )

    frame = nwm_streamflow.fetch_nwm_forecast_streamflow(
        3586192,
        "2025-07-04T10:00:00Z",
        "2025-07-04T12:00:00Z",
        product="medium_range_blend",
    )

    assert observed == {
        "date": "2025-07-04",
        "cycle": 6,
        "start": 5,
        "end": 6,
    }

    assert frame["valid_time"].tolist() == [
        pd.Timestamp("2025-07-04T11:00:00Z"),
        pd.Timestamp("2025-07-04T12:00:00Z"),
    ]


def test_no_da_schedule_filters_to_available_leads(
    monkeypatch,
):
    observed = {}

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0,
        cache_dir,
    ):
        observed.update(
            {
                "cycle": config.cycle,
                "start": start_hour,
                "end": end_hour,
            }
        )

        initialization = pd.Timestamp(f"{config.date}T{config.cycle:02d}:00:00Z")

        return pd.concat(
            [
                operational_frame(
                    date=config.date,
                    cycle=config.cycle,
                    product=config.product,
                    lead_hour=hour,
                    valid_time=(initialization + pd.Timedelta(hours=hour)),
                    reference_time=initialization,
                )
                for hour in (6,)
            ],
            ignore_index=True,
        )

    monkeypatch.setattr(
        nwm_streamflow,
        "fetch_operational_series",
        fake_fetch,
    )

    frame = nwm_streamflow.fetch_nwm_forecast_streamflow(
        3586192,
        "2025-07-04T10:00:00Z",
        "2025-07-04T12:00:00Z",
        product="medium_range_no_da",
    )

    assert observed == {
        "cycle": 6,
        "start": 6,
        "end": 6,
    }

    assert frame["valid_time"].tolist() == [pd.Timestamp("2025-07-04T12:00:00Z")]


def test_forecast_rejects_analysis_product():
    with pytest.raises(
        ValueError,
        match="not a forecast product",
    ):
        nwm_streamflow.fetch_nwm_forecast_streamflow(
            3586192,
            "2025-07-04T10:00:00Z",
            "2025-07-04T12:00:00Z",
            product="analysis_assim",
        )


def test_forecast_requires_value_in_window():
    with pytest.raises(
        ValueError,
        match="No scheduled forecast",
    ):
        nwm_streamflow.fetch_nwm_forecast_streamflow(
            3586192,
            "2025-07-04T10:00:00Z",
            "2025-07-04T11:00:00Z",
            product="medium_range_no_da",
        )


@pytest.mark.parametrize(
    "feature_id",
    [
        0,
        -1,
        True,
        3586192.0,
        "3586192",
    ],
)
def test_invalid_feature_id(
    feature_id,
):
    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        nwm_streamflow.fetch_nwm_analysis_streamflow(
            feature_id,
            "2025-07-04T09:00:00Z",
            "2025-07-04T10:00:00Z",
        )


@pytest.mark.parametrize(
    "timestamp",
    [
        "2025-07-04 10:00:00",
        "2025-07-04T10:15:00Z",
    ],
)
def test_rejects_invalid_hour(
    timestamp,
):
    with pytest.raises(ValueError):
        nwm_streamflow.fetch_nwm_analysis_streamflow(
            3586192,
            timestamp,
            "2025-07-04T11:00:00Z",
        )


def test_forecast_requires_end_after_reference():
    with pytest.raises(
        ValueError,
        match="after reference_time",
    ):
        nwm_streamflow.fetch_nwm_forecast_streamflow(
            3586192,
            "2025-07-04T10:00:00Z",
            "2025-07-04T10:00:00Z",
        )


def test_normalization_rejects_missing_columns():
    with pytest.raises(
        ValueError,
        match="missing columns",
    ):
        nwm_streamflow._normalize_nwm_frame(pd.DataFrame({"feature_id": [3586192]}))


def test_low_level_errors_propagate(
    monkeypatch,
):
    class RetrievalFailure(RuntimeError):
        pass

    def fail(*args, **kwargs):
        raise RetrievalFailure("source identity failure")

    monkeypatch.setattr(
        nwm_streamflow,
        "fetch_operational_series",
        fail,
    )

    with pytest.raises(
        RetrievalFailure,
        match="source identity failure",
    ):
        nwm_streamflow.fetch_nwm_analysis_streamflow(
            3586192,
            "2025-07-04T09:00:00Z",
            "2025-07-04T09:00:00Z",
        )
