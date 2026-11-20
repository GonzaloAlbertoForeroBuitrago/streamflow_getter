import json
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

from streamflow_getter.usgs import streamflow as usgs_streamflow


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def install_payloads(
    monkeypatch,
    payloads,
    *,
    urls=None,
    headers=None,
):
    queue = list(payloads)

    def fake_urlopen(request, timeout):
        if urls is not None:
            urls.append(request.full_url)

        if headers is not None:
            headers.append(
                {key.casefold(): value for key, value in request.header_items()}
            )

        if not queue:
            raise AssertionError("Unexpected additional USGS request")

        return FakeResponse(queue.pop(0))

    monkeypatch.setattr(
        usgs_streamflow,
        "urlopen",
        fake_urlopen,
    )

    return queue


def location_feature():
    return {
        "type": "Feature",
        "id": "USGS-08165500",
        "geometry": {
            "type": "Point",
            "coordinates": [
                -99.3217122,
                30.06993074,
            ],
        },
        "properties": {
            "id": "USGS-08165500",
            "monitoring_location_name": ("Guadalupe Rv at Hunt, TX"),
            "site_type": "Stream",
            "hydrologic_unit_code": "121002010108",
            "drainage_area": 288.0,
            "contributing_drainage_area": 288.0,
            "horizontal_positional_accuracy": ("Accurate to + or - 5 sec."),
        },
    }


def continuous_feature(
    time,
    value,
    *,
    unit="ft^3/s",
    time_series_id="series-1",
):
    return {
        "type": "Feature",
        "properties": {
            "monitoring_location_id": "USGS-08165500",
            "parameter_code": "00060",
            "statistic_id": "00011",
            "time": time,
            "value": str(value),
            "unit_of_measure": unit,
            "time_series_id": time_series_id,
            "approval_status": "Approved",
            "qualifier": None,
        },
    }


def test_monitoring_location_metadata(monkeypatch):
    urls = []

    install_payloads(
        monkeypatch,
        [
            {
                "features": [location_feature()],
                "links": [],
            }
        ],
        urls=urls,
    )

    metadata = usgs_streamflow.fetch_usgs_monitoring_location("08165500")

    assert metadata["source"] == "usgs"
    assert metadata["source_id"] == "08165500"
    assert metadata["monitoring_location_name"] == "Guadalupe Rv at Hunt, TX"

    assert metadata["longitude"] == pytest.approx(-99.3217122)
    assert metadata["latitude"] == pytest.approx(30.06993074)
    assert metadata["drainage_area_sqmi"] == 288.0
    assert metadata["contributing_drainage_area_sqmi"] == 288.0

    assert metadata["drainage_area_km2"] == pytest.approx(
        288.0 * usgs_streamflow.SQMI_TO_KM2
    )

    query = parse_qs(urlsplit(urls[0]).query)

    assert query["id"] == ["USGS-08165500"]


def test_api_key_uses_header_not_url(monkeypatch):
    urls = []
    headers = []

    install_payloads(
        monkeypatch,
        [
            {
                "features": [location_feature()],
                "links": [],
            }
        ],
        urls=urls,
        headers=headers,
    )

    usgs_streamflow.fetch_usgs_monitoring_location(
        "08165500",
        api_key="fake-test-key",
    )

    assert "api_key=" not in urls[0].casefold()
    assert headers[0]["x-api-key"] == "fake-test-key"


def test_environment_api_key(monkeypatch):
    headers = []

    monkeypatch.setenv(
        "USGS_API_KEY",
        "environment-test-key",
    )

    install_payloads(
        monkeypatch,
        [
            {
                "features": [location_feature()],
                "links": [],
            }
        ],
        headers=headers,
    )

    usgs_streamflow.fetch_usgs_monitoring_location("08165500")

    assert headers[0]["x-api-key"] == "environment-test-key"


def test_streamflow_converts_cfs_to_m3s(monkeypatch):
    urls = []

    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        84.7,
                    ),
                    continuous_feature(
                        "2025-07-04T07:05:00Z",
                        121.0,
                    ),
                ],
                "links": [],
            }
        ],
        urls=urls,
    )

    frame = usgs_streamflow.fetch_usgs_streamflow(
        "08165500",
        "2025-07-04T07:00:00Z",
        "2025-07-04T08:00:00Z",
    )

    assert len(frame) == 2
    assert frame["source"].eq("usgs").all()
    assert frame["series"].eq("observation").all()
    assert frame["unit"].eq("m3/s").all()
    assert frame["time_support"].eq("instantaneous").all()

    assert frame.loc[
        0,
        "streamflow_m3s",
    ] == pytest.approx(84.7 * usgs_streamflow.CFS_TO_M3S)

    assert frame["valid_time"].dt.tz is not None

    query = parse_qs(urlsplit(urls[0]).query)

    assert query["monitoring_location_id"] == ["USGS-08165500"]
    assert query["parameter_code"] == ["00060"]


def test_streamflow_preserves_native_m3s(monkeypatch):
    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        12.5,
                        unit="m3/s",
                    )
                ],
                "links": [],
            }
        ],
    )

    frame = usgs_streamflow.fetch_usgs_streamflow(
        "08165500",
        "2025-07-04T07:00:00Z",
        "2025-07-04T08:00:00Z",
    )

    assert frame.loc[
        0,
        "streamflow_m3s",
    ] == pytest.approx(12.5)


