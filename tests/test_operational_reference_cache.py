
"""Tests for production NWM reference caching."""

import json

import pytest

from streamflow_getter.reference_cache import (
    compare_metadata,
    create_cache_record,
    load_cache_record,
    load_fresh_reference,
    save_cache_record,
    validate_cache_record,
)


URL = "https://example.org/data.nc"


@pytest.fixture
def valid_reference():
    return {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [URL, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [URL, 100, 200],
        },
    }


@pytest.fixture
def metadata():
    return {
        "reference_etag": "etag-1",
        "source_generation": "gen-1",
    }


def test_metadata_unchanged(metadata):
    assert compare_metadata(metadata, metadata.copy()) == "unchanged"


def test_metadata_source_changed(metadata):
    changed = {**metadata, "source_generation": "gen-2"}
    assert compare_metadata(metadata, changed) == "source_changed"


def test_metadata_reference_changed(metadata):
    changed = {**metadata, "reference_etag": "etag-2"}
    assert compare_metadata(metadata, changed) == "reference_changed"


def test_cache_record_roundtrip(tmp_path, valid_reference, metadata):
    path = tmp_path / "record.json"

    record = create_cache_record(valid_reference, URL, metadata)
    save_cache_record(path, record, URL)

    assert load_cache_record(path, URL) == record


def test_corrupted_cache_rejected(tmp_path):
    path = tmp_path / "record.json"
    path.write_text("{invalid json")

    assert load_cache_record(path, URL) is None


def test_wrong_source_rejected(valid_reference, metadata):
    record = create_cache_record(valid_reference, URL, metadata)

    assert not validate_cache_record(
        record,
        "https://example.org/other.nc",
    )


def test_fresh_cache_reused(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, metadata),
        URL,
    )

    def unexpected_download():
        raise AssertionError("Cache should have been reused")

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        unexpected_download,
    )

    assert result == valid_reference


def test_reference_change_refreshes(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    old_metadata = {
        **metadata,
        "reference_etag": "etag-old",
    }

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, old_metadata),
        URL,
    )

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode(),
    )

    assert result == valid_reference

    updated = load_cache_record(path, URL)
    assert updated["manifest"]["reference_etag"] == "etag-1"


def test_source_generation_change_rejected(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, metadata),
        URL,
    )

    changed = {
        **metadata,
        "source_generation": "gen-2",
    }

    with pytest.raises(ValueError, match="generation changed"):
        load_fresh_reference(
            path,
            URL,
            lambda: changed,
            lambda: json.dumps(valid_reference).encode(),
        )


def test_failed_refresh_preserves_record(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, metadata),
        URL,
    )

    original = path.read_bytes()

    changed = {
        **metadata,
        "reference_etag": "etag-2",
    }

    def failed_download():
        raise ConnectionError("Download failed")

    with pytest.raises(ConnectionError):
        load_fresh_reference(
            path,
            URL,
            lambda: changed,
            failed_download,
        )

    assert path.read_bytes() == original


def test_invalid_download_rejected(tmp_path, metadata):
    path = tmp_path / "record.json"

    with pytest.raises(ValueError):
        load_fresh_reference(
            path,
            URL,
            lambda: metadata,
            lambda: b'{"version":1,"refs":{}}',
        )

    assert not path.exists()



def test_fetch_remote_metadata(monkeypatch):
    """Read reference ETag and source generation."""
    from unittest.mock import MagicMock
    import urllib.request

    from streamflow_getter.reference_cache import fetch_remote_metadata

    s3 = MagicMock()
    s3.info.return_value = {"ETag": "etag-123"}

    response = MagicMock()
    response.headers.get.return_value = "generation-456"

    context = MagicMock()
    context.__enter__.return_value = response

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: context,
    )

    result = fetch_remote_metadata(
        "bucket/reference.json",
        URL,
        s3=s3,
    )

    assert result == {
        "reference_etag": "etag-123",
        "source_generation": "generation-456",
    }

    s3.info.assert_called_once_with("bucket/reference.json")


def test_fetch_remote_metadata_missing_generation(monkeypatch):
    """Missing source-generation metadata must be rejected."""
    from unittest.mock import MagicMock
    import urllib.request

    from streamflow_getter.reference_cache import fetch_remote_metadata

    s3 = MagicMock()
    s3.info.return_value = {"ETag": "etag-123"}

    response = MagicMock()
    response.headers.get.return_value = None

    context = MagicMock()
    context.__enter__.return_value = response

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: context,
    )

    with pytest.raises(ValueError, match="Missing remote"):
        fetch_remote_metadata(
            "bucket/reference.json",
            URL,
            s3=s3,
        )


def test_fetch_remote_metadata_missing_etag(monkeypatch):
    """Missing reference ETag must be rejected."""
    from unittest.mock import MagicMock
    import urllib.request

    from streamflow_getter.reference_cache import fetch_remote_metadata

    s3 = MagicMock()
    s3.info.return_value = {}

    response = MagicMock()
    response.headers.get.return_value = "generation-456"

    context = MagicMock()
    context.__enter__.return_value = response

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: context,
    )

    with pytest.raises(ValueError, match="Missing remote"):
        fetch_remote_metadata(
            "bucket/reference.json",
            URL,
            s3=s3,
        )

def test_metadata_missing_returns_unknown(metadata):
    current = metadata.copy()
    del current["source_generation"]

    assert compare_metadata(metadata, current) == "unknown"


def test_source_change_takes_priority_over_reference_change(metadata):
    current = {
        **metadata,
        "reference_etag": "etag-2",
        "source_generation": "gen-2",
    }

    assert compare_metadata(metadata, current) == "source_changed"

def test_metadata_change_during_download_rejected(
    tmp_path, valid_reference, metadata
):
    """Reject a reference if remote metadata changes during download."""
    path = tmp_path / "record.json"

    before = metadata.copy()
    after = {
        **metadata,
        "reference_etag": "etag-changed",
    }

    snapshots = iter([before, after])

    def metadata_provider():
        return next(snapshots)

    def downloader():
        return json.dumps(valid_reference).encode("utf-8")

    with pytest.raises(ValueError, match="changed during download"):
        load_fresh_reference(
            path,
            URL,
            metadata_provider,
            downloader,
        )

    assert not path.exists()

def test_corrupted_cache_is_refreshed(
    tmp_path, valid_reference, metadata
):
    """Replace a corrupted cache with a validated reference."""
    path = tmp_path / "record.json"
    path.write_text("{invalid json", encoding="utf-8")

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode("utf-8"),
    )

    assert result == valid_reference

    cached = load_cache_record(path, URL)

    assert cached is not None
    assert cached["reference"] == valid_reference

def test_wrong_source_cache_is_refreshed(
    tmp_path, valid_reference, metadata
):
    """Replace cached references pointing to an incorrect source."""
    path = tmp_path / "record.json"

    wrong_reference = json.loads(json.dumps(valid_reference))
    wrong_reference["refs"]["streamflow/0"][0] = (
        "https://example.org/wrong.nc"
    )

    path.write_text(
        json.dumps({
            "reference": wrong_reference,
            "manifest": {},
        }),
        encoding="utf-8",
    )

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode("utf-8"),
    )

    assert result == valid_reference

    cached = load_cache_record(path, URL)
    assert cached is not None
    assert cached["reference"] == valid_reference