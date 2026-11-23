"""USGS/NWM/GEOGLOWS study orchestration built on existing package adapters.

This module does not implement streamflow retrieval, spatial indexing, temporal
alignment, or serialization algorithms. It coordinates the public implementations
and makes cross-version RouteLink uncertainty explicit in every saved result.
"""

from __future__ import annotations

from copy import copy

import json
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
from shapely.errors import GEOSException

from streamflow_getter.basin_comparison import compare_drainage_areas
from streamflow_getter.geoglows.reach_resolution import nearest_geoglows_reach
from streamflow_getter.geoglows.streamflow import fetch_geoglows_retrospective
from streamflow_getter.multi_source_streamflow import fetch_multi_source_streamflow
from streamflow_getter.operational_nwm import ForecastConfig
from streamflow_getter.operational_versions import resolve_operational_nwm_version
from streamflow_getter.output import write_timeseries
from streamflow_getter.reach_resolution import (
    build_nwm_to_usgs_index,
    load_gage_index_with_provenance,
    validate_routelink_compatibility,
)
from streamflow_getter.spatial_resolution import (
    load_nearby_reaches,
    nearest_reaches,
    validate_hydrofabric_crs,
)
from streamflow_getter.streamflow_alignment import build_exact_time_comparison
from streamflow_getter.usgs.streamflow import (
    fetch_usgs_monitoring_location,
    fetch_usgs_streamflow,
)

LINE_COLORS = {
    "usgs": "#111111",
    "geoglows": "#2563EB",
    "analysis_assim_no_da": "#C99815",
    "analysis_assim": "#14532D",
    "short_range": "#DC2626",
}


