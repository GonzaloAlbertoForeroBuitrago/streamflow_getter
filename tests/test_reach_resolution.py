"""Tests for operational RouteLink reach resolution."""

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.reach_resolution import (
    build_gage_index,
    resolve_gages,
)


@pytest.fixture
def routelink():
    return xr.Dataset(
        {
            "link": ("feature_id", [3586192, 1122645, 7144704]),
            "gages": (
                "feature_id",
                np.array([b"08165500", b"01646500", b""]),
            ),
        }
    )


def test_build_gage_index(routelink):
    assert build_gage_index(routelink) == {
        "08165500": 3586192,
        "01646500": 1122645,
    }


def test_resolve_gages(routelink):
    index = build_gage_index(routelink)

    assert resolve_gages(["08165500"], index) == {
        "08165500": 3586192
    }


def test_unknown_gage(routelink):
    index = build_gage_index(routelink)

    with pytest.raises(ValueError, match="not found"):
        resolve_gages(["99999999"], index)


def test_duplicate_feature_ids():
    ds = xr.Dataset(
        {
            "link": ("feature_id", [3586192, 3586192]),
            "gages": ("feature_id", [b"08165500", b"01234567"]),
        }
    )

    with pytest.raises(ValueError, match="Duplicate"):
        build_gage_index(ds)


def test_ambiguous_gage():
    ds = xr.Dataset(
        {
            "link": ("feature_id", [3586192, 1122645]),
            "gages": ("feature_id", [b"08165500", b"08165500"]),
        }
    )

    with pytest.raises(ValueError, match="Ambiguous"):
        build_gage_index(ds)



def test_seven_digit_gage_exact_match():
    index = {
        "1234567": 101,
        "01234567": 181,
    }

    assert resolve_gages(["1234567"], index) == {
        "1234567": 101
    }

    assert resolve_gages(["01234567"], index) == {
        "01234567": 181
    }


def test_no_automatic_zero_padding():
    index = {"01234567": 181}

    with pytest.raises(ValueError, match="not found"):
        resolve_gages(["1234567"], index)


def test_nonnumeric_gage_preserved():
    index = {"08AB123": 500}

    assert resolve_gages(["08AB123"], index) == {
        "08AB123": 500
    }




def test_load_gage_index(tmp_path, monkeypatch):
    """Load RouteLink through xarray without a NetCDF backend."""
    from unittest.mock import MagicMock

    from streamflow_getter.reach_resolution import load_gage_index

    path = tmp_path / "routelink.nc"
    path.touch()

    ds = xr.Dataset({
        "link": ("feature_id", [3586192, 1122645]),
        "gages": (
            "feature_id",
            [b"08165500", b"01646500"],
        ),
    })

    context = MagicMock()
    context.__enter__.return_value = ds

    mocked_open = MagicMock(return_value=context)

    monkeypatch.setattr(
        "streamflow_getter.reach_resolution.xr.open_dataset",
        mocked_open,
    )

    result = load_gage_index(path, engine="h5netcdf")

    assert result == {
        "08165500": 3586192,
        "01646500": 1122645,
    }

    mocked_open.assert_called_once_with(
        path,
        engine="h5netcdf",
    )

    context.__exit__.assert_called_once()



def test_load_gage_index_missing_file(tmp_path):
    from streamflow_getter.reach_resolution import load_gage_index

    with pytest.raises(FileNotFoundError, match="not found"):
        load_gage_index(tmp_path / "missing.nc")


def test_reject_noninteger_feature_ids():
    ds = xr.Dataset({
        "link": ("feature_id", [3586192.5, 1122645.0]),
        "gages": ("feature_id", [b"08165500", b"01646500"]),
    })

    with pytest.raises(ValueError, match="integer"):
        build_gage_index(ds)