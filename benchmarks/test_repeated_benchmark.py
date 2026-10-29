"""Tests for repeatable multi-reach NWM benchmarking."""

import argparse
import csv
import io
import numpy as np
import pytest
import xarray as xr

import repeated_benchmark as benchmark
from repeated_benchmark import extract_batch




@pytest.fixture
def sample_dataset():
    """Create a small synthetic NWM-like dataset."""
    return xr.Dataset(
        data_vars={
            "streamflow": (
                "feature_id",
                [7.08, 0.41, 0.0, 16062.71, 0.01],
            ),
        },
        coords={
            "feature_id": [
                1122645,
                3586192,
                7144704,
                14191043,
                23610484,
            ],
        },
    )


def test_batch_extraction(sample_dataset):
    indices = [0, 1, 2, 3, 4]
    reaches = [
        1122645,
        3586192,
        7144704,
        14191043,
        23610484,
    ]

    flows = extract_batch(sample_dataset, indices, reaches)

    np.testing.assert_allclose(
        flows,
        [7.08, 0.41, 0.0, 16062.71, 0.01],
    )


def test_single_reach_extraction(sample_dataset):
    flows = extract_batch(
        sample_dataset,
        [1],
        [3586192],
    )

    np.testing.assert_allclose(flows, [0.41])


def test_incorrect_reach_identity(sample_dataset):
    with pytest.raises(ValueError, match="Feature-ID mismatch"):
        extract_batch(
            sample_dataset,
            [0],
            [3586192],
        )


def test_reach_order_preserved(sample_dataset):
    flows = extract_batch(
        sample_dataset,
        [3, 0, 1],
        [14191043, 1122645, 3586192],
    )

    np.testing.assert_allclose(
        flows,
        [16062.71, 7.08, 0.41],
    )


def test_nonfinite_streamflow_rejected(sample_dataset):
    sample_dataset["streamflow"].values[1] = np.nan

    with pytest.raises(ValueError, match="Non-finite"):
        extract_batch(
            sample_dataset,
            [1],
            [3586192],
        )


def test_main_writes_batch_results(tmp_path, monkeypatch):
    """Verify complete benchmark execution without network access."""
    reaches = [1122645, 3586192]
    indices = [100000, 351819]

    flows = np.array([7.08, 0.41])
    valid_time = "2026-04-19T01:00:00"
    reference_time = "2026-04-19T00:00:00"

    args = argparse.Namespace(
        start_hour=1,
        end_hour=1,
        trials=1,
        reach_ids=reaches,
        output_prefix="repeated_benchmark",
    )

    monkeypatch.setattr(
        benchmark, "RESULTS_DIR", tmp_path
    )

    monkeypatch.setattr(
        benchmark,
        "verify_reach",
        lambda hour, requested, config: indices,
    )

    def fake_local(hour, selected_indices, requested, config):
        assert selected_indices == indices
        assert requested == reaches
        return flows.copy(), valid_time, reference_time

    def fake_remote(hour, selected_indices, requested, config):
        values, valid, reference = fake_local(
            hour, selected_indices, requested, config
        )
        return values, valid, reference, 2, 4000

    def fake_kerchunk(hour, selected_indices, requested, config):
        values, valid, reference = fake_local(
            hour, selected_indices, requested, config
        )
        return values, valid, reference, 2, 2500, 100

    monkeypatch.setattr(
        benchmark, "read_native", fake_local
    )
    monkeypatch.setattr(
        benchmark, "read_native_remote", fake_remote
    )
    monkeypatch.setattr(
        benchmark, "read_kerchunk", fake_kerchunk
    )
    monkeypatch.setattr(
        benchmark,
        "download_native",
        lambda hour, config: (tmp_path / "fake.nc", 14000),
    )

    benchmark.main(args)

    operation_path = tmp_path / "repeated_benchmark.csv"
    flow_path = tmp_path / "repeated_benchmark_flows.csv"

    with operation_path.open(newline="") as file:
        operations = list(csv.DictReader(file))

    with flow_path.open(newline="") as file:
        results = list(csv.DictReader(file))

    assert len(operations) == 4
    assert len(results) == 8

    assert {row["method"] for row in operations} == {
        "kerchunk",
        "native_remote",
        "native_download",
        "native_local",
    }

    assert all(int(row["reach_count"]) == 2 for row in operations)

    for reach in reaches:
        matching = [
            row for row in results
            if int(row["reach_id"]) == reach
        ]

        assert len(matching) == 4

        np.testing.assert_allclose(
            [float(row["streamflow_m3s"]) for row in matching],
            [7.08 if reach == 1122645 else 0.41] * 4,
        )

        assert {row["valid_time"] for row in matching} == {
            valid_time
        }
        assert {row["reference_time"] for row in matching} == {
            reference_time
        }


