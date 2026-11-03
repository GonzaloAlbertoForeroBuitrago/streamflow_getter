
"""Tests for CSV and Parquet streamflow output."""

from pathlib import Path

import pandas as pd
import pytest

from streamflow_getter.output import (
    resolve_output_format,
    write_timeseries,
)


@pytest.fixture
def sample_frame():
    return pd.DataFrame({
        "forecast_date": ["2026-04-19", "2026-04-19"],
        "forecast_cycle": [0, 0],
        "product": ["analysis_assim", "short_range"],
        "domain": ["conus", "conus"],
        "lead_hour": [0, 1],
        "feature_id": [3586192, 3586192],
        "valid_time": [
            "2026-04-19T00:00:00",
            "2026-04-19T01:00:00",
        ],
        "reference_time": [
            "2026-04-18T21:00:00",
            "2026-04-19T00:00:00",
        ],
        "streamflow_m3s": [0.41, 0.42],
        "method": ["kerchunk", "kerchunk"],
    })


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("flow.csv", "csv"),
        ("flow.CSV", "csv"),
        ("flow.parquet", "parquet"),
        ("flow.PARQUET", "parquet"),
    ],
)
def test_format_inference(filename, expected):
    assert resolve_output_format(filename) == expected


def test_explicit_format():
    assert resolve_output_format(
        "flow.data", "parquet"
    ) == "parquet"


@pytest.mark.parametrize(
    "filename",
    ["flow", "flow.txt", "flow.json"],
)
def test_unsupported_extension(filename):
    with pytest.raises(ValueError):
        resolve_output_format(filename)


@pytest.mark.parametrize(
    "output_format",
    ["json", "", 123],
)
def test_invalid_explicit_format(output_format):
    with pytest.raises(ValueError):
        resolve_output_format(
            "flow.csv", output_format
        )


def test_csv_roundtrip(tmp_path, sample_frame):
    path = tmp_path / "flow.csv"

    result = write_timeseries(sample_frame, path)

    assert result == path
    assert path.exists()

    restored = pd.read_csv(path)

    assert list(restored.columns) == list(sample_frame.columns)
    assert restored["lead_hour"].tolist() == [0, 1]
    assert restored["product"].tolist() == [
        "analysis_assim",
        "short_range",
    ]
    assert restored["reference_time"].tolist() == [
        "2026-04-18T21:00:00",
        "2026-04-19T00:00:00",
    ]


def test_parquet_roundtrip(tmp_path, sample_frame):
    path = tmp_path / "flow.parquet"

    result = write_timeseries(sample_frame, path)

    assert result == path

    restored = pd.read_parquet(path)

    pd.testing.assert_frame_equal(
        restored,
        sample_frame,
    )


def test_existing_file_preserved(tmp_path, sample_frame):
    path = tmp_path / "flow.csv"
    path.write_text("existing-content")

    with pytest.raises(FileExistsError):
        write_timeseries(sample_frame, path)

    assert path.read_text() == "existing-content"


def test_empty_frame_rejected(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        write_timeseries(
            pd.DataFrame(),
            tmp_path / "flow.csv",
        )


def test_invalid_frame_rejected(tmp_path):
    with pytest.raises(TypeError):
        write_timeseries(
            {"streamflow": [0.41]},
            tmp_path / "flow.csv",
        )


def test_failed_serialization_cleans_temporary_file(
    tmp_path, sample_frame, monkeypatch
):
    path = tmp_path / "flow.csv"

    def failing_to_csv(self, *args, **kwargs):
        raise RuntimeError("Simulated serialization failure")

    monkeypatch.setattr(
        pd.DataFrame,
        "to_csv",
        failing_to_csv,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated serialization failure",
    ):
        write_timeseries(sample_frame, path)

    assert not path.exists()
    assert not list(tmp_path.glob(".streamflow-output-*.tmp"))



def test_publication_failure_cleans_destination(
    tmp_path, sample_frame, monkeypatch
):
    """Remove incomplete output when publication fails."""
    path = tmp_path / "flow.csv"

    original_open = Path.open

    class FailingOutput:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            self.file.__enter__()
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def write(self, data):
            self.file.write(data[:5])
            raise OSError("Simulated publication failure")

    def patched_open(self, mode="r", *args, **kwargs):
        file = original_open(self, mode, *args, **kwargs)

        if self == path and mode == "xb":
            return FailingOutput(file)

        return file

    monkeypatch.setattr(Path, "open", patched_open)

    with pytest.raises(
        OSError,
        match="Simulated publication failure",
    ):
        write_timeseries(sample_frame, path)

    assert not path.exists()
    assert not list(tmp_path.glob(".streamflow-output-*.tmp"))


@pytest.mark.parametrize(
    "filename,output_format",
    [
        ("flow.csv", "parquet"),
        ("flow.parquet", "csv"),
    ],
)
def test_conflicting_output_format(filename, output_format):
    with pytest.raises(ValueError, match="conflicts"):
        resolve_output_format(filename, output_format)