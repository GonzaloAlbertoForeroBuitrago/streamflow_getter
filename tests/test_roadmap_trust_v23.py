"""Data-availability diagnostics do not invent cross-network skill scores."""

from __future__ import annotations

import pandas as pd
import pytest

from streamflow_getter.roadmap_diagnostics import summarize_exact_utc_overlap


def test_exact_usgs_model_pairs_no_resampling():
    table = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(
                [
                    "2025-07-04T06:00:00Z",
                    "2025-07-04T06:15:00Z",
                    "2025-07-04T07:00:00Z",
                ]
            ),
            "usgs_streamflow_m3s": [1.0, 2.0, None],
            "analysis_assim_streamflow_m3s": [None, 4.0, 5.0],
            "geoglows_streamflow_m3s": [2.0, None, 3.0],
        }
    )
    result = summarize_exact_utc_overlap(
        {
            "table": table,
            "metadata": {"nwm": {"gage_crosswalk_verified_for_version": False}},
        }
    )
    assert result["usgs_samples"] == 2
    assert (
        result["model_sources"]["analysis_assim"]["paired_with_usgs_at_exact_utc"] == 1
    )
    assert result["model_sources"]["geoglows"]["paired_with_usgs_at_exact_utc"] == 1
    assert result["skill_evaluated"] is False
    assert result["crosswalk_verified_for_nwm"] is False


def test_duplicate_valid_times_cannot_be_presented_as_exact_pairs():
    table = pd.DataFrame(
        {
            "valid_time": pd.to_datetime(
                ["2025-07-04T06:00:00Z", "2025-07-04T06:00:00Z"]
            ),
            "usgs_streamflow_m3s": [1.0, 1.0],
        }
    )
    with pytest.raises(ValueError, match="unique valid timestamps"):
        summarize_exact_utc_overlap(
            {
                "table": table,
                "metadata": {"nwm": {"gage_crosswalk_verified_for_version": False}},
            }
        )


def test_spatial_diagnostic_matches_fixed_map_identifier_and_geometry(monkeypatch):
    from types import ModuleType, SimpleNamespace
    import sys

    import geopandas as gpd
    import pyogrio
    from shapely.geometry import LineString

    from streamflow_getter import roadmap_diagnostics as diag

    spatial = ModuleType("streamflow_getter.spatial_resolution")
    spatial.validate_hydrofabric_crs = lambda *_a: None
    spatial.load_nearby_reaches = lambda *_a, **_k: object()
    spatial.nearest_reaches = lambda *_a, **_k: [
        {"feature_id": 3586192, "distance_m": 98.7}
    ]
    monkeypatch.setitem(sys.modules, spatial.__name__, spatial)

    reaches = gpd.GeoDataFrame(
        {"ID": [3586192]},
        geometry=[LineString([(-99.3219, 30.069), (-99.3217, 30.071)])],
        crs="EPSG:4269",
    )
    monkeypatch.setattr(pyogrio, "read_dataframe", lambda *_a, **_k: reaches)
    study = SimpleNamespace(
        hydrofabric="fake.gdb",
        gages={"08165500": 3586192},
        provenance={"network_version": "3.1"},
        version="3.0",
        crosswalk_compatible=False,
    )
    result = {
        "metadata": {
            "point_epsg4326": {"longitude": -99.3217, "latitude": 30.0699},
            "ids": {"usgs": "08165500", "nwm": 3586192, "geoglows": 999},
            "geoglows": {"distance_m": 106.79},
            "drainage_area_comparison": {"message": "+5.7%"},
        },
        "nwm_geojson": reaches.to_crs("EPSG:4326").__geo_interface__,
        "geoglows_geometry": {
            "type": "LineString",
            "coordinates": [[-99.322, 30.069], [-99.322, 30.071]],
        },
    }
    report = diag.diagnose_reaches(study, result, "08165500", 3000)
    assert report["routelink_matches_map_id"] is True
    assert report["map_usgs_id"] == "08165500"
    assert report["map_geoglows_id"] == 999
    assert report["nwm_reach_count"] == 1
    assert report["hydrofabric_vs_map_geometry_m"] == pytest.approx(0, abs=0.01)
    assert report["crosswalk_compatible"] is False


def test_click_experiment_uses_same_nearest_hydrofabric_id_as_map(monkeypatch):
    from types import ModuleType, SimpleNamespace
    import sys

    from streamflow_getter.roadmap_diagnostics import diagnose_click_selection

    spatial = ModuleType("streamflow_getter.spatial_resolution")
    spatial.load_nearby_reaches = lambda *_a, **_k: object()
    spatial.nearest_reaches = lambda *_a, **_k: [
        {"feature_id": 888, "distance_m": 110.0}
    ]
    monkeypatch.setitem(sys.modules, spatial.__name__, spatial)
    study = SimpleNamespace(
        hydrofabric="nwm.gdb",
        radius_m=3000,
        gages={"08165500": 3586192},
        crosswalk_compatible=False,
    )
    result = {
        "metadata": {
            "point_epsg4326": {"longitude": -99.31, "latitude": 30.08},
            "ids": {"usgs": None, "nwm": 888, "geoglows": 555},
        }
    }
    audit = diagnose_click_selection(study, result)
    assert audit["map_nwm_id"] == 888
    assert audit["backend_nearest_nwm_id"] == 888
    assert audit["matches_backend_nearest"] is True
    assert audit["matches_routelink_when_usgs"] is None
    assert audit["map_geoglows_id"] == 555
