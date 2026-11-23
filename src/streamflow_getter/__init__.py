"""Download streamflow time series from NWM, NRDS and GEOGLOWS output."""

__version__ = "0.0.1"


def __getattr__(name):
    """Lazily expose the public client without importing heavy dependencies."""
    if name == "StreamflowClient":
        from .api import StreamflowClient

        return StreamflowClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