def test_main_rejects_streamflow_mismatch(tmp_path, monkeypatch):
    """Reject disagreement between retrieval methods."""
    reaches = [1122645, 3586192]
    indices = [100000, 351819]

    args = argparse.Namespace(
        start_hour=1,
        end_hour=1,
        trials=1,
        reach_ids=reaches,
        output_prefix="repeated_benchmark",
    )

    monkeypatch.setattr(benchmark, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(
        benchmark,
        "verify_reach",
        lambda hour, requested, config: indices,
    )

    valid_time = "2026-04-19T01:00:00"
    reference_time = "2026-04-19T00:00:00"

    def fake_local(hour, selected_indices, requested, config):
        return (
            np.array([7.08, 0.41]),
            valid_time,
            reference_time,
        )

    def fake_remote(hour, selected_indices, requested, config):
        return (
            np.array([7.08, 0.41]),
            valid_time,
            reference_time,
            2,
            4000,
        )

    def fake_kerchunk(hour, selected_indices, requested, config):
        return (
            np.array([7.08, 0.99]),  # Deliberate mismatch
            valid_time,
            reference_time,
            2,
            2500,
            100,
        )

    monkeypatch.setattr(benchmark, "read_native", fake_local)
    monkeypatch.setattr(benchmark, "read_native_remote", fake_remote)
    monkeypatch.setattr(benchmark, "read_kerchunk", fake_kerchunk)
    monkeypatch.setattr(
        benchmark,
        "download_native",
        lambda hour, config: (tmp_path / "fake.nc", 14000),
    )

    with pytest.raises(ValueError, match="Streamflow mismatch"):
        benchmark.main(args)

    assert not (tmp_path / "repeated_benchmark.csv").exists()
    assert not (tmp_path / "repeated_benchmark_flows.csv").exists()


def test_main_rejects_timestamp_mismatch(tmp_path, monkeypatch):
    """Reject inconsistent forecast valid times."""
    reaches = [3586192]
    indices = [351819]

    args = argparse.Namespace(
        start_hour=1,
        end_hour=1,
        trials=1,
        reach_ids=reaches,
        output_prefix="repeated_benchmark",
    )

    monkeypatch.setattr(benchmark, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(
        benchmark,
        "verify_reach",
        lambda hour, requested, config: indices,
    )

    reference_time = "2026-04-19T00:00:00"
    correct_time = "2026-04-19T01:00:00"
    incorrect_time = "2026-04-19T02:00:00"

    def fake_local(hour, selected_indices, requested, config):
        return np.array([0.41]), correct_time, reference_time

    def fake_remote(hour, selected_indices, requested, config):
        return np.array([0.41]), correct_time, reference_time, 2, 4000

    def fake_kerchunk(hour, selected_indices, requested, config):
        return (
            np.array([0.41]),
            incorrect_time,
            reference_time,
            2,
            2500,
            100,
        )

    monkeypatch.setattr(benchmark, "read_native", fake_local)
    monkeypatch.setattr(benchmark, "read_native_remote", fake_remote)
    monkeypatch.setattr(benchmark, "read_kerchunk", fake_kerchunk)
    monkeypatch.setattr(
        benchmark,
        "download_native",
        lambda hour, config: (tmp_path / "fake.nc", 14000),
    )

    with pytest.raises(
        ValueError,
        match="Incorrect forecast valid time",
    ):
        benchmark.main(args)

    assert not (tmp_path / "repeated_benchmark.csv").exists()
    assert not (tmp_path / "repeated_benchmark_flows.csv").exists()


def test_native_download_success(tmp_path, monkeypatch):
    """A complete download replaces the destination."""
    monkeypatch.setattr(benchmark, "DATA_DIR", tmp_path)

    content = b"complete-nwm-test-data"

    class FakeResponse(io.BytesIO):
        def __init__(self):
            super().__init__(content)
            self.headers = {"Content-Length": str(len(content))}

    monkeypatch.setattr(
        benchmark.urllib.request,
        "urlopen",
        lambda url, timeout: FakeResponse(),
    )

    path, received = benchmark.download_native(1)

    assert path.read_bytes() == content
    assert received == len(content)
    assert not list(tmp_path.glob(".nwm-download-*.tmp"))


def test_native_download_incomplete_preserves_file(
    tmp_path, monkeypatch
):
    """An incomplete transfer must not replace an existing file."""
    monkeypatch.setattr(benchmark, "DATA_DIR", tmp_path)

    destination = tmp_path / benchmark.filename(1)
    destination.write_bytes(b"existing-valid-file")

    class FakeResponse(io.BytesIO):
        def __init__(self):
            super().__init__(b"incomplete")
            self.headers = {"Content-Length": "100"}

    monkeypatch.setattr(
        benchmark.urllib.request,
        "urlopen",
        lambda url, timeout: FakeResponse(),
    )

    with pytest.raises(IOError, match="Incomplete NWM download"):
        benchmark.download_native(1)

    assert destination.read_bytes() == b"existing-valid-file"
    assert not list(tmp_path.glob(".nwm-download-*.tmp"))

def test_forecast_config_rejects_wrong_identity():
    """Reject incorrect timestamps even when methods agree."""
    config = benchmark.ForecastConfig(
        date="2026-04-20",
        cycle=12,
    )

    # Correct forecast identity.
    config.validate_timestamps(
        1,
        "2026-04-20T13:00:00",
        "2026-04-20T12:00:00",
    )

    # All methods could agree on this incorrect forecast.
    with pytest.raises(
        ValueError,
        match="Incorrect forecast reference time",
    ):
        config.validate_timestamps(
            1,
            "2026-04-19T01:00:00",
            "2026-04-19T00:00:00",
        )

    # Correct reference time, incorrect valid time.
    with pytest.raises(
        ValueError,
        match="Incorrect forecast valid time",
    ):
        config.validate_timestamps(
            1,
            "2026-04-20T14:00:00",
            "2026-04-20T12:00:00",
        )