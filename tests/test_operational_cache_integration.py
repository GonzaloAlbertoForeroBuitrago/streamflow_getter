
"""Offline integration tests for cached operational Kerchunk retrieval."""

import json
from unittest.mock import MagicMock

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    read_kerchunk_forecast,
)


def test_cached_kerchunk_reuses_reference(tmp_path, monkeypatch):
    import fsspec
    import s3fs

    from streamflow_getter import reference_cache

    config = ForecastConfig()
    url = config.native_url(1)

    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }

    raw = json.dumps(reference).encode()

    s3 = MagicMock()
    remote_context = MagicMock()
    remote_context.__enter__.return_value.read.return_value = raw
    s3.open.return_value = remote_context

    monkeypatch.setattr(
        s3fs,
        "S3FileSystem",
        lambda **kwargs: s3,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
            "source_generation": "gen-1",
        },
    )

    filesystem = MagicMock()
    filesystem.get_mapper.return_value = {}

    monkeypatch.setattr(
        fsspec,
        "filesystem",
        lambda *args, **kwargs: filesystem,
    )

    ds = xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [0.41],
            ),
        },
        coords={
            "feature_id": [3586192],
            "time": [np.datetime64("2026-04-19T01:00:00")],
            "reference_time": [
                np.datetime64("2026-04-19T00:00:00")
            ],
        },
    )

    dataset_context = MagicMock()
    dataset_context.__enter__.return_value = ds

    monkeypatch.setattr(
        xr,
        "open_zarr",
        lambda *args, **kwargs: dataset_context,
    )

    first = read_kerchunk_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    second = read_kerchunk_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    assert first["streamflow_m3s"] == second["streamflow_m3s"]
    assert first["streamflow_m3s"][3586192] == 0.41

    # The reference JSON should only be downloaded once.
    assert s3.open.call_count == 1

    cache_file = (
        tmp_path
        / "nwm.20260419"
        / "short_range"
        / f"{config.filename(1)}.cache.json"
    )

    assert cache_file.exists()



def test_cached_reader_rejects_source_generation_change(
    tmp_path, monkeypatch
):
    """A changed source generation must stop cached retrieval."""
    from streamflow_getter import reference_cache
    from streamflow_getter.reference_cache import (
        create_cache_record,
        save_cache_record,
    )

    config = ForecastConfig()
    url = config.native_url(1)

    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }

    cache_file = (
        tmp_path
        / config.date_folder
        / config.product
        / f"{config.filename(1)}.cache.json"
    )

    save_cache_record(
        cache_file,
        create_cache_record(
            reference,
            url,
            {
                "reference_etag": "etag-1",
                "source_generation": "generation-1",
            },
        ),
        url,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
            "source_generation": "generation-2",
        },
    )

    with pytest.raises(ValueError, match="generation changed"):
        read_kerchunk_forecast(
            config,
            1,
            [3586192],
            cache_dir=tmp_path,
        )


def test_cached_reader_rejects_missing_metadata(
    tmp_path, monkeypatch
):
    """Incomplete metadata must not be treated as fresh."""
    from streamflow_getter import reference_cache

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
        },
    )

    with pytest.raises(ValueError, match="incomplete"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
            cache_dir=tmp_path,
        )



