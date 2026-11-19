"""GEOGLOWS river-reach resolution.

Experimental integration. This module discovers nearby GEOGLOWS river
geometries and reports spatial and hydrographic evidence. Streamflow
retrieval and cross-source basin comparison remain separate concerns.
"""

from __future__ import annotations

import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import shapely
from pyproj import Transformer
from shapely import transform
from shapely.geometry import Point, shape


GEOGLOWS_ARCGIS_QUERY_URL = (
    "https://livefeeds3.arcgis.com/"
    "arcgis/rest/services/GEOGLOWS/"
    "GlobalWaterModel_Medium/"
    "MapServer/0/query"
)

_EARTH_RADIUS_M = 6_335_000.0
_MAX_SEARCH_RADIUS_M = 25_000.0
_PAGE_SIZE = 500


def _coordinate(
    value,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    """Return a validated finite geographic coordinate."""
    if isinstance(value, bool):
        raise ValueError(
            f"{name} must be numeric"
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be numeric"
        ) from exc

    if (
        not math.isfinite(result)
        or not minimum <= result <= maximum
    ):
        raise ValueError(
            f"{name} must be between "
            f"{minimum} and {maximum}"
        )

    return result


def _radius_m(value) -> float:
    """Return a validated positive local-search radius."""
    if isinstance(value, bool):
        raise ValueError(
            "max_distance_m must be positive"
        )

    try:
        radius = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "max_distance_m must be positive"
        ) from exc

    if (
        not math.isfinite(radius)
        or not 0 < radius <= _MAX_SEARCH_RADIUS_M
    ):
        raise ValueError(
            "max_distance_m must be in (0, 25000]"
        )

    return radius


def _request_json(
    url: str,
    *,
    timeout: float,
) -> dict:
    """Retrieve one JSON document from the GEOGLOWS ArcGIS service."""
    if timeout <= 0:
        raise ValueError(
            "timeout must be positive"
        )

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "streamflow-getter",
        },
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise ValueError(
            "GEOGLOWS geometry service returned invalid JSON"
        )

    if "error" in payload:
        raise ValueError(
            "GEOGLOWS geometry service error: "
            f"{payload['error']}"
        )

    return payload


def _search_envelope(
    longitude: float,
    latitude: float,
    radius_m: float,
) -> tuple[float, float, float, float]:
    """Return a conservative lon/lat envelope around a point."""
    delta_lat = math.degrees(
        radius_m / _EARTH_RADIUS_M
    )

    if abs(latitude) + delta_lat >= 90:
        raise ValueError(
            "Search area crosses a pole"
        )

    delta_lon = math.degrees(
        math.asin(
            math.sin(
                math.radians(delta_lat)
            )
            / math.cos(
                math.radians(latitude)
            )
        )
    )

    envelope = (
        longitude - delta_lon,
        latitude - delta_lat,
        longitude + delta_lon,
        latitude + delta_lat,
    )

    west, _, east, _ = envelope

    if west < -180 or east > 180:
        raise ValueError(
            "Antimeridian-crossing searches are not supported"
        )

    return envelope


def _query_parameters(
    longitude: float,
    latitude: float,
    radius_m: float,
) -> dict[str, object]:
    """Build the stable ArcGIS query parameters for one search."""
    west, south, east, north = (
        _search_envelope(
            longitude,
            latitude,
            radius_m,
        )
    )

    return {
        "where": "1=1",
        "geometry": (
            f"{west},{south},{east},{north}"
        ),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "comid,upstreamarea,streamorder"
        ),
        "returnGeometry": "true",
        "orderByFields": "comid",
        "resultRecordCount": _PAGE_SIZE,
        "f": "json",
    }


def _fetch_candidate_features(
    parameters: dict[str, object],
    *,
    timeout: float,
    max_pages: int,
) -> dict[int, dict]:
    """Retrieve and deduplicate ArcGIS features by GEOGLOWS river ID."""
    rows: dict[int, dict] = {}
    offset = 0

    for _ in range(max_pages):
        url = (
            GEOGLOWS_ARCGIS_QUERY_URL
            + "?"
            + urlencode(
                {
                    **parameters,
                    "resultOffset": offset,
                }
            )
        )

        payload = _request_json(
            url,
            timeout=timeout,
        )

        page = payload.get(
            "features",
            [],
        )

        if not isinstance(page, list):
            raise ValueError(
                "GEOGLOWS geometry service returned invalid features"
            )

        previous_count = len(rows)

        for feature in page:
            if not isinstance(feature, dict):
                continue

            attributes = feature.get(
                "attributes",
            )

            if not isinstance(
                attributes,
                dict,
            ):
                continue

            river_id = attributes.get(
                "comid"
            )

            if river_id is None:
                continue

            rows.setdefault(
                int(river_id),
                feature,
            )

        offset += len(page)

        if not payload.get(
            "exceededTransferLimit",
            False,
        ):
            return rows

        if not page or len(rows) == previous_count:
            raise ValueError(
                "GEOGLOWS pagination made no progress"
            )

    raise ValueError(
        "Incomplete GEOGLOWS geometry response"
    )


