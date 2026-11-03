
"""Offline tests for the operational NWM CLI."""

import pandas as pd
import pytest

from streamflow_getter.cli import build_parser, main
from streamflow_getter import operational_nwm, output


@pytest.fixture
def mock_operational(monkeypatch):
    """Mock retrieval and output without network access."""
    calls = {}

    frame = pd.DataFrame({
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
        "streamflow_m3s": [0.41, 0.41],
        "method": ["kerchunk", "kerchunk"],
    })

    def fake_fetch(config, reaches, start_hour, end_hour, **kwargs):
        calls["config"] = config
        calls["reaches"] = reaches
        calls["start_hour"] = start_hour
        calls["end_hour"] = end_hour
        calls["fetch_kwargs"] = kwargs
        return frame

    def fake_write(data, path, **kwargs):
        calls["written_frame"] = data
        calls["output_path"] = path
        calls["write_kwargs"] = kwargs
        return path

    monkeypatch.setattr(
        operational_nwm, "fetch_operational_series", fake_fetch
    )
    monkeypatch.setattr(
        output, "write_timeseries", fake_write
    )

    return calls, frame


def test_operational_cli_defaults(mock_operational):
    calls, frame = mock_operational

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--out", "forecast.csv",
    ])

    assert result == 0
    assert calls["config"].date == "2026-04-19"
    assert calls["config"].cycle == 0
    assert calls["reaches"] == [3586192]
    assert calls["start_hour"] == 1
    assert calls["end_hour"] == 18
    assert calls["fetch_kwargs"]["include_t0"] is True
    assert calls["written_frame"] is frame
    assert calls["output_path"] == "forecast.csv"


def test_operational_cli_no_t0(mock_operational):
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--no-t0",
        "--out", "forecast.csv",
    ])

    assert calls["fetch_kwargs"]["include_t0"] is False


def test_operational_cli_parquet_and_cache(mock_operational):
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "12",
        "--reach", "3586192",
        "--reach", "1122645",
        "--start-hour", "2",
        "--end-hour", "6",
        "--cache-dir", "/tmp/nwm-cache",
        "--format", "parquet",
        "--out", "forecast.parquet",
    ])

    assert calls["config"].cycle == 12
    assert calls["reaches"] == [3586192, 1122645]
    assert calls["start_hour"] == 2
    assert calls["end_hour"] == 6
    assert calls["fetch_kwargs"]["cache_dir"] == "/tmp/nwm-cache"
    assert calls["write_kwargs"]["output_format"] == "parquet"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--date", "2026-04-19", "--out", "forecast.csv"],
        ["--reach", "3586192", "--out", "forecast.csv"],
        ["--date", "2026-04-19", "--reach", "3586192"],
        [
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--format", "json",
            "--out", "forecast.json",
        ],
    ],
)
def test_operational_cli_rejects_invalid_arguments(arguments):
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["nwm-operational", *arguments])

    assert exc.value.code == 2


def test_existing_retrospective_parser():
    parser = build_parser()

    args = parser.parse_args([
        "nwm",
        "--gage", "01646500",
        "--version", "2.1",
        "--start", "2015-05-23",
        "--end", "2015-06-24",
        "--out", "flow.csv",
    ])

    assert args.source == "nwm"
    assert args.gage == ["01646500"]
    assert args.nwm_version == "2.1"
    assert args.out == "flow.csv"



@pytest.mark.parametrize("extension", ["csv", "parquet"])
def test_operational_cli_writes_real_output(
    tmp_path, monkeypatch, extension
):
    """Verify CLI integration with the actual CSV/Parquet writer."""
    from streamflow_getter import operational_nwm

    frame = pd.DataFrame({
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

    def fake_fetch(config, reaches, start_hour, end_hour, **kwargs):
        assert reaches == [3586192]
        assert kwargs["include_t0"] is True
        return frame

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )

    destination = tmp_path / f"forecast.{extension}"

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--out", str(destination),
    ])

    assert result == 0
    assert destination.exists()

    if extension == "csv":
        restored = pd.read_csv(destination)
    else:
        restored = pd.read_parquet(destination)

    assert len(restored) == 2
    assert restored["lead_hour"].tolist() == [0, 1]
    assert restored["product"].tolist() == [
        "analysis_assim",
        "short_range",
    ]
    assert restored["reference_time"].tolist() == [
        "2026-04-18T21:00:00",
        "2026-04-19T00:00:00",
    ]



