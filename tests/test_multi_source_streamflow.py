import time

import pandas as pd
import pytest

from streamflow_getter import multi_source_streamflow


def _frame(value):
    return pd.DataFrame(
        {
            "valid_time": pd.to_datetime(
                ["2025-07-04T09:00:00Z"],
                utc=True,
            ),
            "streamflow_m3s": [value],
        }
    )


def _install_fetchers(
    monkeypatch,
    *,
    delay=0.0,
):
    calls = []

    def analysis(
        feature_id,
        start_time,
        end_time,
        *,
        product,
        cache_dir,
    ):
        calls.append(
            ("analysis", product)
        )

        if delay:
            time.sleep(delay)

        return _frame(
            {
                "analysis_assim": 1.0,
                "analysis_assim_no_da": 2.0,
            }.get(product, 9.0)
        )

    def forecast(
        feature_id,
        reference_time,
        end_time,
        *,
        product,
        cache_dir,
    ):
        calls.append(
            ("forecast", product)
        )

        if delay:
            time.sleep(delay)

        return _frame(
            {
                "short_range": 3.0,
                "medium_range_blend": 4.0,
                "medium_range_no_da": 5.0,
            }.get(product, 8.0)
        )

    def usgs(
        gage_id,
        start_time,
        end_time,
        **kwargs,
    ):
        calls.append(
            ("usgs", gage_id, kwargs)
        )

        if delay:
            time.sleep(delay)

        return _frame(6.0)

    def geoglows(
        river_id,
        start_time,
        end_time,
    ):
        calls.append(
            ("geoglows", river_id)
        )

        if delay:
            time.sleep(delay)

        return _frame(7.0)

    monkeypatch.setattr(
        multi_source_streamflow,
        "fetch_nwm_analysis_streamflow",
        analysis,
    )

    monkeypatch.setattr(
        multi_source_streamflow,
        "fetch_nwm_forecast_streamflow",
        forecast,
    )

    monkeypatch.setattr(
        multi_source_streamflow,
        "fetch_usgs_streamflow",
        usgs,
    )

    monkeypatch.setattr(
        multi_source_streamflow,
        "fetch_geoglows_retrospective",
        geoglows,
    )

    return calls


def test_default_request_is_nwm_analysis_only(
    monkeypatch,
):
    _install_fetchers(
        monkeypatch
    )

    result = (
        multi_source_streamflow
        .fetch_multi_source_streamflow(
            3586192,
            "2025-07-04T07:00:00Z",
            "2025-07-04T10:00:00Z",
        )
    )

    assert result.requested_sources == (
        "analysis_assim",
        "analysis_assim_no_da",
    )

    assert result.omitted_sources == (
        "usgs",
        "geoglows",
    )


def test_full_request_preserves_source_order(
    monkeypatch,
):
    _install_fetchers(
        monkeypatch
    )

    result = (
        multi_source_streamflow
        .fetch_multi_source_streamflow(
            3586192,
            "2025-07-04T07:00:00Z",
            "2025-07-04T12:00:00Z",
            forecast_reference_time=(
                "2025-07-04T10:00:00Z"
            ),
            nwm_forecast_products=(
                "short_range",
                "medium_range_blend",
                "medium_range_no_da",
            ),
            usgs_gage_id="08165500",
            geoglows_river_id=770578531,
        )
    )

    assert result.requested_sources == (
        "analysis_assim",
        "analysis_assim_no_da",
        "short_range",
        "medium_range_blend",
        "medium_range_no_da",
        "usgs",
        "geoglows",
    )

    assert result.omitted_sources == ()


def test_parallel_and_sequential_results_match(
    monkeypatch,
):
    _install_fetchers(
        monkeypatch
    )

    kwargs = {
        "feature_id": 3586192,
        "start_time": "2025-07-04T07:00:00Z",
        "end_time": "2025-07-04T12:00:00Z",
        "forecast_reference_time": (
            "2025-07-04T10:00:00Z"
        ),
        "nwm_forecast_products": (
            "short_range",
            "medium_range_blend",
        ),
        "usgs_gage_id": "08165500",
        "geoglows_river_id": 770578531,
    }

    sequential = (
        multi_source_streamflow
        .fetch_multi_source_streamflow(
            **kwargs,
            max_workers=1,
        )
    )

    parallel = (
        multi_source_streamflow
        .fetch_multi_source_streamflow(
            **kwargs,
            max_workers=4,
        )
    )

    assert (
        sequential.requested_sources
        == parallel.requested_sources
    )

    for label in (
        sequential.requested_sources
    ):
        pd.testing.assert_frame_equal(
            sequential[label],
            parallel[label],
        )