def test_cached_reader_refreshes_changed_reference(
    tmp_path, monkeypatch
):
    """A changed reference ETag refreshes the cached record."""
    import json
    from unittest.mock import MagicMock

    import fsspec
    import s3fs
    import xarray as xr

    from streamflow_getter import reference_cache
    from streamflow_getter.reference_cache import (
        create_cache_record,
        load_cache_record,
        save_cache_record,
    )

    config = ForecastConfig()
    url = config.native_url(1)

    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }

    cache_file = (
        tmp_path
        / config.date_folder
        / config.product
        / f"{config.filename(1)}.cache.json"
    )

    save_cache_record(
        cache_file,
        create_cache_record(
            reference,
            url,
            {
                "reference_etag": "etag-old",
                "source_generation": "gen-1",
            },
        ),
        url,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-new",
            "source_generation": "gen-1",
        },
    )

    s3 = MagicMock()
    remote_context = MagicMock()
    remote_context.__enter__.return_value.read.return_value = (
        json.dumps(reference).encode()
    )
    s3.open.return_value = remote_context

    monkeypatch.setattr(
        s3fs,
        "S3FileSystem",
        lambda **kwargs: s3,
    )

    filesystem = MagicMock()
    filesystem.get_mapper.return_value = {}

    monkeypatch.setattr(
        fsspec,
        "filesystem",
        lambda *args, **kwargs: filesystem,
    )

    ds = xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [0.41],
            ),
        },
        coords={
            "feature_id": [3586192],
            "time": [np.datetime64("2026-04-19T01:00:00")],
            "reference_time": [
                np.datetime64("2026-04-19T00:00:00")
            ],
        },
    )

    dataset_context = MagicMock()
    dataset_context.__enter__.return_value = ds

    monkeypatch.setattr(
        xr,
        "open_zarr",
        lambda *args, **kwargs: dataset_context,
    )

    result = read_kerchunk_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    assert result["streamflow_m3s"][3586192] == 0.41
    assert result["method"] == "kerchunk"

    updated = load_cache_record(cache_file, url)

    assert updated is not None
    assert updated["manifest"]["reference_etag"] == "etag-new"
    assert updated["manifest"]["source_generation"] == "gen-1"

    s3.open.assert_called_once()



def test_analysis_t0_cache_separate_from_forecast(
    tmp_path, monkeypatch
):
    """Analysis t0 and forecast references use separate cache records."""
    import json
    from unittest.mock import MagicMock

    import fsspec
    import s3fs

    from streamflow_getter import reference_cache

    config = ForecastConfig()

    def make_reference(url):
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

    s3 = MagicMock()

    def open_reference(path, mode):
        if path == config.analysis_reference_path():
            url = config.analysis_native_url()
        else:
            assert path == config.reference_path(1)
            url = config.native_url(1)

        context = MagicMock()
        context.__enter__.return_value.read.return_value = (
            json.dumps(make_reference(url)).encode()
        )
        return context

    s3.open.side_effect = open_reference

    monkeypatch.setattr(
        s3fs,
        "S3FileSystem",
        lambda **kwargs: s3,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
            "source_generation": "gen-1",
        },
    )

    filesystem = MagicMock()
    filesystem.get_mapper.return_value = {}

    monkeypatch.setattr(
        fsspec,
        "filesystem",
        lambda *args, **kwargs: filesystem,
    )

    def open_dataset(*args, **kwargs):
        # Use separate valid timestamps for analysis and forecast.
        hour = open_dataset.calls
        open_dataset.calls += 1

        valid = (
            "2026-04-19T00:00:00"
            if hour == 0
            else "2026-04-19T01:00:00"
        )
        reference = (
            "2026-04-18T21:00:00"
            if hour == 0
            else "2026-04-19T00:00:00"
        )

        ds = xr.Dataset(
            {"streamflow": ("feature_id", [0.41])},
            coords={
                "feature_id": [3586192],
                "time": [np.datetime64(valid)],
                "reference_time": [np.datetime64(reference)],
            },
        )

        context = MagicMock()
        context.__enter__.return_value = ds
        return context

    open_dataset.calls = 0

    monkeypatch.setattr(
        xr,
        "open_zarr",
        open_dataset,
    )

    analysis = read_kerchunk_forecast(
        config, 0, [3586192], cache_dir=tmp_path
    )
    forecast = read_kerchunk_forecast(
        config, 1, [3586192], cache_dir=tmp_path
    )

    analysis_path = (
        tmp_path
        / config.date_folder
        / "analysis_assim"
        / f"{config.analysis_filename()}.cache.json"
    )

    forecast_path = (
        tmp_path
        / config.date_folder
        / "short_range"
        / f"{config.filename(1)}.cache.json"
    )

    assert analysis_path.exists()
    assert forecast_path.exists()
    assert analysis_path != forecast_path

    assert analysis["product"] == "analysis_assim"
    assert forecast["product"] == "short_range"