def _feature_geometry(
    feature: dict,
) -> dict:
    """Convert an ArcGIS polyline feature into GeoJSON geometry."""
    geometry = feature.get(
        "geometry",
        {},
    )

    paths = geometry.get(
        "paths"
    )

    if not isinstance(paths, list):
        raise ValueError(
            "GEOGLOWS feature has invalid geometry"
        )

    coordinates = [
        [
            list(point[:2])
            for point in path
        ]
        for path in paths
    ]

    if (
        not coordinates
        or any(
            len(path) < 2
            for path in coordinates
        )
    ):
        raise ValueError(
            "GEOGLOWS feature has invalid geometry"
        )

    return {
        "type": "MultiLineString",
        "coordinates": coordinates,
    }


def _local_projector(
    longitude: float,
    latitude: float,
):
    """Return a local azimuthal-equidistant projection function."""
    crs = (
        f"+proj=aeqd "
        f"+lat_0={latitude} "
        f"+lon_0={longitude} "
        f"+datum=WGS84 "
        f"+units=m"
    )

    return Transformer.from_crs(
        4326,
        crs,
        always_xy=True,
    ).transform


def _distance_to_geometry_m(
    geometry: dict,
    *,
    project,
) -> float:
    """Return point-to-line distance in the local metric CRS."""
    line = shape(
        geometry
    )

    if (
        line.is_empty
        or not line.is_valid
    ):
        raise ValueError(
            "Invalid GEOGLOWS geometry"
        )

    metric = transform(
        line,
        lambda xy: np.column_stack(
            project(
                xy[:, 0],
                xy[:, 1],
                errcheck=True,
            )
        ),
    )

    distance = float(
        shapely.distance(
            metric,
            Point(0, 0),
        )
    )

    if not math.isfinite(
        distance
    ):
        raise ValueError(
            "Invalid GEOGLOWS distance"
        )

    return distance


def _upstream_area_km2(
    value,
) -> float | None:
    """Convert optional GEOGLOWS upstream area from m² to km²."""
    if value in (
        None,
        "",
    ):
        return None

    try:
        area = (
            float(value)
            / 1_000_000.0
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Invalid GEOGLOWS upstream area"
        ) from exc

    if (
        not math.isfinite(area)
        or area <= 0
    ):
        return None

    return area


def _stream_order(
    value,
) -> int | None:
    """Return optional positive stream order."""
    if value in (
        None,
        "",
    ):
        return None

    try:
        order = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Invalid GEOGLOWS stream order"
        ) from exc

    return (
        order
        if order > 0
        else None
    )


def _candidate_record(
    river_id: int,
    feature: dict,
    *,
    project,
    radius_m: float,
) -> dict | None:
    """Normalize one ArcGIS feature into candidate evidence."""
    attributes = feature.get(
        "attributes",
        {},
    )

    if not isinstance(
        attributes,
        dict,
    ):
        raise ValueError(
            "GEOGLOWS feature has invalid attributes"
        )

    geometry = _feature_geometry(
        feature
    )

    try:
        distance_m = (
            _distance_to_geometry_m(
                geometry,
                project=project,
            )
        )
    except ValueError as exc:
        raise ValueError(
            "Invalid GEOGLOWS geometry "
            f"for river {river_id}"
        ) from exc

    if distance_m > radius_m:
        return None

    return {
        "source": "geoglows",
        "river_id": river_id,
        "distance_m": distance_m,
        "upstream_area_km2": (
            _upstream_area_km2(
                attributes.get(
                    "upstreamarea"
                )
            )
        ),
        "stream_order": (
            _stream_order(
                attributes.get(
                    "streamorder"
                )
            )
        ),
        "geometry": geometry,
    }


def find_geoglows_reach_candidates(
    longitude,
    latitude,
    *,
    max_distance_m: float = 1000.0,
    timeout: float = 60.0,
    max_pages: int = 4,
) -> list[dict]:
    """Return nearby GEOGLOWS candidates sorted by metric distance.

    Candidate metadata are supporting evidence only. No drainage-area
    threshold or hydrologic-equivalence decision is applied here.
    """
    lon = _coordinate(
        longitude,
        name="longitude",
        minimum=-180,
        maximum=180,
    )

    lat = _coordinate(
        latitude,
        name="latitude",
        minimum=-90,
        maximum=90,
    )

    radius = _radius_m(
        max_distance_m
    )

    if (
        isinstance(max_pages, bool)
        or not isinstance(max_pages, int)
        or max_pages <= 0
    ):
        raise ValueError(
            "max_pages must be a positive integer"
        )

    features = _fetch_candidate_features(
        _query_parameters(
            lon,
            lat,
            radius,
        ),
        timeout=timeout,
        max_pages=max_pages,
    )

    if not features:
        return []

    project = _local_projector(
        lon,
        lat,
    )

    candidates = [
        candidate
        for river_id, feature
        in features.items()
        if (
            candidate := _candidate_record(
                river_id,
                feature,
                project=project,
                radius_m=radius,
            )
        )
        is not None
    ]

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate["distance_m"],
            candidate["river_id"],
        ),
    )


def nearest_geoglows_reach(
    longitude,
    latitude,
    *,
    max_distance_m: float = 1000.0,
    timeout: float = 60.0,
) -> dict | None:
    """Return the nearest candidate, or None when no reach is nearby."""
    candidates = (
        find_geoglows_reach_candidates(
            longitude,
            latitude,
            max_distance_m=max_distance_m,
            timeout=timeout,
        )
    )

    return (
        candidates[0]
        if candidates
        else None
    )