def test_parallel_execution_is_faster(
    monkeypatch,
):
    _install_fetchers(
        monkeypatch,
        delay=0.05,
    )

    kwargs = {
        "feature_id": 3586192,
        "start_time": "2025-07-04T07:00:00Z",
        "end_time": "2025-07-04T12:00:00Z",
        "forecast_reference_time": (
            "2025-07-04T10:00:00Z"
        ),
        "nwm_forecast_products": (
            "short_range",
            "medium_range_blend",
            "medium_range_no_da",
        ),
        "usgs_gage_id": "08165500",
        "geoglows_river_id": 770578531,
    }

    sequential = (
        multi_source_streamflow
        .fetch_multi_source_streamflow(
            **kwargs,
            max_workers=1,
        )
    )

    parallel = (
        multi_source_streamflow
        .fetch_multi_source_streamflow(
            **kwargs,
            max_workers=4,
        )
    )

    assert (
        parallel.total_elapsed_seconds
        < sequential.total_elapsed_seconds
    )


def test_usgs_api_key_is_forwarded(
    monkeypatch,
):
    calls = _install_fetchers(
        monkeypatch
    )

    (
        multi_source_streamflow
        .fetch_multi_source_streamflow(
            3586192,
            "2025-07-04T07:00:00Z",
            "2025-07-04T10:00:00Z",
            nwm_analysis_products=(),
            usgs_gage_id="08165500",
            usgs_api_key="secret",
        )
    )

    usgs_call = next(
        call
        for call in calls
        if call[0] == "usgs"
    )

    assert usgs_call[2] == {
        "api_key": "secret"
    }


def test_requested_failure_is_propagated(
    monkeypatch,
):
    _install_fetchers(
        monkeypatch
    )

    def fail(
        river_id,
        start_time,
        end_time,
    ):
        raise RuntimeError(
            "GEOGLOWS failed"
        )

    monkeypatch.setattr(
        multi_source_streamflow,
        "fetch_geoglows_retrospective",
        fail,
    )

    with pytest.raises(
        RuntimeError,
        match="GEOGLOWS failed",
    ):
        (
            multi_source_streamflow
            .fetch_multi_source_streamflow(
                3586192,
                "2025-07-04T07:00:00Z",
                "2025-07-04T10:00:00Z",
                nwm_analysis_products=(),
                geoglows_river_id=770578531,
            )
        )


def test_forecast_requires_reference_time(
    monkeypatch,
):
    _install_fetchers(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="forecast_reference_time",
    ):
        (
            multi_source_streamflow
            .fetch_multi_source_streamflow(
                3586192,
                "2025-07-04T07:00:00Z",
                "2025-07-04T12:00:00Z",
                nwm_analysis_products=(),
                nwm_forecast_products=(
                    "short_range",
                ),
            )
        )


@pytest.mark.parametrize(
    "workers",
    [
        0,
        -1,
        True,
        1.5,
    ],
)
def test_invalid_worker_count(
    workers,
    monkeypatch,
):
    _install_fetchers(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        (
            multi_source_streamflow
            .fetch_multi_source_streamflow(
                3586192,
                "2025-07-04T07:00:00Z",
                "2025-07-04T10:00:00Z",
                max_workers=workers,
            )
        )


def test_no_sources_is_rejected(
    monkeypatch,
):
    _install_fetchers(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="No streamflow sources",
    ):
        (
            multi_source_streamflow
            .fetch_multi_source_streamflow(
                3586192,
                "2025-07-04T07:00:00Z",
                "2025-07-04T10:00:00Z",
                nwm_analysis_products=(),
            )
        )
