"""Compare metadata snapshots for cached NWM references."""


def compare_metadata(cached, current):
    """Return a freshness status for two metadata snapshots.

    Both dictionaries must contain:
    - reference_etag
    - source_generation
    """
    required = ("reference_etag", "source_generation")

    for key in required:
        if not cached.get(key) or not current.get(key):
            return "unknown"

    if cached["source_generation"] != current["source_generation"]:
        return "source_changed"

    if cached["reference_etag"] != current["reference_etag"]:
        return "reference_changed"

    return "unchanged"
