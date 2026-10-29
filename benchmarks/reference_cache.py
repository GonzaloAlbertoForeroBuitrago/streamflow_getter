"""Experimental cache loader for NWM Kerchunk references."""

import json


def load_fresh_reference(
    cache_file,
    expected_url,
    metadata_provider,
    downloader,
):
    """Load a reference only when its source metadata is consistent.

    metadata_provider returns current reference_etag and source_generation.
    downloader returns the Kerchunk reference JSON bytes.
    """
    from cache_freshness import compare_metadata
    from cache_manifest import (
        create_cache_record,
        load_cache_record,
        save_cache_record,
    )

    current = metadata_provider()

    if not isinstance(current, dict):
        raise ValueError("Invalid remote metadata")

    required = ("reference_etag", "source_generation")
    if any(not current.get(key) for key in required):
        raise ValueError("Remote metadata is incomplete")

    current = {
        "reference_etag": current["reference_etag"],
        "source_generation": str(current["source_generation"]),
    }

    record = load_cache_record(cache_file, expected_url)

    if record is not None:
        status = compare_metadata(record["manifest"], current)

        if status == "unchanged":
            return record["reference"]

        if status == "source_changed":
            raise ValueError(
                "NWM source generation changed; "
                "reference compatibility must be verified"
            )

        if status == "unknown":
            raise ValueError("Cannot establish cache freshness")

    raw = downloader()

    if isinstance(raw, bytes):
        reference = json.loads(raw)
    elif isinstance(raw, str):
        reference = json.loads(raw)
    else:
        raise TypeError("Downloader must return JSON bytes or text")

    # Check whether remote metadata changed during the download.
    after = metadata_provider()

    if not isinstance(after, dict):
        raise ValueError("Remote metadata is incomplete")

    required = ("reference_etag", "source_generation")

    if any(not after.get(key) for key in required):
        raise ValueError("Remote metadata is incomplete")

    after = {
        "reference_etag": after["reference_etag"],
        "source_generation": str(after["source_generation"]),
    }

    if compare_metadata(current, after) != "unchanged":
        raise ValueError(
            "Remote metadata changed during download"
        )

    new_record = create_cache_record(
        reference,
        expected_url,
        current,
    )

    save_cache_record(cache_file, new_record, expected_url)

    return new_record["reference"]
