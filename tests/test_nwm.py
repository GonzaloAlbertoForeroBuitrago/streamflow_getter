import numpy as np
import pandas as pd
import pytest
import xarray as xr

from streamflow_getter import nwm


@pytest.fixture
def ds():
    time = pd.date_range("2020-01-01", periods=48, freq="h")
    ids = [101, 179, 181]
    flow = np.arange(48 * 3, dtype=float).reshape(48, 3)
    return xr.Dataset(
        {"streamflow": (("time", "feature_id"), flow)},
        coords={
            "time": time,
            "feature_id": ids,
            "gage_id": ("feature_id", np.array([b"", b"08165500", b"08166000"])),
        },
    )


def test_fetch_selects_reaches_and_dates(ds):
    df = nwm.fetch([179], "2020-01-01", "2020-01-01 23:00", ds=ds)
    assert list(df.columns) == ["time", "feature_id", "streamflow"]
    assert len(df) == 24
    assert set(df.feature_id) == {179}


def test_fetch_unknown_reach(ds):
    with pytest.raises(ValueError, match="999"):
        nwm.fetch([999], "2020-01-01", "2020-01-02", ds=ds)


def test_gage_lookup_preserves_exact_ids(ds):
    assert nwm.gages_to_reaches(["08165500", "08166000"], ds) == {
        "08165500": 179,
        "08166000": 181,
    }


def test_gage_lookup_unknown(ds):
    with pytest.raises(ValueError, match="99999999"):
        nwm.gages_to_reaches(["99999999"], ds)


def test_gage_lookup_does_not_add_zeros(ds):
    """Shorter IDs must not match by adding leading zeros."""
    with pytest.raises(ValueError, match="gage_id not in"):
        nwm.gages_to_reaches(["8165500"], ds)
