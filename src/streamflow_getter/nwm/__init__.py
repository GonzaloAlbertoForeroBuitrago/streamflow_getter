"""National Water Model integration for streamflow_getter.

The retrospective API remains available from this package for backward
compatibility, while operational streamflow retrieval lives in
``streamflow_getter.nwm.streamflow``.
"""

from .retrospective import (
    CHRTOUT_URLS,
    fetch,
    gages_to_reaches,
    open_chrtout,
)

__all__ = [
    "CHRTOUT_URLS",
    "fetch",
    "gages_to_reaches",
    "open_chrtout",
]
