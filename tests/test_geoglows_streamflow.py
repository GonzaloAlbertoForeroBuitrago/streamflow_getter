import numpy as np
import pandas as pd
import pytest
import xarray as xr

from streamflow_getter.geoglows import (
    streamflow as geoglows_streamflow,
)


RIVER_ID = 770578531


def fake_dataset(
    *,
    units="m3 s-1",
    aggregation="mean",
    values=None,
):
    times = pd.date_range(
        "2025-07-04T06:00:00",
        periods=8,
        freq="h",
    )

    rivers = np.array(
        [
            RIVER_ID,
            770578532,
        ],
        dtype=np.int64,
    )

    if values is None:
        values = np.array(
            [
                [1.0, 10.0],
                [1.85, 11.0],
                [1.77, 12.0],
                [1.83, 13.0],
                [3.76, 14.0],
                [5.62, 15.0],
                [4.90, 16.0],
                [6.10, 17.0],
            ],
            dtype=np.float32,
        )

    dataset = xr.Dataset(
        {
            "Q": (
                (
                    "time",
                    "river_id",
                ),
                values,
            )
        },
        coords={
            "time": times,
            "river_id": rivers,
        },
    )

    dataset["Q"].attrs.update(
        {
            "aggregation_method": aggregation,
            "long_name": ("Discharge at catchment outlet"),
            "units": units,
        }
    )

    return dataset


@pytest.fixture(autouse=True)
def clear_cache():
    (geoglows_streamflow.clear_geoglows_dataset_cache())

    yield

    (geoglows_streamflow.clear_geoglows_dataset_cache())


def test_dataset_open_is_cached(
    monkeypatch,
):
    calls = []

    def fake_open_dataset(
        uri,
        *,
        engine,
        storage_options,
    ):
        calls.append(
            (
                uri,
                engine,
                storage_options,
            )
        )
        return fake_dataset()

    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        fake_open_dataset,
    )

    first = geoglows_streamflow.open_geoglows_retrospective_dataset()

    second = geoglows_streamflow.open_geoglows_retrospective_dataset()

    assert first is second
    assert len(calls) == 1

    assert calls[0][1] == "zarr"
    assert calls[0][2] == {"anon": True}