def test_retrospective_cli_execution(tmp_path, monkeypatch):
    """Preserve existing retrospective retrieval and CSV output."""
    from streamflow_getter import nwm

    calls = {}

    class FakeDataset:
        pass

    dataset = FakeDataset()

    def fake_open(version):
        calls["version"] = version
        return dataset

    def fake_gages(gages, ds):
        assert ds is dataset
        assert gages == ["01646500"]
        return {"01646500": 1122645}

    def fake_fetch(reaches, start, end, variable, *, ds):
        assert ds is dataset
        calls["reaches"] = reaches
        calls["start"] = start
        calls["end"] = end
        calls["variable"] = variable

        return pd.DataFrame({
            "time": ["2015-05-23T00:00:00"],
            "feature_id": [1122645],
            "streamflow": [7.08],
        })

    monkeypatch.setattr(nwm, "open_chrtout", fake_open)
    monkeypatch.setattr(nwm, "gages_to_reaches", fake_gages)
    monkeypatch.setattr(nwm, "fetch", fake_fetch)

    destination = tmp_path / "retrospective.csv"

    result = main([
        "nwm",
        "--gage", "01646500",
        "--version", "2.1",
        "--start", "2015-05-23",
        "--end", "2015-06-24",
        "--out", str(destination),
    ])

    assert result == 0
    assert calls == {
        "version": "2.1",
        "reaches": [1122645],
        "start": "2015-05-23",
        "end": "2015-06-24",
        "variable": "streamflow",
    }

    restored = pd.read_csv(destination)

    assert restored["feature_id"].tolist() == [1122645]
    assert restored["streamflow"].tolist() == [7.08]



@pytest.mark.parametrize(
    "filename,output_format",
    [
        ("forecast.txt", None),
        ("forecast.csv", "parquet"),
        ("forecast.parquet", "csv"),
    ],
)
def test_cli_rejects_invalid_output_before_fetch(
    tmp_path, monkeypatch, filename, output_format
):
    """Invalid output configuration must not trigger retrieval."""
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    destination = tmp_path / filename

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--out", str(destination),
    ]

    if output_format is not None:
        arguments.extend(["--format", output_format])

    with pytest.raises(ValueError):
        main(arguments)

    assert not destination.exists()


def test_cli_rejects_existing_output_before_fetch(
    tmp_path, monkeypatch
):
    """Existing output must be preserved without retrieval."""
    from streamflow_getter import operational_nwm

    destination = tmp_path / "forecast.csv"
    destination.write_text("existing-data")

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(FileExistsError):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--out", str(destination),
        ])

    assert destination.read_text() == "existing-data"



@pytest.mark.parametrize(
    "date,cycle",
    [
        ("2026-02-30", "0"),
        ("2026/04/19", "0"),
        ("2026-04-19", "24"),
        ("2026-04-19", "-1"),
    ],
)
def test_cli_rejects_invalid_configuration_before_fetch(
    monkeypatch, tmp_path, date, cycle
):
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError):
        main([
            "nwm-operational",
            "--date", date,
            "--cycle", cycle,
            "--reach", "3586192",
            "--out", str(tmp_path / "forecast.csv"),
        ])


@pytest.mark.parametrize(
    "start_hour,end_hour",
    [
        ("0", "1"),
        ("2", "1"),
        ("-1", "2"),
    ],
)
def test_cli_rejects_invalid_hours_before_fetch(
    monkeypatch, tmp_path, start_hour, end_hour
):
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--start-hour", start_hour,
            "--end-hour", end_hour,
            "--out", str(tmp_path / "forecast.csv"),
        ])
