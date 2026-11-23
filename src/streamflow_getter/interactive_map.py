"""Two independent Jupyter maps for a version-aware streamflow study.

The fixed station map and the click-to-query explorer never share plotted
selection state. Network resolution and streamflow retrieval stay in the
existing backend adapters, not in notebook cells.
"""

from __future__ import annotations

import asyncio
from html import escape
from time import perf_counter
from typing import Any

from streamflow_getter.station_comparison import LINE_COLORS, plot_comparison


def _valid_line(coords: Any) -> bool:
    """Validate geographic line coordinates without constructing GEOS polygons."""
    from math import isfinite

    if not isinstance(coords, (tuple, list)) or len(coords) < 2:
        return False
    try:
        return all(
            len(position) >= 2
            and all(isfinite(float(value)) for value in position[:2])
            and -180 <= float(position[0]) <= 180
            and -90 <= float(position[1]) <= 90
            for position in coords
        )
    except (TypeError, ValueError, IndexError):
        return False


def _river_feature(line: dict) -> dict:
    return {"type": "Feature", "properties": {}, "geometry": line}


def _river_features(obj: Any) -> list[dict]:
    """Extract valid river lines; invalid polygon rings are never forwarded."""
    if not isinstance(obj, dict):
        return []
    kind = obj.get("type")
    if kind in ("FeatureCollection", "GeometryCollection"):
        children = obj.get(
            "features" if kind == "FeatureCollection" else "geometries", []
        )
        return [feature for child in children for feature in _river_features(child)]
    if kind == "Feature":
        return _river_features(obj.get("geometry"))
    if kind == "LineString":
        return [_river_feature(obj)] if _valid_line(obj.get("coordinates")) else []
    if kind == "MultiLineString":
        return [
            _river_feature({"type": "LineString", "coordinates": line})
            for line in obj.get("coordinates", [])
            if _valid_line(line)
        ]
    return []


def _geoglows_status_warning(metadata: dict) -> str:
    error = metadata.get("geoglows", {}).get("selection_error")
    return f"<br>GEOGLOWS selection unavailable: {escape(str(error))}" if error else ""


