import pytest

from streamflow_getter.basin_comparison import (
    compare_drainage_areas,
)


def test_area_comparison_available():
    result = compare_drainage_areas(
        745.916575776768,
        788.289088,
        reference_label="USGS",
        candidate_label="GEOGLOWS",
    )

    assert result["available"] is True

    assert result[
        "difference_km2"
    ] == pytest.approx(
        42.372512223232
    )

    assert result[
        "relative_difference_pct"
    ] == pytest.approx(
        5.6805966779
    )

    assert result[
        "area_ratio"
    ] == pytest.approx(
        1.0568059668
    )

    assert (
        "supporting evidence only"
        in result["message"]
    )


def test_nwm_usgs_area_comparison():
    result = compare_drainage_areas(
        745.916575776768,
        744.246,
        reference_label="USGS",
        candidate_label="NWM/NHDPlus",
    )

    assert result["available"] is True

    assert result[
        "relative_difference_pct"
    ] == pytest.approx(
        0.2239628172
    )


@pytest.mark.parametrize(
    ("reference", "candidate"),
    [
        (None, 788.0),
        (746.0, None),
        (None, None),
    ],
)
def test_missing_area_is_normal(
    reference,
    candidate,
):
    result = compare_drainage_areas(
        reference,
        candidate,
        reference_label="USGS",
        candidate_label="GEOGLOWS",
    )

    assert result[
        "available"
    ] is False

    assert (
        result[
            "relative_difference_pct"
        ]
        is None
    )

    assert (
        "unavailable"
        in result["message"]
    )


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        float("inf"),
        float("nan"),
        True,
    ],
)
def test_invalid_available_area(
    value,
):
    with pytest.raises(
        ValueError,
        match="positive area",
    ):
        compare_drainage_areas(
            value,
            788,
            reference_label="USGS",
            candidate_label="GEOGLOWS",
        )


def test_labels_are_required():
    with pytest.raises(
        ValueError,
        match="labels",
    ):
        compare_drainage_areas(
            746,
            788,
            reference_label="",
            candidate_label="GEOGLOWS",
        )