def _utc_hour(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None or timestamp != timestamp.floor("h"):
        raise ValueError("Reference must be an explicit whole-hour UTC timestamp")
    return timestamp.tz_convert("UTC")


def _optional_float(value: object) -> float | None:
    if value is None or not pd.notna(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _gage_near_click(
    station: Mapping[str, Any], longitude: float, latitude: float
) -> bool:
    """Avoid identifying a distant station merely because its reach was clicked.

    RouteLink identifies the NWM *reach*, not an arbitrary position along it.
    Only show USGS on the explorer when the user clicks within 250 m of the
    real USGS monitoring-location coordinates (WGS84 geodesic distance).
    """
    from pyproj import Geod

    try:
        station_lon = float(station["longitude"])
        station_lat = float(station["latitude"])
    except (KeyError, TypeError, ValueError):
        return False
    distance_m = Geod(ellps="WGS84").inv(longitude, latitude, station_lon, station_lat)[
        2
    ]
    return isfinite(distance_m) and abs(distance_m) <= 250.0


def _read_geojson(hydrofabric: Path, feature_id: int) -> dict | None:
    """Read the existing Hydrofabric's exact reach geometry (no new snap)."""
    import pyogrio

    reaches = pyogrio.read_dataframe(
        hydrofabric,
        layer="nwm_reaches_conus",
        where=f"ID = {feature_id}",
        columns=["ID"],
    )
    if len(reaches) != 1:
        return None
    return reaches.to_crs("EPSG:4326").__geo_interface__


def _validate_study_inputs(
    *,
    policy: str,
    hours_before: int,
    hours_after: int,
    radius_m: float,
    max_workers: int,
) -> None:
    """Validate user configuration before any expensive I/O."""
    if policy not in ("strict", "exploratory"):
        raise ValueError("cross_version_policy must be 'strict' or 'exploratory'")
    if hours_before < 0 or hours_after <= 0 or radius_m <= 0:
        raise ValueError("Invalid UTC window or search distance")
    if max_workers < 1:
        raise ValueError("max_workers must be positive")


def _window_nwm_version(
    start: pd.Timestamp,
    reference: pd.Timestamp,
    end: pd.Timestamp,
    requested: str,
) -> str:
    """Use the existing NWM version registry for all three UTC boundaries."""
    versions = {
        resolve_operational_nwm_version(
            ForecastConfig(
                date=timestamp.strftime("%Y-%m-%d"),
                cycle=timestamp.hour,
                product="short_range",
                domain="conus",
            )
        )
        for timestamp in (start, reference, end)
    }
    if None in versions or len(versions) != 1:
        raise ValueError(f"Unsupported or mixed NWM versions: {versions}")
    version = versions.pop()
    if requested not in ("auto", version):
        raise ValueError(f"The selected UTC window uses NWM {version}, not {requested}")
    return version


def _load_route_index(settings: Mapping[str, Any], version: str) -> tuple:
    """Read each configured index once and prefer an exact network version."""
    sources = dict.fromkeys(
        Path(settings[key]).expanduser()
        for key in ("routelink", "routelink_3_0", "routelink_3_1")
        if settings.get(key)
    )
    if not sources:
        raise ValueError("No RouteLink paths were provided")
    indexes = []
    default = Path(settings["routelink"]).expanduser()
    for path in sources:
        if not path.is_file():
            if path == default:
                raise FileNotFoundError(path)
            continue
        index, provenance = load_gage_index_with_provenance(path, engine="h5netcdf")
        try:
            validate_routelink_compatibility((version,), provenance["network_version"])
            compatible = True
        except ValueError:
            compatible = False
        indexes.append((compatible, path, index, provenance))
    if not indexes:
        raise FileNotFoundError("No readable RouteLink found")
    return next((entry for entry in indexes if entry[0]), indexes[0])


def _fetch_without_nwm(
    *,
    usgs_id: str | None,
    geoglows_id: int | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    max_workers: int,
    usgs_api_key: str | None,
) -> tuple[dict, dict, float]:
    """Fallback to existing individual adapters when no NWM reach is valid."""
    jobs = {}
    if usgs_id:
        jobs["USGS"] = (
            fetch_usgs_streamflow,
            (usgs_id, start, end),
            {"api_key": usgs_api_key},
        )
    if geoglows_id is not None:
        jobs["GEOGLOWS retrospective"] = (
            fetch_geoglows_retrospective,
            (geoglows_id, start, end),
            {},
        )
    if not jobs:
        raise ValueError("No NWM, USGS or GEOGLOWS source was identified")

    def timed(job):
        function, args, kwargs = job
        started = perf_counter()
        result = function(*args, **kwargs)
        return result, perf_counter() - started

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=min(len(jobs), max_workers)) as pool:
        futures = {label: pool.submit(timed, job) for label, job in jobs.items()}
        completed = {label: future.result() for label, future in futures.items()}
    series = {label: value[0] for label, value in completed.items()}
    per_source = {label: value[1] for label, value in completed.items()}
    return series, per_source, perf_counter() - started


class StreamflowStudy:
    """A single UTC window, with version-aware RouteLink and click-to-query support.

    ``cross_version_policy='strict'`` omits an unverified USGS->NWM
    association. ``'exploratory'`` allows a *candidate* from an incompatible
    RouteLink, prominently tagged as unverified in metadata and console output.
    """

    def __init__(
        self,
        settings: Mapping[str, Any],
        *,
        reference_utc: str,
        hours_before: int = 3,
        hours_after: int = 6,
        nwm_version: str = "auto",
        cross_version_policy: str = "strict",
        search_radius_m: float = 3000,
        max_workers: int = 5,
        save_csv: bool = False,
        backend_revision: str | None = None,
        auto_save: bool = True,
    ) -> None:
        initialization_start = perf_counter()
        _validate_study_inputs(
            policy=cross_version_policy,
            hours_before=hours_before,
            hours_after=hours_after,
            radius_m=search_radius_m,
            max_workers=max_workers,
        )
        self.reference = _utc_hour(reference_utc)
        self.start = self.reference - pd.Timedelta(hours=hours_before)
        self.end = self.reference + pd.Timedelta(hours=hours_after)
        self._settings = dict(settings)
        self._requested_version = nwm_version
        self._hours_before = hours_before
        self._hours_after = hours_after
        self.workspace = Path(settings["workspace"]).expanduser()
        self.hydrofabric = Path(settings["hydrofabric"]).expanduser()
        self.radius_m = search_radius_m
        self.max_workers = max_workers
        self.save_csv = save_csv
        self.auto_save = auto_save
        self.backend_revision = backend_revision
        self.policy = cross_version_policy
        self.version = _window_nwm_version(
            self.start, self.reference, self.end, nwm_version
        )
        validate_hydrofabric_crs(self.hydrofabric)
        (
            self.crosswalk_compatible,
            self.routelink,
            self.gages,
            self.provenance,
        ) = _load_route_index(settings, self.version)
        self.reach_gages = build_nwm_to_usgs_index(self.gages)
        self.allow_candidate = self.crosswalk_compatible or self.policy == "exploratory"
        self.initialization_seconds = perf_counter() - initialization_start

    def for_reference(self, reference_utc: str) -> StreamflowStudy:
        """Use a new UTC window without changing the station-map study.

        Keep the loaded RouteLink index for the same NWM network version;
        reinitialize through the version-aware constructor if the version changes.
        """
        started = perf_counter()
        # A date-only selection retains the current study's UTC clock hour.
        if len(reference_utc) == 10 and reference_utc[4:5] == "-":
            reference_utc = f"{reference_utc}T{self.reference:%H:%M:%S}Z"
        reference = _utc_hour(reference_utc)
        if reference == self.reference:
            return self
        start = reference - pd.Timedelta(hours=self._hours_before)
        end = reference + pd.Timedelta(hours=self._hours_after)
        version = _window_nwm_version(start, reference, end, self._requested_version)
        if version != self.version:
            return type(self)(
                self._settings,
                reference_utc=reference.isoformat(),
                hours_before=self._hours_before,
                hours_after=self._hours_after,
                nwm_version=self._requested_version,
                cross_version_policy=self.policy,
                search_radius_m=self.radius_m,
                max_workers=self.max_workers,
                save_csv=self.save_csv,
                backend_revision=self.backend_revision,
                auto_save=self.auto_save,
            )
        updated = copy(self)
        updated.reference = reference
        updated.start = start
        updated.end = end
        updated.initialization_seconds = perf_counter() - started
        return updated

    @property
    def network_message(self) -> str:
        if self.crosswalk_compatible:
            return (
                f"NWM {self.version}: compatible RouteLink "
                f"{self.provenance['network_version']} ({len(self.gages)} gages)"
            )
        policy = (
            "provisional candidates enabled"
            if self.allow_candidate
            else "strict: no station-to-NWM matching"
        )
        return (
            f"NWM {self.version} versus RouteLink "
            f"{self.provenance['network_version']}: INCOMPATIBLE; {policy}"
        )

    def _gage_for_reach(self, feature_id: int | None) -> str | None:
        if feature_id is None or not self.allow_candidate:
            return None
        return self.reach_gages.get(feature_id)

    def compare_station(self, gage_id: str) -> dict:
        """Resolve USGS ID automatically through RouteLink, then retrieve data."""
        if (
            not isinstance(gage_id, str)
            or not gage_id.isascii()
            or not gage_id.isdecimal()
        ):
            raise ValueError("Preserve the exact numeric USGS identifier as a string")
        resolve_start = perf_counter()
        station = fetch_usgs_monitoring_location(
            gage_id, api_key=os.getenv("USGS_API_KEY")
        )
        station_seconds = perf_counter() - resolve_start
        nwm_id = self.gages.get(gage_id) if self.allow_candidate else None
        method = (
            "routelink_exact_compatible"
            if nwm_id is not None and self.crosswalk_compatible
            else "routelink_cross_version_provisional"
            if nwm_id is not None
            else "no_compatible_routelink"
        )
        return self._retrieve(
            longitude=float(station["longitude"]),
            latitude=float(station["latitude"]),
            nwm_id=nwm_id,
            usgs_id=gage_id,
            station=station,
            method=method,
            nwm_distance_m=None,
            resolution_seconds=station_seconds,
            station_metadata_seconds=station_seconds,
            preflight_seconds=station_seconds,
        )

    def _point_usgs(
        self,
        feature_id: int | None,
        longitude: float,
        latitude: float,
        *,
        include_usgs: bool,
    ) -> tuple[str | None, dict | None, float]:
        gage_id = self._gage_for_reach(feature_id) if include_usgs else None
        if not gage_id:
            return None, None, 0.0
        started = perf_counter()
        station = fetch_usgs_monitoring_location(
            gage_id, api_key=os.getenv("USGS_API_KEY")
        )
        duration = perf_counter() - started
        if not _gage_near_click(station, longitude, latitude):
            return None, None, duration
        return gage_id, station, duration

    def compare_point(
        self, longitude: float, latitude: float, *, include_usgs: bool = True
    ) -> dict:
        """USGS is included only at a locally mapped station (within 250 m)."""
        resolution_start = perf_counter()
        reaches = load_nearby_reaches(
            self.hydrofabric,
            longitude,
            latitude,
            max_distance_m=self.radius_m,
        )
        candidates = nearest_reaches(
            reaches,
            longitude,
            latitude,
            max_distance_m=self.radius_m,
            limit=1,
        )
        nwm_id = int(candidates[0]["feature_id"]) if candidates else None
        distance_m = (
            _optional_float(candidates[0].get("distance_m")) if candidates else None
        )
        resolution_seconds = perf_counter() - resolution_start
        gage_id, station, station_metadata_seconds = self._point_usgs(
            nwm_id, longitude, latitude, include_usgs=include_usgs
        )
        return self._retrieve(
            longitude=longitude,
            latitude=latitude,
            nwm_id=nwm_id,
            usgs_id=gage_id,
            station=station,
            method=(
                "local_hydrofabric_with_compatible_routelink"
                if gage_id and self.crosswalk_compatible
                else "local_hydrofabric_with_provisional_routelink"
                if gage_id
                else "local_hydrofabric_point"
            ),
            nwm_distance_m=distance_m,
            resolution_seconds=resolution_seconds,
            station_metadata_seconds=station_metadata_seconds,
            preflight_seconds=resolution_seconds + station_metadata_seconds,
        )

    def _retrieve(
        self,
        *,
        longitude: float,
        latitude: float,
        nwm_id: int | None,
        usgs_id: str | None,
        station: dict | None,
        method: str,
        nwm_distance_m: float | None,
        resolution_seconds: float = 0.0,
        station_metadata_seconds: float = 0.0,
        preflight_seconds: float = 0.0,
    ) -> dict:
        request_start = perf_counter()
        start = perf_counter()
        try:
            geo = nearest_geoglows_reach(
                longitude, latitude, max_distance_m=self.radius_m
            )
            geo_error = None
        except (OSError, ValueError, KeyError, TimeoutError, GEOSException) as exc:
            # A bad optional GEOGLOWS ring must not abort usable NWM/USGS data.
            geo, geo_error = None, f"{type(exc).__name__}: {exc}"
        geo_id = int(geo["river_id"]) if geo else None
        spatial_seconds = perf_counter() - start

        area_start = perf_counter()
        usgs_area = _optional_float(
            station.get("drainage_area_km2") if station else None
        )
        geoglows_area = _optional_float(geo.get("upstream_area_km2") if geo else None)
        drainage = compare_drainage_areas(
            usgs_area,
            geoglows_area,
            reference_label="USGS",
            candidate_label="GEOGLOWS",
        )
        area_seconds = perf_counter() - area_start

        start = perf_counter()
        if nwm_id is not None:
            fetched = fetch_multi_source_streamflow(
                int(nwm_id),
                self.start,
                self.end,
                forecast_reference_time=self.reference,
                nwm_analysis_products=("analysis_assim", "analysis_assim_no_da"),
                nwm_forecast_products=("short_range",),
                usgs_gage_id=usgs_id,
                geoglows_river_id=geo_id,
                usgs_api_key=os.getenv("USGS_API_KEY"),
                cache_dir=self.workspace / "reference_cache",
                max_workers=self.max_workers,
            )
            series = fetched.series
            timings = fetched.source_timings_seconds
            wall_seconds = fetched.total_elapsed_seconds
        else:
            # Reuse the existing individual providers if an NWM ID is missing.
            series, timings, wall_seconds = _fetch_without_nwm(
                usgs_id=usgs_id,
                geoglows_id=geo_id,
                start=self.start,
                end=self.end,
                max_workers=self.max_workers,
                usgs_api_key=os.getenv("USGS_API_KEY"),
            )

        populated = {name: frame for name, frame in series.items() if not frame.empty}
        if not populated:
            raise ValueError("All requested sources returned empty discharge series")
        alignment_start = perf_counter()
        aligned = build_exact_time_comparison(populated, how="outer")
        table = aligned.loc[
            :, ["valid_time", *(c for c in aligned if c.endswith("_streamflow_m3s"))]
        ]
        alignment_seconds = perf_counter() - alignment_start
        geometry_start = perf_counter()
        nwm_geojson = (
            _read_geojson(self.hydrofabric, int(nwm_id)) if nwm_id is not None else None
        )
        geometry_seconds = perf_counter() - geometry_start

        # The notebook opts out of automatic saving; the v18 public API
        # retains auto_save=True for existing integrations.

        verified = self.crosswalk_compatible and bool(usgs_id and nwm_id is not None)
        metadata = {
            "schema": "streamflow_getter.station_comparison.v19",
            "backend_git_revision": self.backend_revision,
            "ids": {"usgs": usgs_id, "nwm": nwm_id, "geoglows": geo_id},
            "point_epsg4326": {"longitude": longitude, "latitude": latitude},
            "nwm": {
                "version": self.version,
                "selection_method": method,
                "distance_m": nwm_distance_m,
                "gage_crosswalk_verified_for_version": verified,
                "hydrofabric_network_compatibility_verified": False,
                "routelink_network_version": self.provenance["network_version"],
                "routelink_path": str(self.routelink),
                "routelink_sha256": self.provenance.get("crosswalk_sha256"),
                "cross_version_policy": self.policy,
            },
            "geoglows": {
                "selection": "independent_nearest_channel" if geo else "not_found",
                "distance_m": _optional_float(geo.get("distance_m")) if geo else None,
                "upstream_area_km2": geoglows_area,
                "selection_error": geo_error,
                "product": "GEOGLOWS v2 hourly retrospective",
            },
            "drainage_area_comparison": drainage,
            "hydrologic_equivalence_verified": False,
            "utc_window": {
                "start": self.start.isoformat(),
                "reference": self.reference.isoformat(),
                "end": self.end.isoformat(),
                "alignment": "exact_timestamp_outer_no_interpolation",
            },
            "units": "m3/s",
            "source_rows": {name: len(frame) for name, frame in populated.items()},
            "source_seconds": timings,
            "geoglows_spatial_seconds": spatial_seconds,
            "retrieval_wall_seconds": wall_seconds,
            "timings_seconds": {
                "study_initialization": self.initialization_seconds,
                "station_metadata": station_metadata_seconds,
                "nwm_reach_resolution": resolution_seconds,
                "geoglows_reach_resolution": spatial_seconds,
                "drainage_area_comparison": area_seconds,
                "source_retrieval_wall": wall_seconds,
                "alignment": alignment_seconds,
                "nwm_geometry": geometry_seconds,
                "total_request_wall": perf_counter()
                - request_start
                + preflight_seconds,
                "per_source": timings,
            },
            "saved": False,
            "files": [],
        }
        item = {
            "table": table,
            "metadata": metadata,
            "nwm_geojson": nwm_geojson,
            "geoglows_geometry": geo.get("geometry") if geo else None,
            "folder": None,
        }
        if self.auto_save:
            self._save_record(item, name_by_gage=False)
        return item

    def save_record(self, result: dict) -> Path:
        """Persist a chosen result, naming files after its exact USGS ID if present.

        On-demand saving is opt-in from the notebook UI. Save calls are
        idempotent per result; a second click never overwrites outputs.
        """
        return self._save_record(result, name_by_gage=True)

    def _save_record(self, result: dict, *, name_by_gage: bool) -> Path:
        if result.get("folder") is not None:
            return Path(result["folder"])
        ids = result["metadata"]["ids"]
        usgs_id = ids["usgs"]
        label = (
            f"USGS_{usgs_id}"
            if usgs_id
            else f"NWM_{ids['nwm']}"
            if ids["nwm"] is not None
            else f"GEOGLOWS_{ids['geoglows']}"
        )
        basename = label.removeprefix("USGS_") if name_by_gage else "streamflow"
        # Avoid file collisions and preserve prior datasets from repeated clicks.
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        folder = self.workspace / "results" / label / run_id
        folder.mkdir(parents=True, exist_ok=False)
        metadata_file = f"{basename}.json" if name_by_gage else "metadata.json"
        data_file = f"{basename}.parquet"
        csv_file = f"{basename}.csv"
        save_start = perf_counter()
        write_timeseries(result["table"], folder / data_file, output_format="parquet")
        if self.save_csv:
            write_timeseries(result["table"], folder / csv_file, output_format="csv")
        metadata = result["metadata"].copy()
        metadata["saved"] = True
        metadata["files"] = [data_file, metadata_file] + (
            [csv_file] if self.save_csv else []
        )
        metadata["timings_seconds"] = dict(metadata["timings_seconds"])
        metadata["timings_seconds"]["save"] = perf_counter() - save_start
        (folder / metadata_file).write_text(
            json.dumps(metadata, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        result["metadata"] = metadata
        result["folder"] = folder
        return folder


def plot_comparison(result: Mapping[str, Any]):
    """Backward-compatible access to the optional Plotly renderer."""
    from streamflow_getter.visualization.plotly import (
        plot_comparison as render_plot,
    )

    return render_plot(result)
