"""Streaming integrity checks for exported scientific data."""

from hashlib import sha256
from pathlib import Path


def file_integrity(path: str | Path) -> dict[str, str | int]:
    """Return SHA-256 and actual byte count without loading the whole file."""
    digest = sha256()
    size_bytes = 0

    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)

    return {
        "algorithm": "sha256",
        "sha256": digest.hexdigest(),
        "size_bytes": size_bytes,
    }
