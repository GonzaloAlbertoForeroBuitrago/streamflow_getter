"""USGS streamflow and monitoring-location access.

Source-specific request, parsing, unit, and timestamp handling lives here
so notebooks, CLIs, and future web interfaces can use the same backend.
"""

from __future__ import annotations

import json
import math
import os
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

import pandas as pd


USGS_OGC_BASE_URL = "https://api.waterdata.usgs.gov/ogcapi/v1"
DISCHARGE_PARAMETER_CODE = "00060"

CFS_TO_M3S = 0.028316846592
SQMI_TO_KM2 = 2.589988110336

_DISCHARGE_UNIT_FACTORS = {
    "ft^3/s": CFS_TO_M3S,
    "ft3/s": CFS_TO_M3S,
    "cfs": CFS_TO_M3S,
    "m^3/s": 1.0,
    "m3/s": 1.0,
    "m³/s": 1.0,
}

USGS_STREAMFLOW_COLUMNS = [
    "source",
    "series",
    "source_id",
    "usgs_gage_id",
    "valid_time",
    "interval_start",
    "interval_end",
    "time_support",
    "aggregation",
    "streamflow_m3s",
    "unit",
    "method",
    "parameter_code",
    "statistic_id",
    "time_series_id",
    "approval_status",
    "qualifier",
    "native_value",
    "native_unit",
]


def _normalize_gage_id(gage_id: str) -> str:
    """Validate and preserve a numeric USGS gage identifier."""
    if not isinstance(gage_id, str):
        raise TypeError("USGS gage ID must be a string")

    gage = gage_id.strip()

    if not gage or not gage.isascii() or not gage.isdecimal():
        raise ValueError(
            "USGS gage ID must contain only ASCII digits"
        )

    return gage


def _location_id(gage_id: str) -> str:
    return f"USGS-{_normalize_gage_id(gage_id)}"


def _utc_timestamp(value, *, name: str) -> pd.Timestamp:
    """Return a timezone-aware UTC timestamp."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{name} must be a valid datetime"
        ) from exc

    if timestamp.tzinfo is None:
        raise ValueError(
            f"{name} must include an explicit timezone"
        )

    return timestamp.tz_convert("UTC")


def _resolved_api_key(api_key: str | None) -> str | None:
    """Prefer an explicit key, otherwise use USGS_API_KEY."""
    key = (
        api_key
        if api_key is not None
        else os.environ.get("USGS_API_KEY")
    )

    if key is None:
        return None

    key = key.strip()
    return key or None


def _collection_url(
    collection: str,
    parameters: dict[str, object],
) -> str:
    """Build a credential-free USGS OGC collection URL."""
    query = urlencode(
        {
            key: value
            for key, value in parameters.items()
            if value is not None
        }
    )

    return (
        f"{USGS_OGC_BASE_URL}/collections/"
        f"{collection}/items?{query}"
    )


def _request_json(
    url: str,
    *,
    timeout: float,
    api_key: str | None,
) -> dict:
    """Retrieve one USGS JSON document."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    headers = {
        "Accept": "application/geo+json, application/json",
        "User-Agent": "streamflow-getter",
    }

    key = _resolved_api_key(api_key)

    if key is not None:
        # Keep credentials out of query strings and logs.
        headers["X-Api-Key"] = key

    request = Request(
        url,
        headers=headers,
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise ValueError(
            "USGS API returned an unexpected JSON document"
        )

    return payload


def _next_page_url(
    payload: dict,
    *,
    current_url: str,
    expected_host: str,
) -> str | None:
    """Return a validated OGC next-page URL."""
    links = payload.get("links", [])

    if not isinstance(links, list):
        raise ValueError(
            "USGS API returned invalid pagination metadata"
        )

    for link in links:
        if not isinstance(link, dict):
            continue

        if link.get("rel") != "next" or not link.get("href"):
            continue

        next_url = urljoin(
            current_url,
            str(link["href"]),
        )

        if urlsplit(next_url).netloc != expected_host:
            raise ValueError(
                "USGS pagination redirected to an unexpected host"
            )

        return next_url

    return None


def _fetch_features(
    url: str,
    *,
    timeout: float,
    api_key: str | None,
    max_pages: int = 100,
) -> list[dict]:
    """Retrieve all pages in one USGS OGC FeatureCollection."""
    if max_pages <= 0:
        raise ValueError("max_pages must be positive")

    expected_host = urlsplit(url).netloc
    current_url: str | None = url
    seen_urls: set[str] = set()
    features: list[dict] = []

    for _ in range(max_pages):
        if current_url is None:
            return features

        if current_url in seen_urls:
            raise ValueError(
                "USGS pagination repeated the same URL"
            )

        seen_urls.add(current_url)

        payload = _request_json(
            current_url,
            timeout=timeout,
            api_key=api_key,
        )

        page = payload.get("features", [])

        if not isinstance(page, list):
            raise ValueError(
                "USGS API returned invalid features"
            )

        features.extend(
            feature
            for feature in page
            if isinstance(feature, dict)
        )

        current_url = _next_page_url(
            payload,
            current_url=current_url,
            expected_host=expected_host,
        )

    raise ValueError(
        "USGS pagination exceeded max_pages"
    )


def _optional_float(
    value,
    *,
    name: str,
) -> float | None:
    """Return a finite float or None."""
    if value in (None, ""):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid USGS {name}: {value!r}"
        ) from exc

    if not math.isfinite(number):
        raise ValueError(
            f"Invalid USGS {name}: {value!r}"
        )

    return number


