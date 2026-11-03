
"""Validation of operational NWM Kerchunk references."""

REQUIRED_KEYS = {
    ".zgroup",
    "feature_id/.zarray",
    "feature_id/0",
    "streamflow/.zarray",
    "streamflow/0",
}


def valid_byte_range(value) -> bool:
    """Check an external Kerchunk byte-range reference."""
    if not isinstance(value, list) or len(value) != 3:
        return False

    url, offset, length = value

    if not isinstance(url, str) or not url.startswith(
        ("https://", "http://", "s3://")
    ):
        return False

    if type(offset) is not int or offset < 0:
        return False

    if type(length) is not int or length <= 0:
        return False

    return True


def validate_reference(reference) -> bool:
    """Validate the observed NWM Kerchunk reference structure."""
    if not isinstance(reference, dict):
        return False

    if reference.get("version") != 1:
        return False

    refs = reference.get("refs")

    if not isinstance(refs, dict):
        return False

    if not REQUIRED_KEYS.issubset(refs):
        return False

    for value in refs.values():
        if isinstance(value, list):
            if not valid_byte_range(value):
                return False
        elif not isinstance(value, str):
            return False

    return True


def valid_source_identity(reference, expected_url) -> bool:
    """Verify that external chunks reference the expected NWM file."""
    if not isinstance(expected_url, str) or not expected_url:
        return False

    if not validate_reference(reference):
        return False

    for value in reference["refs"].values():
        if isinstance(value, list) and value[0] != expected_url:
            return False

    return True
