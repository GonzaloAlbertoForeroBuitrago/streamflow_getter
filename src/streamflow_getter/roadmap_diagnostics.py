"""Small live demonstrations of James Halgren's operational NWM roadmap.

These functions call the existing backend readers and spatial selection APIs.
They never create synthetic hydrology, alter model data, or save research
results unless explicitly requested. Network access is required for E1/E3.
"""

from __future__ import annotations

from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import perf_counter

import pandas as pd


# One source time is compared for each method; this is a *live* I/O check,
# not a claim about the speed of full multi-day forecasts.
def _sample_config(reference_utc: str, product: str):
    from streamflow_getter.operational_nwm import ForecastConfig

    timestamp = pd.Timestamp(reference_utc)
    if timestamp.tzinfo is None:
        raise ValueError("reference_utc must include an explicit UTC offset")
    timestamp = timestamp.tz_convert("UTC")
    if timestamp != timestamp.floor("h"):
        raise ValueError("reference_utc must be at an exact UTC hour")
    return ForecastConfig(
        date=f"{timestamp:%Y-%m-%d}",
        cycle=timestamp.hour,
        product=product,
        domain="conus",
    )


def _sample_read(reader, config, feature_id, hour, cache_dir=None) -> dict:
    """Measure process RSS while the existing reader runs (approximate peak)."""
    import psutil

    process = psutil.Process()
    baseline = process.memory_info().rss
    peak = [baseline]
    done = Event()

    def observe():
        while not done.wait(0.01):
            try:
                peak[0] = max(peak[0], process.memory_info().rss)
            except psutil.Error:
                break

    sampler = Thread(target=observe, daemon=True)
    sampler.start()
    started = perf_counter()
    response = None
    error = None
    try:
        kwargs = {"cache_dir": cache_dir} if cache_dir is not None else {}
        response = reader(config, hour, [int(feature_id)], **kwargs)
    except (
        Exception
    ) as exc:  # Network failure is a measured outcome, not a test fabrication.
        error = f"{type(exc).__name__}: {exc}"
    finally:
        seconds = perf_counter() - started
        done.set()
        sampler.join(timeout=2.0)
        peak[0] = max(peak[0], process.memory_info().rss)

    value = None
    method = None
    if response is not None:
        flows = response["streamflow_m3s"]
        value = float(flows.get(int(feature_id), flows.get(str(feature_id))))
        method = response.get("method")
    return {
        "ok": error is None,
        "error": error,
        "method": method,
        "streamflow_m3s": value,
        "seconds": round(seconds, 3),
        "rss_start_mb": round(baseline / 2**20, 2),
        "rss_peak_mb": round(peak[0] / 2**20, 2),
        "rss_increment_mb": round(max(0, peak[0] - baseline) / 2**20, 2),
    }


def benchmark_access(
    reference_utc: str,
    feature_id: int,
    *,
    lead_hour: int = 1,
    product: str = "short_range",
    cache_dir=None,
) -> dict:
    """Read the same Texas reach and forecast lead via Kerchunk and native.

    RSS is approximate sampled process RSS above the pre-call baseline, not
    isolated reader allocation. Compare both on the same machine and note that
    prior cache warming and network variability affect timing.
    """
    from streamflow_getter.operational_nwm import (
        read_kerchunk_forecast,
        read_native_forecast,
    )

    config = _sample_config(reference_utc, product)
    config.forecast_hours(lead_hour, lead_hour)  # Validate lead before I/O.
    kerchunk = _sample_read(
        read_kerchunk_forecast,
        config,
        feature_id,
        lead_hour,
        cache_dir=cache_dir,
    )
    native = _sample_read(read_native_forecast, config, feature_id, lead_hour)
    comparable = kerchunk["ok"] and native["ok"]
    absolute_difference = (
        abs(kerchunk["streamflow_m3s"] - native["streamflow_m3s"])
        if comparable
        else None
    )
    return {
        "source": "live NOAA/CIROH operational NWM; one reach and one lead",
        "reference_utc": reference_utc,
        "product": product,
        "lead_hour": lead_hour,
        "feature_id": int(feature_id),
        "kerchunk": kerchunk,
        "native": native,
        "comparable": comparable,
        "absolute_difference_m3s": absolute_difference,
        "equal_within_tolerance": (
            isclose(
                kerchunk["streamflow_m3s"],
                native["streamflow_m3s"],
                rel_tol=1e-6,
                abs_tol=1e-6,
            )
            if comparable
            else None
        ),
    }


