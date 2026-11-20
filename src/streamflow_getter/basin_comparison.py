"""Optional hydrologic-area comparison utilities.

Drainage-area agreement is supporting evidence rather than a strict
network-equivalence test because different hydrographic datasets can use
different catchment boundaries and outlet definitions.
"""

from __future__ import annotations

import math


def _optional_area(
    value,
    *,
    name: str,
) -> float | None:
    """Return a positive finite km² value, or None when unavailable."""
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive area")

    try:
        area = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive area") from exc

    if not math.isfinite(area) or area <= 0:
        raise ValueError(f"{name} must be a positive area")

    return area


def compare_drainage_areas(
    reference_area_km2,
    candidate_area_km2,
    *,
    reference_label: str,
    candidate_label: str,
) -> dict:
    """Return optional drainage-area comparison evidence.

    Missing area metadata is a normal condition and does not invalidate
    the spatial selection.
    """
    if (
        not isinstance(reference_label, str)
        or not reference_label.strip()
        or not isinstance(candidate_label, str)
        or not candidate_label.strip()
    ):
        raise ValueError("Area-comparison labels must be nonempty strings")

    reference = _optional_area(
        reference_area_km2,
        name="reference_area_km2",
    )

    candidate = _optional_area(
        candidate_area_km2,
        name="candidate_area_km2",
    )

    if reference is None or candidate is None:
        return {
            "available": False,
            "reference_label": (reference_label.strip()),
            "candidate_label": (candidate_label.strip()),
            "reference_area_km2": reference,
            "candidate_area_km2": candidate,
            "difference_km2": None,
            "absolute_difference_km2": None,
            "relative_difference": None,
            "relative_difference_pct": None,
            "area_ratio": None,
            "message": (
                "Drainage-area comparison unavailable for this "
                "selection because area metadata are missing for "
                "one or both sources."
            ),
        }

    difference = candidate - reference

    absolute_difference = abs(difference)

    relative_difference = absolute_difference / reference

    ratio = candidate / reference

    return {
        "available": True,
        "reference_label": (reference_label.strip()),
        "candidate_label": (candidate_label.strip()),
        "reference_area_km2": reference,
        "candidate_area_km2": candidate,
        "difference_km2": difference,
        "absolute_difference_km2": (absolute_difference),
        "relative_difference": (relative_difference),
        "relative_difference_pct": (relative_difference * 100.0),
        "area_ratio": ratio,
        "message": (
            f"{reference_label.strip()} area: "
            f"{reference:.1f} km²; "
            f"{candidate_label.strip()} area: "
            f"{candidate:.1f} km²; "
            f"difference: {difference:+.1f} km² "
            f"({relative_difference * 100.0:.1f}%). "
            "Drainage areas from different hydrographic "
            "networks are not expected to match exactly; "
            "this comparison is supporting evidence only."
        ),
    }
