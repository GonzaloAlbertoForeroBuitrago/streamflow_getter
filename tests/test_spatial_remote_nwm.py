"""Tests for remote NOAA NWM reach selection; no live HTTP requests."""

import pytest

from streamflow_getter.nwm import remote_reach_resolution as remote


def _flowline(feature_id, latitude, *, version=3.0):
    return {
        "type": "Feature",
        "properties": {"feature_id": feature_id, "nwm_vers": version, "name": "test"},
        "geometry": {
            "type": "LineString",
            "coordinates": [[-99.32, latitude], [-99.30, latitude]],
        },
    }


def test_nearest_v3_with_no_local_hydrofabric(monkeypatch):
    def query(parameters, *, timeout):
        assert parameters["outFields"] == "feature_id,nwm_vers,name"
        assert parameters["f"] == "geojson"
        assert timeout == 30.0
        return {
            "features": [
                _flowline("123", 30.071),
                _flowline("456", 30.070),
                _flowline("999", 30.070, version=2.1),
            ]
        }

    monkeypatch.setattr(remote, "_fetch_flowlines", query)
    result = remote.nearest_nwm_reach_remote(-99.31, 30.07)
    assert result["feature_id"] == 456
    assert result["distance_m"] < 1
    assert result["nwm_version"] == 3.0
    assert result["geometry"]["type"] == "LineString"


def test_no_reach_within_radius_returns_none(monkeypatch):
    monkeypatch.setattr(
        remote,
        "_fetch_flowlines",
        lambda parameters, *, timeout: {"features": [_flowline("123", 30.4)]},
    )
    assert remote.nearest_nwm_reach_remote(-99.31, 30.07) is None


def test_service_result_limit_is_not_silently_truncated(monkeypatch):
    monkeypatch.setattr(
        remote,
        "_fetch_flowlines",
        lambda parameters, *, timeout: {"features": [], "exceededTransferLimit": True},
    )
    with pytest.raises(ValueError, match="result limit"):
        remote.nearest_nwm_reach_remote(-99.31, 30.07)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_distance_m": 0}, "Radius"),
        ({"max_distance_m": 26_000}, "Radius"),
        ({"nwm_major_version": True}, "nwm_major_version"),
        ({"timeout": 0}, "Radius"),
    ],
)
def test_invalid_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        remote.nearest_nwm_reach_remote(-99.31, 30.07, **kwargs)


def test_rejects_fractional_or_nondecimal_feature_ids(monkeypatch):
    monkeypatch.setattr(
        remote,
        "_fetch_flowlines",
        lambda parameters, *, timeout: {
            "features": [
                _flowline("456.0", 30.07),
                _flowline(456.8, 30.07),
                _flowline("456", 30.071),
            ]
        },
    )
    assert remote.nearest_nwm_reach_remote(-99.31, 30.07)["feature_id"] == 456


def test_missing_version_cannot_be_assumed_compatible(monkeypatch):
    monkeypatch.setattr(
        remote,
        "_fetch_flowlines",
        lambda parameters, *, timeout: {
            "features": [_flowline("456", 30.07, version=None)]
        },
    )
    assert remote.nearest_nwm_reach_remote(-99.31, 30.07) is None
