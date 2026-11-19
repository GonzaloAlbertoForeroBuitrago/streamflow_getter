"""Concurrent retrieval coordinator for streamflow sources.

This module coordinates already-resolved source identifiers. It does not
perform spatial matching, basin comparison, temporal alignment, resampling,
or visualization.

Each source adapter remains responsible for its own scientific and API
semantics.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from time import perf_counter

import pandas as pd

from streamflow_getter.geoglows.streamflow import (
    fetch_geoglows_retrospective,
)
from streamflow_getter.nwm.streamflow import (
    fetch_nwm_analysis_streamflow,
    fetch_nwm_forecast_streamflow,
)
from streamflow_getter.usgs.streamflow import (
    fetch_usgs_streamflow,
)

DEFAULT_NWM_ANALYSIS_PRODUCTS = (
    "analysis_assim",
    "analysis_assim_no_da",
)

DEFAULT_NWM_FORECAST_PRODUCTS = (
    "short_range",
    "medium_range_blend",
    "medium_range_no_da",
)

DEFAULT_MAX_WORKERS = 4
RECOMMENDED_MIN_WORKERS = 4
MAX_WORKERS = 7


@dataclass(frozen=True, slots=True)
class MultiSourceStreamflowResult:
    """Raw source retrieval result with timing metadata."""

    series: dict[str, pd.DataFrame]
    source_timings_seconds: dict[str, float]
    total_elapsed_seconds: float
    requested_sources: tuple[str, ...]
    omitted_sources: tuple[str, ...]

    def __getitem__(
        self,
        source: str,
    ) -> pd.DataFrame:
        """Return one retrieved source frame."""
        return self.series[source]


@dataclass(frozen=True, slots=True)
class _FetchTask:
    """One independently executable retrieval request."""

    label: str
    call: Callable[[], pd.DataFrame]


def _positive_worker_count(
    value: int,
) -> int:
    """Return a validated retrieval-worker count."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > MAX_WORKERS
    ):
        raise ValueError(
            "max_workers must be an integer from 1 through "
            f"{MAX_WORKERS}. The conservative default is "
            f"{DEFAULT_MAX_WORKERS}; values from "
            f"{RECOMMENDED_MIN_WORKERS} through "
            f"{MAX_WORKERS} are recommended for the current "
            "multi-source workflow."
        )

    return value


def _product_tuple(
    products,
    *,
    name: str,
) -> tuple[str, ...]:
    """Return normalized, unique NWM product names."""
    if isinstance(products, str):
        raise ValueError(f"{name} must be an iterable of product names")

    try:
        values = tuple(products)
    except TypeError as exc:
        raise ValueError(f"{name} must be an iterable of product names") from exc

    normalized = []

    for product in values:
        if not isinstance(product, str) or not product.strip():
            raise ValueError(f"{name} must contain nonempty strings")

        normalized.append(product.strip())

    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} contains duplicate products")

    return tuple(normalized)


def _timed_call(
    task: _FetchTask,
) -> tuple[pd.DataFrame, float]:
    """Execute one task and return its frame and elapsed seconds."""
    started = perf_counter()

    frame = task.call()

    elapsed = perf_counter() - started

    if not isinstance(
        frame,
        pd.DataFrame,
    ):
        raise TypeError(f"{task.label} retrieval did not return a DataFrame")

    return (
        frame,
        elapsed,
    )


def _validate_product_groups(
    analysis_products: tuple[str, ...],
    forecast_products: tuple[str, ...],
    forecast_reference_time,
) -> None:
    """Validate relationships between requested NWM product groups."""
    overlap = set(analysis_products).intersection(forecast_products)

    if overlap:
        raise ValueError(
            "NWM products cannot be requested as both "
            "analysis and forecast: " + ", ".join(sorted(overlap))
        )

    if forecast_products and forecast_reference_time is None:
        raise ValueError(
            "forecast_reference_time is required when forecast products are requested"
        )


def _analysis_tasks(
    feature_id: int,
    start_time,
    end_time,
    *,
    products: tuple[str, ...],
    cache_dir,
) -> list[_FetchTask]:
    """Build NWM analysis retrieval tasks."""
    return [
        _FetchTask(
            label=product,
            call=partial(
                fetch_nwm_analysis_streamflow,
                feature_id,
                start_time,
                end_time,
                product=product,
                cache_dir=cache_dir,
            ),
        )
        for product in products
    ]


def _forecast_tasks(
    feature_id: int,
    reference_time,
    end_time,
    *,
    products: tuple[str, ...],
    cache_dir,
) -> list[_FetchTask]:
    """Build NWM forecast retrieval tasks."""
    return [
        _FetchTask(
            label=product,
            call=partial(
                fetch_nwm_forecast_streamflow,
                feature_id,
                reference_time,
                end_time,
                product=product,
                cache_dir=cache_dir,
            ),
        )
        for product in products
    ]


