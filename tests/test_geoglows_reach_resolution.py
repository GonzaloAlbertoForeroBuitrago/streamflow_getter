import json

import pytest

from streamflow_getter.geoglows import (
    reach_resolution as geoglows_reach_resolution,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def feature(
    river_id,
    *,
    lon,
    lat,
    area_m2=None,
    stream_order=4,
):
    return {
        "attributes": {
            "comid": river_id,
            "upstreamarea": area_m2,
            "streamorder": stream_order,
        },
        "geometry": {
            "paths": [
                [
                    [lon, lat - 0.001],
                    [lon, lat + 0.001],
                ]
            ]
        },
    }


def install_payload(
    monkeypatch,
    payload,
):
    monkeypatch.setattr(
        geoglows_reach_resolution,
        "urlopen",
        lambda request, timeout: FakeResponse(payload),
    )


def test_candidates_are_sorted_by_distance(
    monkeypatch,
):
    install_payload(
        monkeypatch,
        {
            "features": [
                feature(
                    2,
                    lon=-99.325,
                    lat=30.07,
                    area_m2=800_000_000,
                ),
                feature(
                    1,
                    lon=-99.322,
                    lat=30.07,
                    area_m2=750_000_000,
                ),
            ],
            "exceededTransferLimit": False,
        },
    )

    candidates = geoglows_reach_resolution.find_geoglows_reach_candidates(
        -99.3217,
        30.0699,
        max_distance_m=1000,
    )

    assert [candidate["river_id"] for candidate in candidates] == [1, 2]


def test_candidate_preserves_area_and_order(
    monkeypatch,
):
    install_payload(
        monkeypatch,
        {
            "features": [
                feature(
                    770578531,
                    lon=-99.322,
                    lat=30.07,
                    area_m2=788_289_088,
                    stream_order=4,
                )
            ],
            "exceededTransferLimit": False,
        },
    )

    candidate = geoglows_reach_resolution.nearest_geoglows_reach(
        -99.3217,
        30.0699,
        max_distance_m=1000,
    )

    assert candidate is not None

    assert candidate["river_id"] == 770578531

    assert candidate["upstream_area_km2"] == pytest.approx(788.289088)

    assert candidate["stream_order"] == 4


def test_missing_area_is_allowed(
    monkeypatch,
):
    install_payload(
        monkeypatch,
        {
            "features": [
                feature(
                    1,
                    lon=-99.322,
                    lat=30.07,
                    area_m2=None,
                )
            ],
            "exceededTransferLimit": False,
        },
    )

    candidate = geoglows_reach_resolution.nearest_geoglows_reach(
        -99.3217,
        30.0699,
    )

    assert candidate is not None
    assert candidate["upstream_area_km2"] is None


def test_no_candidate_returns_none(
    monkeypatch,
):
    install_payload(
        monkeypatch,
        {
            "features": [],
            "exceededTransferLimit": False,
        },
    )

    assert (
        geoglows_reach_resolution.nearest_geoglows_reach(
            -99.3217,
            30.0699,
        )
        is None
    )


def test_candidate_outside_radius_is_removed(
    monkeypatch,
):
    install_payload(
        monkeypatch,
        {
            "features": [
                feature(
                    1,
                    lon=-99.5,
                    lat=30.07,
                )
            ],
            "exceededTransferLimit": False,
        },
    )

    candidates = geoglows_reach_resolution.find_geoglows_reach_candidates(
        -99.3217,
        30.0699,
        max_distance_m=100,
    )

    assert candidates == []


@pytest.mark.parametrize(
    ("longitude", "latitude"),
    [
        (181, 30),
        (-181, 30),
        (-99, 91),
        (-99, -91),
    ],
)
def test_invalid_coordinates(
    longitude,
    latitude,
):
    with pytest.raises(
        ValueError,
    ):
        (
            geoglows_reach_resolution.find_geoglows_reach_candidates(
                longitude,
                latitude,
            )
        )


@pytest.mark.parametrize(
    "radius",
    [
        0,
        -1,
        25_001,
        True,
    ],
)
def test_invalid_radius(
    radius,
):
    with pytest.raises(
        ValueError,
    ):
        (
            geoglows_reach_resolution.find_geoglows_reach_candidates(
                -99.3217,
                30.0699,
                max_distance_m=radius,
            )
        )


def test_service_error_is_propagated(
    monkeypatch,
):
    install_payload(
        monkeypatch,
        {"error": {"message": "service failure"}},
    )

    with pytest.raises(
        ValueError,
        match="service error",
    ):
        (
            geoglows_reach_resolution.find_geoglows_reach_candidates(
                -99.3217,
                30.0699,
            )
        )
