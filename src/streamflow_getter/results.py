"""Non-copying result interface for multi-source streamflow studies."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Expose an existing study record without altering scientific data.

    This is a view over the established dictionary contract, not a
    replacement for the source-level MultiSourceStreamflowResult.
    """

    raw: Mapping[str, Any]

    def __post_init__(self):
        if not isinstance(self.raw, Mapping):
            raise TypeError("Study result must be a mapping.")

        table = self.raw.get("table")
        if not isinstance(table, pd.DataFrame):
            raise TypeError("Study result requires a pandas DataFrame.")

        if "valid_time" not in table.columns:
            raise ValueError("Study table requires valid_time.")

        metadata = self.raw.get("metadata")
        if not isinstance(metadata, Mapping):
            raise TypeError("Study result requires metadata.")

        if not isinstance(metadata.get("ids"), Mapping):
            raise TypeError("Study metadata requires an ids mapping.")

    @property
    def table(self) -> pd.DataFrame:
        """Original aligned UTC table; no copying or resampling."""
        return self.raw["table"]

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Original provenance and scientific metadata."""
        return self.raw["metadata"]

    @property
    def ids(self) -> Mapping[str, Any]:
        """Native USGS, NWM and GEOGLOWS identifiers."""
        return self.metadata["ids"]

    @property
    def network(self) -> dict[str, Any]:
        """Original network metadata and equivalence status."""
        return {
            "nwm": self.metadata.get("nwm", {}),
            "geoglows": self.metadata.get("geoglows", {}),
            "hydrologic_equivalence_verified": self.metadata.get(
                "hydrologic_equivalence_verified"
            ),
        }

    @property
    def geometries(self) -> dict[str, Any]:
        """Original geometries, without transformation or replacement."""
        return {
            "nwm": self.raw.get("nwm_geojson"),
            "geoglows": self.raw.get("geoglows_geometry"),
        }

    @property
    def source_rows(self) -> Mapping[str, int]:
        """Rows reported for populated sources; not expected coverage."""
        return self.metadata.get("source_rows", {})

    @property
    def warnings(self) -> tuple[str, ...]:
        """Report explicitly unverified associations and source errors."""
        warnings = []
        ids = self.ids
        nwm = self.metadata.get("nwm", {})
        geoglows = self.metadata.get("geoglows", {})

        if (
            ids.get("usgs") is not None
            and ids.get("nwm") is not None
            and nwm.get("gage_crosswalk_verified_for_version") is False
        ):
            warnings.append(
                "USGS–NWM RouteLink association is not verified "
                "for the selected NWM version."
            )

        if (
            ids.get("nwm") is not None
            and nwm.get("hydrofabric_network_compatibility_verified") is False
        ):
            warnings.append("NWM Hydrofabric network compatibility is not verified.")

        if geoglows.get("selection_error"):
            warnings.append(f"GEOGLOWS selection error: {geoglows['selection_error']}")

        if self.metadata.get("hydrologic_equivalence_verified") is False:
            warnings.append(
                "Hydrologic equivalence between selected networks "
                "has not been verified."
            )

        return tuple(warnings)

    @staticmethod
    def _geojson_document(value: Any, *, source: str) -> dict[str, Any] | None:
        """Preserve GeoJSON without changing its coordinates."""
        if value is None:
            return None

        payload = (
            value
            if isinstance(value, Mapping)
            else getattr(value, "__geo_interface__", None)
        )

        if not isinstance(payload, Mapping):
            raise TypeError(f"{source} geometry must be GeoJSON-like")

        return dict(payload)

    def export(
        self,
        path: str | Path,
        *,
        output_format: str | None = None,
    ) -> tuple[Path, Path]:
        """Export original scientific data and a versioned manifest.

        Existing files are never overwritten. Exporting does not
        mutate the in-memory study record or reproject geometries.
        """
        from streamflow_getter.output import (
            resolve_output_format,
            write_timeseries_with_manifest,
        )

        destination = Path(path).expanduser()

        manifest = {
            "schema": "streamflow_getter.comparison_export.v1",
            "data_file": destination.name,
            "data_format": resolve_output_format(destination, output_format),
            "metadata": dict(self.metadata),
            "geometries": {
                "nwm": self._geojson_document(
                    self.raw.get("nwm_geojson"),
                    source="NWM",
                ),
                "geoglows": self._geojson_document(
                    self.raw.get("geoglows_geometry"),
                    source="GEOGLOWS",
                ),
            },
            "warnings": list(self.warnings),
        }

        return write_timeseries_with_manifest(
            self.table,
            destination,
            manifest,
            output_format=output_format,
        )

    @classmethod
    def load(cls, path: str | Path) -> "ComparisonResult":
        """Load a previously exported comparison without network access."""
        destination = Path(path).expanduser()

        payload, data_format = _read_comparison_manifest(destination)
        metadata, geometries, saved_warnings = _validate_comparison_manifest(payload)
        table = _read_comparison_table(destination, data_format)

        result = cls(
            {
                "table": table,
                "metadata": metadata,
                "nwm_geojson": geometries.get("nwm"),
                "geoglows_geometry": geometries.get("geoglows"),
                "folder": None,
            }
        )

        if list(result.warnings) != saved_warnings:
            raise ValueError("Manifest warnings disagree with scientific metadata.")

        return result


def _read_comparison_manifest(destination: Path):
    """Read and validate the identity of a comparison export."""
    import json

    from streamflow_getter.output import (
        manifest_path_for,
        resolve_output_format,
    )

    manifest_file = manifest_path_for(destination)
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("Comparison manifest must be an object.")

    if payload.get("schema") != "streamflow_getter.comparison_export.v1":
        raise ValueError("Unsupported comparison manifest schema.")

    if payload.get("data_file") != destination.name:
        raise ValueError("Manifest data filename mismatch.")

    data_format = resolve_output_format(destination)

    if payload.get("data_format") != data_format:
        raise ValueError("Manifest data format mismatch.")

    return payload, data_format


def _validate_comparison_manifest(payload: dict):
    """Validate the scientific metadata and saved warnings."""
    metadata = payload.get("metadata")
    geometries = payload.get("geometries")
    warnings = payload.get("warnings")

    if not isinstance(metadata, dict):
        raise ValueError("Invalid comparison metadata.")

    if not isinstance(geometries, dict):
        raise ValueError("Invalid comparison geometries.")

    if not isinstance(warnings, list) or not all(
        isinstance(item, str) for item in warnings
    ):
        raise ValueError("Invalid comparison warnings.")

    return metadata, geometries, warnings


def _read_comparison_table(destination: Path, data_format: str):
    """Read the original samples and enforce explicit UTC timestamps."""
    if data_format == "parquet":
        table = pd.read_parquet(destination)
    else:
        table = pd.read_csv(
            destination,
            dtype={"valid_time": "string"},
        )

    if table.empty or "valid_time" not in table.columns:
        raise ValueError("Missing or empty valid_time series.")

    if data_format == "parquet":
        if not isinstance(
            table["valid_time"].dtype,
            pd.DatetimeTZDtype,
        ):
            raise ValueError("Parquet valid_time must be timezone-aware.")
    else:
        timestamps = table["valid_time"].str.strip()

        # Accept explicit UTC, not naive local timestamps.
        explicit_utc = timestamps.str.contains(
            r"(?:Z|\+00:00)$",
            regex=True,
            na=False,
        )

        if not explicit_utc.all():
            raise ValueError("CSV valid_time requires an explicit UTC offset.")

    table["valid_time"] = pd.to_datetime(
        table["valid_time"],
        utc=True,
        errors="raise",
    )

    if table["valid_time"].isna().any():
        raise ValueError("Invalid or missing UTC timestamps.")

    return table