def _usgs_task(
    gage_id: str,
    start_time,
    end_time,
    *,
    api_key: str | None,
) -> _FetchTask:
    """Build one optional USGS retrieval task."""
    kwargs = {}

    if api_key is not None:
        kwargs["api_key"] = api_key

    return _FetchTask(
        label="usgs",
        call=partial(
            fetch_usgs_streamflow,
            gage_id,
            start_time,
            end_time,
            **kwargs,
        ),
    )


def _geoglows_task(
    river_id: int,
    start_time,
    end_time,
) -> _FetchTask:
    """Build one optional GEOGLOWS retrieval task."""
    return _FetchTask(
        label="geoglows",
        call=partial(
            fetch_geoglows_retrospective,
            river_id,
            start_time,
            end_time,
        ),
    )


def _build_tasks(
    *,
    feature_id: int,
    start_time,
    end_time,
    forecast_reference_time,
    analysis_products: tuple[str, ...],
    forecast_products: tuple[str, ...],
    usgs_gage_id: str | None,
    geoglows_river_id: int | None,
    cache_dir,
    usgs_api_key: str | None,
) -> tuple[
    list[_FetchTask],
    tuple[str, ...],
]:
    """Build independent source retrieval tasks and normal omissions."""
    _validate_product_groups(
        analysis_products,
        forecast_products,
        forecast_reference_time,
    )

    tasks = _analysis_tasks(
        feature_id,
        start_time,
        end_time,
        products=analysis_products,
        cache_dir=cache_dir,
    )

    tasks.extend(
        _forecast_tasks(
            feature_id,
            forecast_reference_time,
            end_time,
            products=forecast_products,
            cache_dir=cache_dir,
        )
    )

    omitted = []

    if usgs_gage_id is None:
        omitted.append("usgs")
    else:
        tasks.append(
            _usgs_task(
                usgs_gage_id,
                start_time,
                end_time,
                api_key=usgs_api_key,
            )
        )

    if geoglows_river_id is None:
        omitted.append("geoglows")
    else:
        tasks.append(
            _geoglows_task(
                geoglows_river_id,
                start_time,
                end_time,
            )
        )

    return (
        tasks,
        tuple(omitted),
    )


def _run_tasks(
    tasks: list[_FetchTask],
    *,
    max_workers: int,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, float],
]:
    """Execute retrieval tasks while preserving request order."""
    if not tasks:
        return (
            {},
            {},
        )

    worker_count = min(
        max_workers,
        len(tasks),
    )

    if worker_count == 1:
        completed = {task.label: _timed_call(task) for task in tasks}

    else:
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="streamflow-getter",
        ) as executor:
            results = executor.map(_timed_call, tasks)
            completed = dict(
                zip(
                    (task.label for task in tasks),
                    results,
                    strict=True,
                )
            )

    series = {label: result[0] for label, result in completed.items()}

    timings = {label: result[1] for label, result in completed.items()}

    return (
        series,
        timings,
    )


def fetch_multi_source_streamflow(
    feature_id: int,
    start_time,
    end_time,
    *,
    forecast_reference_time=None,
    nwm_analysis_products=(DEFAULT_NWM_ANALYSIS_PRODUCTS),
    nwm_forecast_products=(),
    usgs_gage_id: str | None = None,
    geoglows_river_id: int | None = None,
    cache_dir=None,
    usgs_api_key: str | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> MultiSourceStreamflowResult:
    """Retrieve independent streamflow sources concurrently.

    Identifiers must already be resolved. Missing optional USGS or
    GEOGLOWS identifiers are normal omissions. Requested-source failures
    are propagated rather than silently ignored.
    """
    workers = _positive_worker_count(max_workers)

    analyses = _product_tuple(
        nwm_analysis_products,
        name="nwm_analysis_products",
    )

    forecasts = _product_tuple(
        nwm_forecast_products,
        name="nwm_forecast_products",
    )

    tasks, omitted = _build_tasks(
        feature_id=feature_id,
        start_time=start_time,
        end_time=end_time,
        forecast_reference_time=(forecast_reference_time),
        analysis_products=analyses,
        forecast_products=forecasts,
        usgs_gage_id=usgs_gage_id,
        geoglows_river_id=(geoglows_river_id),
        cache_dir=cache_dir,
        usgs_api_key=usgs_api_key,
    )

    if not tasks:
        raise ValueError("No streamflow sources were requested")

    started = perf_counter()

    series, timings = _run_tasks(
        tasks,
        max_workers=workers,
    )

    total_elapsed = perf_counter() - started

    return MultiSourceStreamflowResult(
        series=series,
        source_timings_seconds=timings,
        total_elapsed_seconds=total_elapsed,
        requested_sources=tuple(series),
        omitted_sources=omitted,
    )