def fetch_usgs_monitoring_location(
    gage_id: str,
    *,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> dict:
    """Return USGS station coordinates and basin metadata.

    USGS drainage-area fields are provided in square miles. This adapter
    preserves those native values and also exposes explicit km² values for
    later cross-source basin matching.
    """
    gage = _normalize_gage_id(gage_id)
    location_id = _location_id(gage)

    url = _collection_url(
        "monitoring-locations",
        {
            "f": "json",
            "limit": 2,
            "id": location_id,
        },
    )

    features = _fetch_features(
        url,
        timeout=timeout,
        api_key=api_key,
        max_pages=2,
    )

    matches = []

    for feature in features:
        properties = feature.get("properties", {})

        if not isinstance(properties, dict):
            continue

        if (
            feature.get("id") == location_id
            or properties.get("id") == location_id
            or properties.get("monitoring_location_id")
            == location_id
        ):
            matches.append(feature)

    if not matches:
        raise ValueError(
            f"USGS monitoring location not found: {gage}"
        )

    if len(matches) != 1:
        raise ValueError(
            "USGS monitoring-location query "
            f"was ambiguous for {gage}"
        )

    feature = matches[0]
    properties = feature.get("properties", {})
    geometry = feature.get("geometry")

    if (
        not isinstance(geometry, dict)
        or geometry.get("type") != "Point"
    ):
        raise ValueError(
            "USGS monitoring location must have Point geometry"
        )

    coordinates = geometry.get("coordinates")

    if (
        not isinstance(coordinates, (list, tuple))
        or len(coordinates) < 2
    ):
        raise ValueError(
            "USGS monitoring location has invalid coordinates"
        )

    longitude = _optional_float(
        coordinates[0],
        name="longitude",
    )
    latitude = _optional_float(
        coordinates[1],
        name="latitude",
    )

    if (
        longitude is None
        or latitude is None
        or not -180 <= longitude <= 180
        or not -90 <= latitude <= 90
    ):
        raise ValueError(
            "USGS monitoring location has invalid longitude/latitude"
        )

    drainage_sqmi = _optional_float(
        properties.get("drainage_area"),
        name="drainage area",
    )

    contributing_sqmi = _optional_float(
        properties.get("contributing_drainage_area"),
        name="contributing drainage area",
    )

    return {
        "source": "usgs",
        "source_id": gage,
        "monitoring_location_id": location_id,
        "monitoring_location_name": properties.get(
            "monitoring_location_name"
        ),
        "longitude": longitude,
        "latitude": latitude,
        "site_type": properties.get("site_type"),
        "hydrologic_unit_code": properties.get(
            "hydrologic_unit_code"
        ),
        "drainage_area_sqmi": drainage_sqmi,
        "drainage_area_km2": (
            None
            if drainage_sqmi is None
            else drainage_sqmi * SQMI_TO_KM2
        ),
        "contributing_drainage_area_sqmi": contributing_sqmi,
        "contributing_drainage_area_km2": (
            None
            if contributing_sqmi is None
            else contributing_sqmi * SQMI_TO_KM2
        ),
        "horizontal_positional_accuracy": properties.get(
            "horizontal_positional_accuracy"
        ),
    }


def fetch_usgs_streamflow(
    gage_id: str,
    start_time,
    end_time,
    *,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> pd.DataFrame:
    """Retrieve native USGS discharge in the UTC interval [start, end).

    Observations remain at their native timestamps. No temporal averaging
    is performed here; comparison/alignment belongs in a separate layer.
    """
    gage = _normalize_gage_id(gage_id)
    location_id = _location_id(gage)

    start = _utc_timestamp(
        start_time,
        name="start_time",
    )
    end = _utc_timestamp(
        end_time,
        name="end_time",
    )

    if end <= start:
        raise ValueError(
            "end_time must be after start_time"
        )

    interval = (
        f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
        f"{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )

    url = _collection_url(
        "continuous",
        {
            "f": "json",
            "limit": 1000,
            "monitoring_location_id": location_id,
            "parameter_code": DISCHARGE_PARAMETER_CODE,
            "datetime": interval,
        },
    )

    features = _fetch_features(
        url,
        timeout=timeout,
        api_key=api_key,
    )

    rows = []

    for feature in features:
        properties = feature.get("properties", {})

        if not isinstance(properties, dict):
            raise ValueError(
                "USGS continuous feature has invalid properties"
            )

        if (
            properties.get("monitoring_location_id")
            != location_id
            or properties.get("parameter_code")
            != DISCHARGE_PARAMETER_CODE
        ):
            continue

        timestamp = pd.to_datetime(
            properties.get("time"),
            utc=True,
            errors="coerce",
        )

        if pd.isna(timestamp):
            raise ValueError(
                "USGS continuous feature has an invalid timestamp"
            )

        # OGC interval behavior may include the end point.
        # The package contract is explicitly half-open [start, end).
        if not start <= timestamp < end:
            continue

        value = _optional_float(
            properties.get("value"),
            name="discharge value",
        )

        if value is None:
            continue

        native_unit = str(
            properties.get("unit_of_measure", "")
        ).strip()

        factor = _DISCHARGE_UNIT_FACTORS.get(native_unit)

        if factor is None:
            raise ValueError(
                "Unrecognized USGS discharge "
                f"unit: {native_unit!r}"
            )

        rows.append(
            {
                "source": "usgs",
                "series": "observation",
                "source_id": gage,
                "usgs_gage_id": gage,
                "valid_time": timestamp,
                "interval_start": timestamp,
                "interval_end": timestamp,
                "time_support": "instantaneous",
                "aggregation": "native",
                "streamflow_m3s": value * factor,
                "unit": "m3/s",
                "method": "usgs_api",
                "parameter_code": properties.get(
                    "parameter_code"
                ),
                "statistic_id": properties.get("statistic_id"),
                "time_series_id": properties.get(
                    "time_series_id"
                ),
                "approval_status": properties.get(
                    "approval_status"
                ),
                "qualifier": properties.get("qualifier"),
                "native_value": value,
                "native_unit": native_unit,
            }
        )

    frame = pd.DataFrame(
        rows,
        columns=USGS_STREAMFLOW_COLUMNS,
    )

    if frame.empty:
        return frame

    if not frame["streamflow_m3s"].map(math.isfinite).all():
        raise ValueError(
            "USGS discharge contains non-finite values"
        )

    conflicts = (
        frame.groupby("valid_time")["streamflow_m3s"]
        .nunique(dropna=False)
        .gt(1)
    )

    if conflicts.any():
        timestamp = conflicts[conflicts].index[0]

        raise ValueError(
            "Conflicting USGS discharge "
            f"values at {timestamp}"
        )

    return (
        frame.sort_values(
            ["valid_time", "time_series_id"],
            na_position="last",
        )
        .drop_duplicates(
            ["valid_time", "streamflow_m3s"],
            keep="first",
        )
        .reset_index(drop=True)
    )