def benchmark_cache(
    reference_utc: str,
    feature_id: int,
    *,
    lead_hour: int = 1,
    product: str = "short_range",
    cache_dir,
) -> dict:
    """Two live requests through the *existing* Kerchunk→native coordinator.

    The cache stores references, not automatically the full model data. A
    second request is not guaranteed faster; fallback method is recorded.
    """
    from streamflow_getter.operational_nwm import fetch_operational_forecast

    config = _sample_config(reference_utc, product)
    config.forecast_hours(lead_hour, lead_hour)
    results = []
    for iteration in (1, 2):
        started = perf_counter()
        try:
            response = fetch_operational_forecast(
                config, lead_hour, [int(feature_id)], cache_dir=cache_dir
            )
            value = response["streamflow_m3s"].get(
                int(feature_id), response["streamflow_m3s"].get(str(feature_id))
            )
            entry = {
                "iteration": iteration,
                "ok": True,
                "method": response.get("method"),
                "streamflow_m3s": float(value),
                "error": None,
            }
        except Exception as exc:
            entry = {
                "iteration": iteration,
                "ok": False,
                "method": None,
                "streamflow_m3s": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        entry["seconds"] = round(perf_counter() - started, 3)
        results.append(entry)
        if not entry["ok"]:
            break
    return {
        "cache_dir": str(cache_dir),
        "requests": results,
        "equal_within_tolerance": (
            isclose(
                results[0]["streamflow_m3s"],
                results[1]["streamflow_m3s"],
                rel_tol=1e-6,
                abs_tol=1e-6,
            )
            if len(results) == 2 and all(r["ok"] for r in results)
            else None
        ),
    }


def _geoglows_in_albers(value):
    """Interpret WGS84 GeoJSON and project it to CONUS Albers meters."""
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely import transform, union_all

    if value is None:
        return None
    value = getattr(value, "__geo_interface__", value)
    kind = value.get("type")
    if kind == "Feature":
        value = value["geometry"]
    if kind == "FeatureCollection":
        geometry = union_all(
            [shape(feature["geometry"]) for feature in value["features"]]
        )
    else:
        geometry = shape(value)
    if geometry.is_empty:
        return None
    west, south, east, north = geometry.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("GEOGLOWS GeoJSON not in expected EPSG:4326 lon/lat")
    to_albers = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    return transform(geometry, to_albers.transform, interleaved=False)


def _optional_reach_geometry(record: dict, nwm_line, station_point):
    """Measure optional map lines in EPSG:5070 without aborting the audit."""
    from shapely.errors import GEOSException

    geo_albers = None
    warning = None
    try:
        geo_albers = _geoglows_in_albers(record.get("geoglows_geometry"))
    except (GEOSException, ValueError, TypeError) as exc:
        warning = f"GEOGLOWS geometry: {type(exc).__name__}: {exc}"

    map_separation = None
    if nwm_line is not None and record.get("nwm_geojson") is not None:
        try:
            map_geometry = _geoglows_in_albers(record["nwm_geojson"])
            if map_geometry is not None:
                map_separation = nwm_line.distance(map_geometry)
        except (GEOSException, ValueError, TypeError) as exc:
            warning = f"NWM map geometry: {type(exc).__name__}: {exc}"

    return (
        station_point.distance(geo_albers) if geo_albers is not None else None,
        nwm_line.distance(geo_albers)
        if nwm_line is not None and geo_albers is not None
        else None,
        map_separation,
        warning,
    )


def diagnose_reaches(study, record: dict, gage_id: str, radius_m: float) -> dict:
    """Demonstrate RouteLink ID lookup and three EPSG:5070 distances.

    USGS WGS84 EPSG:4326 -> EPSG:5070, NWM NAD83 EPSG:4269 -> EPSG:5070,
    GEOGLOWS geographic GeoJSON EPSG:4326 -> EPSG:5070. Projected planar
    distances are approximate; they are not hydrologic routing distances.
    """
    import pyogrio
    from pyproj import Transformer
    from shapely.geometry import Point

    from streamflow_getter.spatial_resolution import (
        load_nearby_reaches,
        nearest_reaches,
        validate_hydrofabric_crs,
    )

    started = perf_counter()
    point = record["metadata"]["point_epsg4326"]
    longitude, latitude = float(point["longitude"]), float(point["latitude"])
    wgs_to_albers = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    x, y = wgs_to_albers.transform(longitude, latitude)
    station_point = Point(x, y)
    validate_hydrofabric_crs(study.hydrofabric)
    feature_id = study.gages.get(gage_id)  # Exact crosswalk, not nearest line.
    nwm_line = None
    nwm_distance = None
    selected_count = 0
    if feature_id is not None:
        selected = pyogrio.read_dataframe(
            study.hydrofabric,
            layer="nwm_reaches_conus",
            where=f"ID = {int(feature_id)}",
            columns=["ID"],
        )
        selected_count = len(selected)
        if selected_count == 1:
            nwm_line = selected.to_crs("EPSG:5070").geometry.iloc[0]
            nwm_distance = station_point.distance(nwm_line)

    nearby_frame = load_nearby_reaches(
        study.hydrofabric, longitude, latitude, max_distance_m=radius_m
    )
    nearby = nearest_reaches(
        nearby_frame, longitude, latitude, max_distance_m=radius_m, limit=3
    )
    nearby = [
        {"feature_id": item["feature_id"], "distance_m": item["distance_m"]}
        for item in nearby
    ]

    geo_distance, lines_distance, map_line_distance, geometry_warning = (
        _optional_reach_geometry(record, nwm_line, station_point)
    )
    displayed = record["metadata"].get("ids", {})
    map_id = displayed.get("nwm")
    same_id = (
        int(feature_id) == int(map_id)
        if feature_id is not None and map_id is not None
        else None
    )
    return {
        "gage_id": gage_id,
        "feature_id": feature_id,
        "map_nwm_id": map_id,
        "map_usgs_id": displayed.get("usgs"),
        "map_geoglows_id": displayed.get("geoglows"),
        "routelink_matches_map_id": same_id,
        "hydrofabric_vs_map_geometry_m": map_line_distance,
        "geometry_warning": geometry_warning,
        "routelink_network_version": study.provenance["network_version"],
        "nwm_version": study.version,
        "crosswalk_compatible": study.crosswalk_compatible,
        "station_epsg4326_lonlat": (longitude, latitude),
        "station_epsg5070_xy_m": (x, y),
        "nwm_reach_count": selected_count,
        "usgs_to_nwm_m": nwm_distance,
        "usgs_to_geoglows_m": geo_distance,
        "nwm_to_geoglows_m": lines_distance,
        "geoglows_service_distance_m": record["metadata"]["geoglows"]["distance_m"],
        "nearby": nearby,
        "area": record["metadata"]["drainage_area_comparison"]["message"],
        "seconds": round(perf_counter() - started, 3),
    }


def benchmark_parquet(record: dict, gage_id: str) -> dict:
    """Verify lossless Parquet round-trip for the real aligned Texas dataframe."""
    from streamflow_getter.output import write_timeseries

    with TemporaryDirectory(prefix="streamflow-getter-roadmap-") as tmp:
        dest = Path(tmp) / f"{gage_id}.parquet"
        started = perf_counter()
        written = write_timeseries(record["table"], dest, output_format="parquet")
        write_seconds = perf_counter() - started
        started = perf_counter()
        reloaded = pd.read_parquet(written)
        read_seconds = perf_counter() - started
        pd.testing.assert_frame_equal(record["table"], reloaded)
        return {
            "rows": len(reloaded),
            "columns": len(reloaded.columns),
            "bytes": dest.stat().st_size,
            "write_seconds": round(write_seconds, 3),
            "read_seconds": round(read_seconds, 3),
            "source_columns": {
                column: int(reloaded[column].notna().sum())
                for column in reloaded
                if column.endswith("_streamflow_m3s")
            },
            "equal": True,
            "saved_permanently": False,
        }


def summarize_exact_utc_overlap(record: dict) -> dict:
    """Count timestamp-exact USGS/model pairs, without interpolation or scoring.

    Before the network crosswalk has been validated, pairs describe data
    availability only—not forecast accuracy or hydrologic equivalence.
    """
    table = record["table"]
    if "valid_time" not in table:
        raise ValueError("Comparison requires valid_time (UTC)")
    timestamps = pd.to_datetime(table["valid_time"], utc=True, errors="raise")
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError("Exact UTC comparison requires unique valid timestamps")
    usgs_col = "usgs_streamflow_m3s"
    usgs_mask = (
        table[usgs_col].notna()
        if usgs_col in table
        else pd.Series(False, index=table.index)
    )
    models = {}
    for column in table:
        if column == usgs_col or not column.endswith("_streamflow_m3s"):
            continue
        populated = table[column].notna()
        models[column.removesuffix("_streamflow_m3s")] = {
            "model_samples": int(populated.sum()),
            "paired_with_usgs_at_exact_utc": int((populated & usgs_mask).sum()),
            "interpolated": False,
        }
    return {
        "time_basis": "unique_valid_time_utc",
        "usgs_samples": int(usgs_mask.sum()),
        "model_sources": models,
        "crosswalk_verified_for_nwm": bool(
            record["metadata"]["nwm"]["gage_crosswalk_verified_for_version"]
        ),
        "skill_evaluated": False,
    }


def diagnose_click_selection(study, record: dict) -> dict:
    """Independently repeat D2's nearest-Hydrofabric lookup for one click.

    This is an acceptance check of *which ID* was displayed, not an assertion
    that the closest line is hydrologically equivalent to a gage or GEOGLOWS.
    GEOGLOWS data is not re-fetched: its ID is preserved in the same result.
    """
    from streamflow_getter.spatial_resolution import (
        load_nearby_reaches,
        nearest_reaches,
    )

    point = record["metadata"]["point_epsg4326"]
    lon, lat = float(point["longitude"]), float(point["latitude"])
    reaches = load_nearby_reaches(
        study.hydrofabric, lon, lat, max_distance_m=study.radius_m
    )
    nearest = nearest_reaches(reaches, lon, lat, max_distance_m=study.radius_m, limit=1)
    expected = int(nearest[0]["feature_id"]) if nearest else None
    displayed = record["metadata"]["ids"]
    actual = displayed["nwm"]
    gage = displayed["usgs"]
    routelink_id = study.gages.get(gage) if gage else None
    return {
        "point_epsg4326": (lon, lat),
        "map_nwm_id": actual,
        "backend_nearest_nwm_id": expected,
        "matches_backend_nearest": actual == expected,
        "map_usgs_id": gage,
        "routelink_nwm_id": routelink_id,
        "matches_routelink_when_usgs": (
            actual == routelink_id if gage is not None else None
        ),
        "crosswalk_compatible": study.crosswalk_compatible,
        "map_geoglows_id": displayed["geoglows"],
        "geoglows_resolution": "independent network; no official NWM ID join",
    }
