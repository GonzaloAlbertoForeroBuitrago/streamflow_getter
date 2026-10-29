"""Resolve operational NWM reaches using RouteLink metadata."""

from collections import defaultdict

import numpy as np
import xarray as xr


def build_gage_index(ds: xr.Dataset) -> dict[str, int]:
    """Build a validated gage-to-feature-ID index from RouteLink."""
    if "link" not in ds or "gages" not in ds:
        raise ValueError("RouteLink requires 'link' and 'gages'")

    links = np.asarray(ds["link"].values)
    gages = np.asarray(ds["gages"].values)

    if not np.issubdtype(links.dtype, np.integer):
        raise ValueError("RouteLink feature IDs must be integers")

    if links.ndim != 1 or gages.ndim != 1:
        raise ValueError("RouteLink identifiers must be one-dimensional")

    if len(links) != len(gages):
        raise ValueError("RouteLink link/gages length mismatch")

    if len(np.unique(links)) != len(links):
        raise ValueError("Duplicate RouteLink feature IDs")

    mapping = defaultdict(set)

    for link, raw_gage in zip(links, gages):
        if isinstance(raw_gage, bytes):
            gage = raw_gage.decode("utf-8").strip()
        else:
            gage = str(raw_gage).strip()

        if gage:
            mapping[gage].add(int(link))

    ambiguous = {
        gage: reaches
        for gage, reaches in mapping.items()
        if len(reaches) > 1
    }

    if ambiguous:
        raise ValueError(
            f"Ambiguous RouteLink gage mappings: {len(ambiguous)}"
        )

    return {
        gage: next(iter(reaches))
        for gage, reaches in mapping.items()
    }



def resolve_gages(
    gages: list[str],
    index: dict[str, int],
) -> dict[str, int]:
    """Resolve gage IDs using exact string matching."""
    result = {}

    for gage in gages:
        if not isinstance(gage, str) or not gage:
            raise ValueError("Gage IDs must be nonempty strings")

        if gage not in index:
            raise ValueError(f"Gage not found in RouteLink: {gage}")

        result[gage] = index[gage]

    return result



def load_gage_index(
    path,
    *,
    engine=None,
) -> dict[str, int]:
    """Load and validate a RouteLink gage index from a NetCDF file."""
    from pathlib import Path

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"RouteLink file not found: {path}")

    with xr.open_dataset(path, engine=engine) as ds:
        return build_gage_index(ds)
