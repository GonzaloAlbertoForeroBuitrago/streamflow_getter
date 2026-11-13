"""Tests for standalone operational NWM analysis products."""

import pytest

from streamflow_getter.cli import build_parser, main
from streamflow_getter.operational_nwm import (
    ForecastConfig,
    PRODUCT_SPECS,
    fetch_operational_series,
    resolve_operational_source,
)


ANALYSIS_PRODUCTS = (
    "analysis_assim",
    "analysis_assim_no_da",
)


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_analysis_products_are_registered(product):
    spec = PRODUCT_SPECS[product]

    assert spec.analysis_only is True
    assert spec.cycles == tuple(range(24))
    assert spec.max_hour == 0
    assert spec.channel_family == "channel_rt"
    assert spec.analysis_product == product


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
@pytest.mark.parametrize("cycle", [0, 1, 6, 9, 12, 18, 23])
def test_analysis_products_accept_hourly_cycles(product, cycle):
    config = ForecastConfig(
        date="2025-07-04",
        cycle=cycle,
        product=product,
    )

    assert config.cycle == cycle
    assert config.spec.analysis_only is True


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_analysis_products_have_no_forecast_leads(product):
    config = ForecastConfig(
        date="2025-07-04",
        cycle=9,
        product=product,
    )

    assert config.forecast_hours(1, 18) == []

    with pytest.raises(
        ValueError,
        match="analysis-only",
    ):
        config.filename(1)


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_analysis_product_source_identity(product):
    config = ForecastConfig(
        date="2025-07-04",
        cycle=9,
        product=product,
    )

    source = resolve_operational_source(
        config,
        0,
    )

    expected_filename = (
        f"nwm.t09z.{product}."
        "channel_rt.tm00.conus.nc"
    )

    assert source["source_product"] == product
    assert source["lead_hour"] == 0
    assert source["filename"] == expected_filename
    assert expected_filename in source["native_url"]
    assert expected_filename in source["reference_path"]


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_analysis_products_reject_forecast_source(product):
    config = ForecastConfig(
        date="2025-07-04",
        cycle=9,
        product=product,
    )

    with pytest.raises(
        ValueError,
        match="analysis-only",
    ):
        resolve_operational_source(
            config,
            1,
        )


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_analysis_series_fetches_only_t0(
    monkeypatch,
    product,
):
    calls = []

    def fake_fetch(
        config,
        hour,
        reach_ids,
        *,
        cache_dir=None,
    ):
        calls.append({
            "product": config.product,
            "hour": hour,
            "reaches": list(reach_ids),
            "cache_dir": cache_dir,
        })

        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": product,
            "domain": config.domain,
            "lead_hour": 0,
            "method": "kerchunk",
            "valid_time": (
                "2025-07-04T09:00:00.000000000"
            ),
            "reference_time": (
                "2025-07-04T06:00:00.000000000"
            ),
            "streamflow_m3s": {
                3586192: 1.0,
            },
        }

    monkeypatch.setattr(
        "streamflow_getter.operational_nwm."
        "fetch_operational_forecast",
        fake_fetch,
    )

    config = ForecastConfig(
        date="2025-07-04",
        cycle=9,
        product=product,
    )

    frame = fetch_operational_series(
        config,
        [3586192],
        start_hour=1,
        end_hour=18,
        include_t0=True,
        cache_dir=None,
    )

    assert len(calls) == 1
    assert calls[0]["hour"] == 0

    assert len(frame) == 1
    assert frame.iloc[0]["lead_hour"] == 0
    assert frame.iloc[0]["product"] == product
    assert frame.iloc[0]["feature_id"] == 3586192


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_analysis_series_requires_t0(product):
    config = ForecastConfig(
        date="2025-07-04",
        cycle=9,
        product=product,
    )

    with pytest.raises(
        ValueError,
        match="requires include_t0=True",
    ):
        fetch_operational_series(
            config,
            [3586192],
            start_hour=1,
            end_hour=18,
            include_t0=False,
            cache_dir=None,
        )


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_cli_parser_accepts_analysis_products(product):
    parser = build_parser()

    args = parser.parse_args([
        "nwm-operational",
        "--date", "2025-07-04",
        "--cycle", "9",
        "--product", product,
        "--reach", "3586192",
        "--out", "analysis.csv",
    ])

    assert args.product == product
    assert args.cycle == 9


@pytest.mark.parametrize("product", ANALYSIS_PRODUCTS)
def test_cli_rejects_no_t0_for_analysis_product(
    tmp_path,
    product,
):
    output = tmp_path / "analysis.csv"

    with pytest.raises(
        ValueError,
        match="Analysis-only products cannot be used with --no-t0",
    ):
        main([
            "nwm-operational",
            "--date", "2025-07-04",
            "--cycle", "9",
            "--product", product,
            "--reach", "3586192",
            "--no-t0",
            "--no-cache",
            "--out", str(output),
        ])

    assert not output.exists()