def test_streamflow_uses_half_open_interval(monkeypatch):
    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        10,
                    ),
                    continuous_feature(
                        "2025-07-04T07:59:59Z",
                        20,
                    ),
                    continuous_feature(
                        "2025-07-04T08:00:00Z",
                        30,
                    ),
                ],
                "links": [],
            }
        ],
    )

    frame = usgs_streamflow.fetch_usgs_streamflow(
        "08165500",
        "2025-07-04T07:00:00Z",
        "2025-07-04T08:00:00Z",
    )

    assert frame["valid_time"].tolist() == [
        pd.Timestamp("2025-07-04T07:00:00Z"),
        pd.Timestamp("2025-07-04T07:59:59Z"),
    ]


def test_streamflow_empty_response(monkeypatch):
    install_payloads(
        monkeypatch,
        [{"features": [], "links": []}],
    )

    frame = usgs_streamflow.fetch_usgs_streamflow(
        "08165500",
        "2025-07-04T07:00:00Z",
        "2025-07-04T08:00:00Z",
    )

    assert frame.empty
    assert list(frame.columns) == usgs_streamflow.USGS_STREAMFLOW_COLUMNS


def test_streamflow_rejects_unknown_unit(monkeypatch):
    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        10,
                        unit="unknown",
                    )
                ],
                "links": [],
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="Unrecognized USGS discharge unit",
    ):
        usgs_streamflow.fetch_usgs_streamflow(
            "08165500",
            "2025-07-04T07:00:00Z",
            "2025-07-04T08:00:00Z",
        )


def test_streamflow_rejects_naive_time():
    with pytest.raises(
        ValueError,
        match="explicit timezone",
    ):
        usgs_streamflow.fetch_usgs_streamflow(
            "08165500",
            "2025-07-04 07:00:00",
            "2025-07-04T08:00:00Z",
        )


def test_streamflow_rejects_conflicting_duplicates(
    monkeypatch,
):
    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        10,
                        time_series_id="series-1",
                    ),
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        20,
                        time_series_id="series-2",
                    ),
                ],
                "links": [],
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="Conflicting USGS discharge values",
    ):
        usgs_streamflow.fetch_usgs_streamflow(
            "08165500",
            "2025-07-04T07:00:00Z",
            "2025-07-04T08:00:00Z",
        )


def test_pagination_follows_same_host(monkeypatch):
    urls = []
    headers = []

    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        10,
                    )
                ],
                "links": [
                    {
                        "rel": "next",
                        "href": "?page=2",
                    }
                ],
            },
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:05:00Z",
                        20,
                    )
                ],
                "links": [],
            },
        ],
        urls=urls,
        headers=headers,
    )

    frame = usgs_streamflow.fetch_usgs_streamflow(
        "08165500",
        "2025-07-04T07:00:00Z",
        "2025-07-04T08:00:00Z",
        api_key="fake-test-key",
    )

    assert len(frame) == 2
    assert len(urls) == 2
    assert all(urlsplit(url).netloc == "api.waterdata.usgs.gov" for url in urls)
    assert all(header["x-api-key"] == "fake-test-key" for header in headers)


def test_pagination_rejects_foreign_host(monkeypatch):
    install_payloads(
        monkeypatch,
        [
            {
                "features": [],
                "links": [
                    {
                        "rel": "next",
                        "href": "https://example.com/next",
                    }
                ],
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="unexpected host",
    ):
        usgs_streamflow.fetch_usgs_streamflow(
            "08165500",
            "2025-07-04T07:00:00Z",
            "2025-07-04T08:00:00Z",
        )


def test_pagination_rejects_repeated_url(monkeypatch):
    install_payloads(
        monkeypatch,
        [
            {
                "features": [],
                "links": [
                    {
                        "rel": "next",
                        "href": (
                            "https://api.waterdata.usgs.gov/"
                            "ogcapi/v1/collections/continuous/"
                            "items?repeat=1"
                        ),
                    }
                ],
            },
            {
                "features": [],
                "links": [
                    {
                        "rel": "next",
                        "href": (
                            "https://api.waterdata.usgs.gov/"
                            "ogcapi/v1/collections/continuous/"
                            "items?repeat=1"
                        ),
                    }
                ],
            },
        ],
    )

    with pytest.raises(
        ValueError,
        match="repeated the same URL",
    ):
        usgs_streamflow.fetch_usgs_streamflow(
            "08165500",
            "2025-07-04T07:00:00Z",
            "2025-07-04T08:00:00Z",
        )


@pytest.mark.parametrize(
    "gage_id",
    [
        "",
        "08165A00",
        "USGS-08165500",
    ],
)
def test_invalid_gage_id(gage_id):
    with pytest.raises(ValueError):
        usgs_streamflow.fetch_usgs_streamflow(
            gage_id,
            "2025-07-04T07:00:00Z",
            "2025-07-04T08:00:00Z",
        )


def test_identical_usgs_observations_are_deduplicated(monkeypatch):
    """Equal observations at one UTC timestamp produce one row."""
    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        10.0,
                        time_series_id="series-2",
                    ),
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        10.0,
                        time_series_id="series-1",
                    ),
                ],
                "links": [],
            }
        ],
    )

    frame = usgs_streamflow.fetch_usgs_streamflow(
        "08165500",
        "2025-07-04T07:00:00Z",
        "2025-07-04T08:00:00Z",
    )

    assert len(frame) == 1
    assert frame.iloc[0]["time_series_id"] == "series-1"
    assert frame.iloc[0]["native_value"] == 10.0


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_usgs_rejects_nonfinite_discharge(monkeypatch, value):
    """Non-finite discharge must never enter the output."""
    install_payloads(
        monkeypatch,
        [
            {
                "features": [
                    continuous_feature(
                        "2025-07-04T07:00:00Z",
                        value,
                    )
                ],
                "links": [],
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="Invalid USGS discharge value",
    ):
        usgs_streamflow.fetch_usgs_streamflow(
            "08165500",
            "2025-07-04T07:00:00Z",
            "2025-07-04T08:00:00Z",
        )
