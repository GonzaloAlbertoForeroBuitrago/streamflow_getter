"""Regression checks for optional presentation boundaries."""

import subprocess
import sys

import pandas as pd
import pytest


def test_existing_plot_interface_matches_new_renderer():
    pytest.importorskip("plotly")

    from streamflow_getter.station_comparison import (
        LINE_COLORS,
        plot_comparison as legacy_plot,
    )
    from streamflow_getter.visualization.plotly import (
        plot_comparison as new_plot,
    )

    source = next(iter(LINE_COLORS))
    result = {
        "table": pd.DataFrame(
            {
                "valid_time": pd.to_datetime(
                    ["2025-07-04T06:00:00Z", "2025-07-04T07:00:00Z"],
                    utc=True,
                ),
                f"{source}_streamflow_m3s": [1.0, 1.5],
            }
        )
    }

    original = legacy_plot(result)
    new = new_plot(result)

    assert original.to_plotly_json() == new.to_plotly_json()
    assert len(new.data) == 1


def test_backend_import_does_not_load_plotly():
    script = (
        "import sys; "
        "from streamflow_getter import StreamflowClient; "
        "import streamflow_getter.station_comparison; "
        "assert 'plotly' not in sys.modules"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