class StreamflowMap:
    """Show an immutable station view and a separately clickable river view."""

    INTERFACE_VERSION = 23  # Date input, stable UTC axes and resilient click redraw.

    def __init__(self, study, initial: dict[str, Any]) -> None:
        from ipyleaflet import CircleMarker, GeoJSON, LayerGroup, Map
        from ipywidgets import Button, HTML, Layout, Output, Text, VBox
        from plotly.graph_objects import FigureWidget

        self._circle = CircleMarker
        self._geojson = GeoJSON
        self.study = study
        self.station_result = initial
        self.result = None  # Explorer: no previous USGS data on startup.
        self.busy = False
        self.task = None
        self._explorer_study = study
        self._explorer_reference = None
        reference = getattr(study, "reference", None)
        reference_value = (
            reference.strftime("%Y-%m-%dT%H:%M:%SZ") if reference is not None else ""
        )
        self.reference_input = Text(
            value=reference_value,
            description="UTC date/time",
            placeholder="2025-07-04 or 2025-07-04T06:00:00Z",
            layout=Layout(width="485px"),
            style={"description_width": "initial"},
        )

        point = initial["metadata"]["point_epsg4326"]
        center = (point["latitude"], point["longitude"])
        options = {
            "center": center,
            "zoom": 12,
            "scroll_wheel_zoom": True,
            "layout": Layout(height="390px", width="100%"),
        }
        self.station_map = Map(**options)
        self.station_rivers = LayerGroup()
        self.station_map.add(self.station_rivers)
        self.station_status = HTML()
        self.station_hydrograph = Output(layout=Layout(width="100%"))
        self.station_save = Button(description="Save USGS station result")
        self.station_save.on_click(self._on_save_station)

        self.map = Map(**options)  # Existing public name is the clickable map.
        self.rivers = LayerGroup()
        self.map.add(self.rivers)
        self.status = HTML(value="Enter a UTC hour, then click the map.")
        try:
            self.hydrograph = FigureWidget()
        except ImportError as exc:
            raise ImportError(
                "Plotly's live river hydrograph requires anywidget. "
                "Run: micromamba run -n streamflow-getter-guide "
                "python -m pip install anywidget; restart the kernel."
            ) from exc
        self.hydrograph.update_layout(
            title="Click a location to load streamflow",
            height=430,
            xaxis_title="Valid time (UTC)",
            yaxis_title="Discharge (m³/s)",
            xaxis={"type": "date", "tickformat": "%b %d\n%H:%M"},
        )
        self.click_save = Button(description="Save clicked result", disabled=True)
        self.click_save.on_click(self._on_save_click)

        self.widget = VBox(
            [
                HTML("<h3>1 · USGS station — fixed reference</h3>"),
                self.station_status,
                self.station_map,
                self.station_hydrograph,
                self.station_save,
                HTML("<h3>2 · River explorer — click any location</h3>"),
                self.reference_input,
                self.status,
                self.map,
                self.hydrograph,
                self.click_save,
            ]
        )
        self._draw_station(initial)
        self.map.on_interaction(self._on_interaction)

    @staticmethod
    def _river_geojson(value: Any) -> dict | None:
        """Keep river lines only; never send malformed polygon rings to Leaflet."""
        raw = getattr(value, "__geo_interface__", value)
        features = _river_features(raw)
        if features or (
            isinstance(raw, dict)
            and raw.get("type") == "FeatureCollection"
            and raw.get("features") == []
        ):
            return {"type": "FeatureCollection", "features": features}
        return None

    def _layers_for(self, item: dict[str, Any]) -> tuple:
        """Render only the geometries present in this particular result."""
        ids = item["metadata"]["ids"]
        point = item["metadata"]["point_epsg4326"]
        color = LINE_COLORS["usgs"] if ids["usgs"] else "#64748B"
        layers = [
            self._circle(
                location=(point["latitude"], point["longitude"]),
                radius=6,
                color=color,
                fill_color=color,
                fill_opacity=0.9,
            )
        ]
        nwm_lines = self._river_geojson(item.get("nwm_geojson"))
        if nwm_lines:
            layers.append(
                self._geojson(
                    data=nwm_lines,
                    style={"color": LINE_COLORS["analysis_assim"], "weight": 6},
                    name=f"NWM {ids['nwm']}",
                )
            )
        geometry = item.get("geoglows_geometry")
        geo_lines = self._river_geojson(geometry) if geometry is not None else None
        if geo_lines:
            layers.append(
                self._geojson(
                    data=geo_lines,
                    style={"color": LINE_COLORS["geoglows"], "weight": 5},
                    name=f"GEOGLOWS {ids['geoglows']}",
                )
            )
        return tuple(layers)

    @staticmethod
    def _status_for(item: dict[str, Any]) -> str:
        metadata = item["metadata"]
        ids = metadata["ids"]
        drainage = metadata["drainage_area_comparison"]
        area = (
            drainage["message"]
            if drainage["available"]
            else "USGS–GEOGLOWS area comparison unavailable"
        )
        timing = metadata.get("timings_seconds", {})
        request = timing.get("total_request_wall")
        elapsed = (
            f" · query {request:.2f} s" if isinstance(request, (int, float)) else ""
        )
        window = metadata.get("utc_window", {})
        utc_range = (
            f"<br>UTC: {escape(window['start'])} → {escape(window['end'])}"
            if window.get("start") and window.get("end")
            else ""
        )
        warning = (
            " · <b>crosswalk unverified for this NWM version</b>"
            if ids["usgs"]
            and ids["nwm"] is not None
            and not metadata["nwm"]["gage_crosswalk_verified_for_version"]
            else ""
        )
        geoglows_warning = _geoglows_status_warning(metadata)
        saved = (
            f"Saved: {escape(str(item['folder']))}"
            if item.get("folder") is not None
            else "Not saved (use the button below)"
        )
        return (
            f"<b>USGS:</b> {escape(str(ids['usgs'] or 'not associated'))} · "
            f"<b>NWM:</b> {escape(str(ids['nwm']))} · "
            f"<b>GEOGLOWS:</b> {escape(str(ids['geoglows']))}"
            f"<br><small>{escape(area)}{elapsed}{warning}{utc_range}"
            f"{geoglows_warning}<br>{saved}</small>"
        )

    @staticmethod
    def _draw_plot(output, item: dict[str, Any]) -> None:
        from IPython.display import clear_output, display

        figure = plot_comparison(item)
        if hasattr(output, "batch_update"):
            # FigureWidget remains mounted in D2; update its data in place.
            # This avoids VS Code dropping async display() MIME messages.
            if figure is not None:
                with output.batch_update():
                    output.data = ()
                    output.add_traces(list(figure.data))
                    output.update_layout(**figure.layout.to_plotly_json())
                    if hasattr(output, "update_xaxes"):
                        output.update_xaxes(type="date", tickformat="%b %d\n%H:%M")
        else:
            with output:
                clear_output(wait=True)
                display(figure)

    def _draw_station(self, item: dict[str, Any]) -> None:
        self.station_rivers.layers = self._layers_for(item)
        self.station_status.value = self._status_for(item)
        self._draw_plot(self.station_hydrograph, item)

    def _display(self, item: dict[str, Any]) -> None:
        """Replace explorer content without mutating the station reference."""
        # Plot first: malformed optional map geometry must never suppress the
        # retrieved hydrograph or prevent the next independent click.
        self._draw_plot(self.hydrograph, item)
        overlay_warning = ""
        try:
            self.rivers.layers = self._layers_for(item)
        except Exception as exc:  # Optional display: never discard retrieved data.
            self.rivers.layers = ()
            overlay_warning = (
                "<br><small>Map overlay unavailable: "
                f"{escape(type(exc).__name__ + ': ' + str(exc))}</small>"
            )
        self.status.value = (
            self._status_for(item)
            + f"<br><small>Plotted series: {len(self.hydrograph.data)}</small>"
            + overlay_warning
        )
        self.result = item
        self.click_save.disabled = False

    def _clear_selection(self) -> None:
        self.result = None
        self.click_save.disabled = True
        self.rivers.layers = ()
        with self.hydrograph.batch_update():
            self.hydrograph.data = ()
            self.hydrograph.layout.title = "Retrieving new location…"

    async def _query_point(
        self, lat: float, lon: float, reference_utc: str = ""
    ) -> None:
        started = perf_counter()
        try:
            # The fixed USGS map keeps its own study and date. For the explorer,
            # a changed UTC date creates a separate, version-aware study.
            if reference_utc and reference_utc != self._explorer_reference:
                self._explorer_study = await asyncio.to_thread(
                    self.study.for_reference, reference_utc
                )
                self._explorer_reference = reference_utc
            item = await asyncio.to_thread(self._explorer_study.compare_point, lon, lat)
            item["metadata"].setdefault("timings_seconds", {})["click_end_to_end"] = (
                perf_counter() - started
            )
            self._display(item)
        except Exception as exc:
            self.status.value = f"<b>Click failed:</b> {escape(str(exc))}"
        finally:
            self.busy = False

    def _on_interaction(self, **event) -> None:
        if event.get("type") != "click" or self.busy:
            return
        lat, lon = map(float, event["coordinates"])
        self._clear_selection()  # Old USGS plot disappears immediately.
        self.busy = True
        self.status.value = f"Retrieving at {lat:.4f}, {lon:.4f}…"
        self.task = asyncio.get_running_loop().create_task(
            self._query_point(lat, lon, self.reference_input.value.strip())
        )

    def _save(self, item: dict[str, Any] | None, target) -> None:
        if item is None:
            return
        try:
            self.study.save_record(item)
            target.value = self._status_for(item)
        except Exception as exc:
            target.value = f"<b>Save failed:</b> {escape(str(exc))}"

    def _on_save_station(self, _button) -> None:
        self._save(self.station_result, self.station_status)

    def _on_save_click(self, _button) -> None:
        self._save(self.result, self.status)

    def close(self) -> None:
        """Unregister callbacks; leave completed output data in memory."""
        self.map.on_interaction(self._on_interaction, remove=True)
        self.widget.close()
        self.hydrograph.close()
