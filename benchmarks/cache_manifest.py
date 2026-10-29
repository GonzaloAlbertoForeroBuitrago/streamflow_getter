"""Create and validate metadata manifests for cached references."""

import hashlib
import json
import os
import tempfile
from pathlib import Path




def sha256_bytes(data):
    """Return SHA-256 digest of reference JSON bytes."""
    return hashlib.sha256(data).hexdigest()


def create_manifest(reference_bytes, expected_url, metadata):
    """Create a manifest for a validated reference."""
    if not isinstance(reference_bytes, bytes):
        raise TypeError("reference_bytes must be bytes")

    if not isinstance(expected_url, str) or not expected_url:
        raise ValueError("expected_url is required")

    required = ("reference_etag", "source_generation")

    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary")

    if any(not metadata.get(key) for key in required):
        raise ValueError("Required metadata is missing")

    return {
        "schema_version": 1,
        "source_url": expected_url,
        "reference_sha256": sha256_bytes(reference_bytes),
        "reference_etag": metadata["reference_etag"],
        "source_generation": str(metadata["source_generation"]),
    }


def validate_manifest(manifest, reference_bytes, expected_url):
    """Validate manifest structure, identity, and local digest."""
    if not isinstance(manifest, dict):
        return False

    if manifest.get("schema_version") != 1:
        return False

    if manifest.get("source_url") != expected_url:
        return False

    if not isinstance(reference_bytes, bytes):
        return False

    if not manifest.get("reference_etag"):
        return False

    if not manifest.get("source_generation"):
        return False

    return manifest.get("reference_sha256") == sha256_bytes(
        reference_bytes
    )
def create_cache_record(reference, expected_url, metadata):
    """Bundle a validated reference and its metadata."""
    from reference_validation import (
        validate_reference,
        valid_source_identity,
    )

    if not validate_reference(reference):
        raise ValueError("Invalid reference structure")

    if not valid_source_identity(reference, expected_url):
        raise ValueError("Incorrect reference source")

    raw = json.dumps(
        reference, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    manifest = create_manifest(raw, expected_url, metadata)

    return {
        "manifest": manifest,
        "reference": reference,
    }


def validate_cache_record(record, expected_url):
    """Validate a complete cached reference record."""
    from reference_validation import (
        validate_reference,
        valid_source_identity,
    )

    if not isinstance(record, dict):
        return False

    reference = record.get("reference")
    manifest = record.get("manifest")

    if not validate_reference(reference):
        return False

    if not valid_source_identity(reference, expected_url):
        return False

    raw = json.dumps(
        reference, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    return validate_manifest(manifest, raw, expected_url)



def save_cache_record(path, record, expected_url):
    """Atomically save a validated single-file cache record."""
    if not validate_cache_record(record, expected_url):
        raise ValueError("Invalid cache record")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".cache-record-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(record, temporary, sort_keys=True)

        os.replace(temporary_path, path)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_cache_record(path, expected_url):
    """Return a validated cache record or None."""
    path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as file:
            record = json.load(file)

        if validate_cache_record(record, expected_url):
            return record

    except (OSError, UnicodeError, ValueError, TypeError):
        pass

    return None