def test_retrospective_hourly_contract(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    frame = geoglows_streamflow.fetch_geoglows_retrospective(
        RIVER_ID,
        "2025-07-04T07:00:00Z",
        "2025-07-04T12:00:00Z",
    )

    assert len(frame) == 5

    assert frame["streamflow_m3s"].tolist() == pytest.approx(
        [
            1.85,
            1.77,
            1.83,
            3.76,
            5.62,
        ]
    )

    assert frame["source"].eq("geoglows").all()

    assert frame["series"].eq("retrospective_hourly").all()

    assert frame["geoglows_river_id"].eq(RIVER_ID).all()

    assert frame["unit"].eq("m3/s").all()

    assert frame["time_support"].eq("hourly_mean").all()

    assert frame["aggregation"].eq("mean").all()

    assert frame["method"].eq("geoglows_zarr").all()

    assert frame["model_version"].eq("rfs-v2").all()


def test_retrospective_uses_half_open_window(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    frame = geoglows_streamflow.fetch_geoglows_retrospective(
        RIVER_ID,
        "2025-07-04T07:00:00Z",
        "2025-07-04T10:00:00Z",
    )

    assert frame["valid_time"].tolist() == [
        pd.Timestamp("2025-07-04T07:00:00Z"),
        pd.Timestamp("2025-07-04T08:00:00Z"),
        pd.Timestamp("2025-07-04T09:00:00Z"),
    ]


def test_interval_end_is_one_hour_later(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    frame = geoglows_streamflow.fetch_geoglows_retrospective(
        RIVER_ID,
        "2025-07-04T07:00:00Z",
        "2025-07-04T09:00:00Z",
    )

    assert (
        (frame["interval_end"] - frame["interval_start"])
        .eq(pd.Timedelta(hours=1))
        .all()
    )


def test_retrospective_timestamps_are_utc(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    frame = geoglows_streamflow.fetch_geoglows_retrospective(
        RIVER_ID,
        "2025-07-04T07:00:00-05:00",
        "2025-07-04T14:00:00-05:00",
    )

    assert frame["valid_time"].dt.tz is not None

    assert str(frame["valid_time"].dt.tz) == "UTC"


@pytest.mark.parametrize(
    "river_id",
    [
        0,
        -1,
        True,
        770578531.0,
        "770578531",
    ],
)
def test_invalid_river_id(
    river_id,
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        (
            geoglows_streamflow.fetch_geoglows_retrospective(
                river_id,
                "2025-07-04T07:00:00Z",
                "2025-07-04T12:00:00Z",
            )
        )


@pytest.mark.parametrize(
    "timestamp",
    [
        "2025-07-04 07:00:00",
        "2025-07-04T07:15:00Z",
    ],
)
def test_invalid_time(
    timestamp,
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    with pytest.raises(ValueError):
        (
            geoglows_streamflow.fetch_geoglows_retrospective(
                RIVER_ID,
                timestamp,
                "2025-07-04T12:00:00Z",
            )
        )


def test_end_must_follow_start(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    with pytest.raises(
        ValueError,
        match="after start_time",
    ):
        (
            geoglows_streamflow.fetch_geoglows_retrospective(
                RIVER_ID,
                "2025-07-04T07:00:00Z",
                "2025-07-04T07:00:00Z",
            )
        )


def test_dataset_requires_q(
    monkeypatch,
):
    dataset = xr.Dataset(
        coords={
            "time": pd.date_range(
                "2025-07-04",
                periods=2,
                freq="h",
            ),
            "river_id": [RIVER_ID],
        }
    )

    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: dataset,
    )

    with pytest.raises(
        ValueError,
        match="does not contain Q",
    ):
        (geoglows_streamflow.open_geoglows_retrospective_dataset())


def test_dataset_requires_expected_units(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(units="ft3/s"),
    )

    with pytest.raises(
        ValueError,
        match="Unexpected GEOGLOWS discharge units",
    ):
        (geoglows_streamflow.open_geoglows_retrospective_dataset())


def test_dataset_requires_mean_aggregation(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(aggregation="instantaneous"),
    )

    with pytest.raises(
        ValueError,
        match="Unexpected GEOGLOWS aggregation",
    ):
        (geoglows_streamflow.open_geoglows_retrospective_dataset())


def test_missing_river_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(),
    )

    with pytest.raises(
        ValueError,
        match="river ID not found",
    ):
        (
            geoglows_streamflow.fetch_geoglows_retrospective(
                999999999,
                "2025-07-04T07:00:00Z",
                "2025-07-04T12:00:00Z",
            )
        )


def test_nonfinite_streamflow_is_rejected(
    monkeypatch,
):
    values = np.array(
        [
            [1.0, 10.0],
            [np.nan, 11.0],
            [1.7, 12.0],
            [1.8, 13.0],
            [1.9, 14.0],
            [2.0, 15.0],
            [2.1, 16.0],
            [2.2, 17.0],
        ],
        dtype=np.float32,
    )

    monkeypatch.setattr(
        geoglows_streamflow.xr,
        "open_dataset",
        lambda *args, **kwargs: fake_dataset(values=values),
    )

    with pytest.raises(
        ValueError,
        match="non-finite",
    ):
        (
            geoglows_streamflow.fetch_geoglows_retrospective(
                RIVER_ID,
                "2025-07-04T07:00:00Z",
                "2025-07-04T12:00:00Z",
            )
        )


def test_invalid_geoglows_dataset_closes_resources(monkeypatch):
    """A dataset rejected during validation releases its resources."""
    import xarray as xr
    from streamflow_getter.geoglows import streamflow as adapter

    closed = []
    dataset = xr.Dataset()
    dataset.set_close(lambda: closed.append(True))

    monkeypatch.setattr(
        adapter.xr,
        "open_dataset",
        lambda *args, **kwargs: dataset,
    )

    adapter.clear_geoglows_dataset_cache()

    try:
        with pytest.raises(
            ValueError,
            match="does not contain Q",
        ):
            adapter.open_geoglows_retrospective_dataset()

        assert closed == [True]
    finally:
        adapter.clear_geoglows_dataset_cache()


def test_geoglows_cleanup_preserves_validation_error(monkeypatch):
    """A failed close must not mask the validation exception."""
    import xarray as xr
    from streamflow_getter.geoglows import streamflow as adapter

    dataset = xr.Dataset()

    def failing_close():
        raise OSError("simulated close failure")

    dataset.set_close(failing_close)

    monkeypatch.setattr(
        adapter.xr,
        "open_dataset",
        lambda *args, **kwargs: dataset,
    )

    adapter.clear_geoglows_dataset_cache()

    try:
        with pytest.raises(
            ValueError,
            match="does not contain Q",
        ) as error:
            adapter.open_geoglows_retrospective_dataset()

        assert any("simulated close failure" in note for note in error.value.__notes__)
    finally:
        adapter.clear_geoglows_dataset_cache()


def test_concurrent_geoglows_open_reuses_one_dataset(monkeypatch):
    """Simultaneous cache misses must share one dataset instance."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    import time

    from streamflow_getter.geoglows import streamflow as adapter

    adapter.clear_geoglows_dataset_cache()

    barrier = Barrier(6)
    counter_lock = Lock()
    opens = []

    def fake_open(*args, **kwargs):
        with counter_lock:
            opens.append(1)
        time.sleep(0.03)
        return fake_dataset()

    monkeypatch.setattr(
        adapter.xr,
        "open_dataset",
        fake_open,
    )

    def worker(_):
        barrier.wait()
        return adapter.open_geoglows_retrospective_dataset()

    try:
        with ThreadPoolExecutor(max_workers=6) as executor:
            datasets = list(executor.map(worker, range(6)))

        assert len(opens) == 1
        assert len({id(dataset) for dataset in datasets}) == 1
        assert adapter.open_geoglows_retrospective_dataset.cache_info().currsize == 1
    finally:
        adapter.clear_geoglows_dataset_cache()
