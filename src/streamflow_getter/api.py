"""Public, presentation-independent entry point for Streamflow Getter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from collections.abc import Mapping


class StreamflowClient:
    """Lightweight interface to the existing scientific backend.

    No network access, hydrofabric loading, or visualization is
    performed during client construction.
    """

    def __init__(
        self,
        settings: Mapping[str, Any],
        *,
        hours_before: int = 3,
        hours_after: int = 6,
        nwm_version: str = "auto",
        cross_version_policy: str = "strict",
        search_radius_m: float = 3000,
        max_workers: int = 5,
        save_csv: bool = False,
        auto_save: bool = False,
    ):
        if not isinstance(settings, Mapping):
            raise TypeError("settings must be a mapping")

        self.settings = dict(settings)
        self._options = {
            "hours_before": hours_before,
            "hours_after": hours_after,
            "nwm_version": nwm_version,
            "cross_version_policy": cross_version_policy,
            "search_radius_m": search_radius_m,
            "max_workers": max_workers,
            "save_csv": save_csv,
            "auto_save": auto_save,
        }

    @classmethod
    def from_config(cls, path: str | Path, **kwargs):
        """Load the existing JSON configuration without changing it."""
        config_path = Path(path).expanduser()
        settings = json.loads(config_path.read_text(encoding="utf-8"))

        if not isinstance(settings, dict):
            raise ValueError("Configuration must contain a JSON object")

        return cls(settings, **kwargs)

    def study(self, reference_utc: str):
        """Create a study using the existing backend implementation."""
        from streamflow_getter.station_comparison import StreamflowStudy

        return StreamflowStudy(
            self.settings,
            reference_utc=reference_utc,
            **self._options,
        )

    def compare_station(self, gage_id: str, *, reference_utc: str):
        """Retrieve a station comparison without visualization."""
        return self.study(reference_utc).compare_station(gage_id)

    def compare_point(
        self,
        longitude: float,
        latitude: float,
        *,
        reference_utc: str,
        include_usgs: bool = True,
    ):
        """Retrieve a geographic river comparison."""
        return self.study(reference_utc).compare_point(
            longitude,
            latitude,
            include_usgs=include_usgs,
        )

    def compare_station_result(self, gage_id: str, *, reference_utc: str):
        """Return a convenient view of the existing station record."""
        from streamflow_getter.results import ComparisonResult

        return ComparisonResult(
            self.compare_station(gage_id, reference_utc=reference_utc)
        )

    def compare_point_result(
        self,
        longitude: float,
        latitude: float,
        *,
        reference_utc: str,
        include_usgs: bool = True,
    ):
        """Return a convenient view of the existing point record."""
        from streamflow_getter.results import ComparisonResult

        return ComparisonResult(
            self.compare_point(
                longitude,
                latitude,
                reference_utc=reference_utc,
                include_usgs=include_usgs,
            )
        )
