
"""Compatibility tests for operational Kerchunk reference validation."""

import sys
from pathlib import Path

import pytest

from streamflow_getter.reference_validation import (
    validate_reference,
    valid_source_identity,
)

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmarks"
sys.path.insert(0, str(BENCHMARK_DIR))

from reference_validation import (
    validate_reference as benchmark_validate_reference,
    valid_source_identity as benchmark_source_identity,
)


@pytest.fixture
def reference():
    url = "https://example.com/nwm.nc"

    return {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "valid",
        "wrong_version",
        "missing_key",
        "wrong_offset",
        "wrong_source",
    ],
)
def test_reference_validation_matches_benchmark(reference, mutation):
    expected_url = "https://example.com/nwm.nc"

    if mutation == "wrong_version":
        reference["version"] = 2
    elif mutation == "missing_key":
        del reference["refs"]["streamflow/0"]
    elif mutation == "wrong_offset":
        reference["refs"]["streamflow/0"][1] = -1
    elif mutation == "wrong_source":
        reference["refs"]["streamflow/0"][0] = (
            "https://example.com/other.nc"
        )

    assert validate_reference(reference) == (
        benchmark_validate_reference(reference)
    )

    assert valid_source_identity(reference, expected_url) == (
        benchmark_source_identity(reference, expected_url)
    )
