"""Optional Plotly hydrographs for streamflow comparisons."""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from streamflow_getter.station_comparison import LINE_COLORS


def plot_comparison(result: Mapping[str, Any]):
    """Create continuous Plotly curves from actual samples (no resampling)."""
    import plotly.graph_objects as go

    figure = go.Figure()
    columns = result["table"]
    for column in columns:
        if not column.endswith("_streamflow_m3s"):
            continue
        name = column.removesuffix("_streamflow_m3s").casefold()
        source = next((key for key in LINE_COLORS if key in name), None)
        if source is None:
            continue
        samples = columns[["valid_time", column]].dropna(subset=[column]).copy()
        samples["valid_time"] = pd.to_datetime(
            samples["valid_time"], utc=True, errors="coerce"
        )
        samples = samples.dropna(subset=["valid_time"])
        if samples.empty:
            continue
        # Explicit ISO-8601 strings avoid nanosecond-epoch numbers in the
        # Plotly FigureWidget used for the clickable explorer.
        plot_times = samples["valid_time"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        figure.add_scatter(
            x=plot_times.tolist(),
            y=samples[column],
            mode="lines" if len(samples) > 1 else "markers",
            name=source,
            line={"color": LINE_COLORS[source], "width": 3},
            marker={"color": LINE_COLORS[source], "size": 9},
            legendrank=list(LINE_COLORS).index(source),
            hovertemplate=(
                "%{x|%Y-%m-%d %H:%M UTC}<br>%{y:.2f} m³/s"
                "<extra>%{fullData.name}</extra>"
            ),
        )
    figure.update_layout(
        title="USGS · NWM · GEOGLOWS streamflow",
        xaxis_title="Valid time (UTC)",
        xaxis={"type": "date", "tickformat": "%b %d\n%H:%M"},
        yaxis_title="Discharge (m³/s)",
        template="plotly_white",
        height=430,
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.3},
        margin={"l": 55, "r": 18, "t": 50, "b": 105},
    )
    return figure
