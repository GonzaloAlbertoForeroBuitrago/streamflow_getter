"""Resolve NWM flowline IDs from NOAA's public CONUS reference service.

Spatial proximity is evidence, not proof of hydrologic equivalence.
"""

from __future__ import annotations

import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pyproj import Geod, Transformer
from shapely import transform
from shapely.geometry import Point, shape

from streamflow_getter.spatial_resolution import validate_feature_id

_NWM_FLOWLINES_URL = (
    "https://maps.water.noaa.gov/server/rest/services/"
    "reference/static_nwm_flowlines/FeatureServer/0/query"
)
_MAX_FEATURES = 2000
_MAX_RESPONSE_BYTES = 10_000_000


def _fetch_flowlines(parameters: dict, *, timeout: float) -> dict:
    url = f"{_NWM_FLOWLINES_URL}?{urlencode(parameters)}"
    request = Request(url, headers={"Accept": "application/geo+json, application/json"})
    with urlopen(request, timeout=timeout) as response:
        content = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(content) > _MAX_RESPONSE_BYTES:
        raise ValueError("NOAA NWM flowline response exceeds the maximum size")
    payload = json.loads(content)
    if not isinstance(payload, dict) or "error" in payload:
        raise ValueError(f"NOAA NWM flowline service error: {payload!r}")
    if not isinstance(payload.get("features"), list):
        raise ValueError("Unexpected NOAA NWM flowline response")
    return payload


def _parse_feature_id(value) -> int:
    if isinstance(value, str):
        if not value.isascii() or not value.isdecimal():
            raise ValueError("Invalid NOAA NWM feature ID")
        return validate_feature_id(int(value))
    return validate_feature_id(value)


def _validate_remote_request(longitude, latitude, radius, version, timeout):
    values = (longitude, latitude, radius, timeout)
    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in values
    ):
        raise ValueError("Coordinates, radius, and timeout must be finite numbers")
    if not (-180 <= longitude <= 180 and -90 < latitude < 90):
        raise ValueError("Invalid longitude or latitude")
    if not (0 < radius <= 25_000) or timeout <= 0:
        raise ValueError("Radius must be in (0, 25000] meters and timeout positive")
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise ValueError("nwm_major_version must be a positive integer")


def _query_parameters(longitude, latitude, radius):
    geod = Geod(ellps="WGS84")
    bounds = [
        geod.fwd(longitude, latitude, bearing, radius)[:2]
        for bearing in (0, 90, 180, 270)
    ]
    west, east = min(x for x, _ in bounds), max(x for x, _ in bounds)
    south, north = min(y for _, y in bounds), max(y for _, y in bounds)

    if west < -180 or east > 180 or east - west > 180:
        raise ValueError("Antimeridian-crossing queries are not supported")

    return {
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "feature_id,nwm_vers,name",
        "returnGeometry": "true",
        "resultRecordCount": _MAX_FEATURES,
        "f": "geojson",
    }


def _candidate_from_feature(feature, *, version, radius, transformer):
    if not isinstance(feature, dict):
        return None

    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        return None

    try:
        feature_id = _parse_feature_id(props["feature_id"])
        nwm_version = float(props["nwm_vers"])
    except (KeyError, ValueError, TypeError, OverflowError):
        return None

    if not math.isfinite(nwm_version) or not (version <= nwm_version < version + 1):
        return None

    geometry_json = feature.get("geometry")
    if not geometry_json:
        return None

    try:
        geometry = shape(geometry_json)
        if geometry.is_empty or not geometry.is_valid:
            return None
        if geometry.geom_type not in {"LineString", "MultiLineString"}:
            return None

        metric = transform(
            geometry,
            transformer.transform,
            interleaved=False,
        )
        distance_m = float(metric.distance(Point(0, 0)))
    except (ValueError, TypeError):
        return None

    if not math.isfinite(distance_m) or distance_m > radius:
        return None

    return {
        "feature_id": feature_id,
        "distance_m": distance_m,
        "nwm_version": nwm_version,
        "name": props.get("name"),
        "geometry": geometry_json,
    }


def nearest_nwm_reach_remote(
    longitude: float,
    latitude: float,
    *,
    max_distance_m: float = 1000.0,
    nwm_major_version: int = 3,
    timeout: float = 30.0,
) -> dict | None:
    """Return the nearest NOAA NWM reach, or None when none is nearby.

    No local Hydrofabric or USGS identifier is required.
    """
    _validate_remote_request(
        longitude, latitude, max_distance_m, nwm_major_version, timeout
    )

    parameters = _query_parameters(longitude, latitude, max_distance_m)
    payload = _fetch_flowlines(parameters, timeout=timeout)
    features = payload["features"]

    if payload.get("exceededTransferLimit") or len(features) >= _MAX_FEATURES:
        raise ValueError("NOAA flowline result limit reached; reduce max_distance_m")

    crs = f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} +datum=WGS84 +units=m"
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    candidates = [
        candidate
        for feature in features
        if (
            candidate := _candidate_from_feature(
                feature,
                version=nwm_major_version,
                radius=max_distance_m,
                transformer=transformer,
            )
        )
        is not None
    ]

    return min(
        candidates,
        key=lambda item: (item["distance_m"], item["feature_id"]),
        default=None,
    )
