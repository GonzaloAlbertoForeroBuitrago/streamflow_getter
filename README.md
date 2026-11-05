# streamflow_getter

Download streamflow time series for specific river reaches from public
hydrologic model output, using one command-line tool. A single-page map
website will sit on top of the same tool, so anything the website does, the
CLI can do.

> **Status:** early development. The `nwm` command works (CONUS retrospective v3.0 and v2.1, by reach or USGS gage).

## Goal

Pick a reach, pick a date range, get a time series file.

| Source | Reach ID | Status |
|---|---|---|
| NOAA National Water Model (NWM) | `feature_id` (COMID) | working (v3.0 retrospective) |
| NextGen Research DataStream (NRDS) | NextGen hydrofabric IDs (`wb-*`, `cat-*`) | planned |
| GEOGLOWS | `LINKNO` | planned |

Each source uses a different hydrofabric, so each gets its own adapter that
turns a reach ID into that source's native lookup. Crosswalks between
hydrofabrics come later.

## Planned usage

```bash
# NWM streamflow for two reaches, as CSV
streamflow-getter nwm --reach 101 --reach 179 \
    --start 2020-01-01 --end 2020-01-31 --out flow.csv

# ...or by USGS gage ID, from the older v2.1 retrospective
streamflow-getter nwm --gage 01646500 --version 2.1 \
    --start 2015-05-23 --end 2015-06-24 --out flow.csv
```

Flags may change. Output columns: `time` (UTC), `feature_id`, `streamflow` (m³/s).
Background on the NWM network and data: [docs/nwm-notes.md](docs/nwm-notes.md).


## Operational NWM — short-range CONUS

The `nwm-operational` command retrieves NWM short-range CONUS streamflow forecasts. It uses Kerchunk first, with controlled native NetCDF fallback. Analysis `t0` is included by default.

The command supports direct NWM feature IDs, USGS gage IDs through RouteLink, and geographic point selection.

Install the optional spatial dependencies:

    uv sync --extra spatial


### Operational NWM product configuration

The Python library currently supports these validated operational
NWM configurations:

| Product | Domain | Cycles (UTC) | Forecast leads |
|---|---|---|---|
| `short_range` | CONUS | 00–23 hourly | f001–f018 |
| `medium_range_mem1` | CONUS | 00, 06, 12, 18 | f001–f240 |

The `medium_range_mem1` configuration uses:

- NOAA directory: `medium_range_mem1`
- Filename product: `medium_range`
- Channel family: `channel_rt_1`
- Analysis t0 source: `analysis_assim`

Example Python usage:

    from streamflow_getter.operational_nwm import (
        ForecastConfig,
        fetch_operational_series,
    )

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
        domain="conus",
    )

    frame = fetch_operational_series(
        config,
        [3586192],
        start_hour=1,
        end_hour=2,
        include_t0=True,
    )

    print(frame)

The medium-range configuration has been validated against real NOAA
data for April 19, 2026, cycle t00z, feature ID 3586192,
including analysis t0 and forecast hours f001–f002.

Kerchunk-first retrieval succeeded for all three time steps.
The native NetCDF reader returned the same streamflow value as
Kerchunk for f001.

Product-specific cycle and forecast-hour validation prevents
unsupported requests from reaching remote retrieval.

The command-line interface currently defaults to short-range
CONUS and does not yet expose product selection.

Other ensemble members, domains, and forecast products require
separate validation before being enabled.


### Geographic point selection

Example:

    streamflow-getter nwm-operational \
      --date 2026-04-19 \
      --cycle 0 \
      --point -99.3217121935161 30.0699307434853 \
      --hydrofabric /path/to/NWM_v3_hydrofabric.gdb \
      --max-distance-m 500 \
      --start-hour 1 \
      --end-hour 1 \
      --out forecast.csv

Point coordinates are longitude and latitude in EPSG:4326. The command selects the nearest NWM channel within the specified maximum distance, using actual CONUS hydrofabric geometries.

The nearest geographic channel is not necessarily the correct hydrologic reach, particularly near confluences.

Direct selection using `--reach` and USGS station selection using `--gage` are also supported. Gage selection requires `--routelink PATH`.

CSV and Parquet outputs are supported. Use `--no-t0` to exclude the analysis-assimilation initial timestep.

Operational retrieval is currently limited to short-range CONUS. Other products, domains, and historical model-version compatibility remain under development.



### Geographic bounding-box selection

The operational CLI can select all NWM channel reaches intersecting
a geographic bounding box.

Coordinates must be provided in EPSG:4326 as:

    --bbox WEST SOUTH EAST NORTH

Example:

    streamflow-getter nwm-operational \
      --date 2026-04-19 \
      --cycle 0 \
      --bbox -99.35 30.05 -99.30 30.09 \
      --hydrofabric /path/to/NWM_v3_hydrofabric.gdb \
      --max-reaches 100 \
      --start-hour 1 \
      --end-hour 1 \
      --out bbox_forecast.csv

The selection uses actual NWM hydrofabric channel geometries.
All intersecting reaches are returned; selections are not silently
truncated.


The default maximum is 100 reaches for requests involving `--bbox`,
including requests that combine bounding-box selection with other
reach-selection methods. This is a provisional CLI safety limit,
not a benchmarked NWM retrieval capacity.

Use `--max-reaches` to configure the limit. Requests exceeding the
limit are rejected rather than silently truncated.

Requests without `--bbox` retain their previous reach-count behavior.


Bounding-box selection can be combined with `--reach`, `--gage`,
and `--point`. Duplicate feature IDs are rejected.

The geographic implementation currently supports CONUS.


### Geographic polygon selection

The operational CLI supports selecting NWM reaches intersecting
a GeoJSON Polygon or MultiPolygon.

Example:

    streamflow-getter nwm-operational \
      --date 2026-04-19 \
      --cycle 0 \
      --polygon /path/to/region.geojson \
      --hydrofabric /path/to/NWM_v3_hydrofabric.gdb \
      --max-reaches 100 \
      --start-hour 1 \
      --end-hour 1 \
      --out polygon_forecast.csv

Supported GeoJSON inputs:
- Polygon geometry
- MultiPolygon geometry
- GeoJSON Feature containing a Polygon or MultiPolygon
- FeatureCollection containing exactly one polygonal Feature

The GeoJSON file must contain geographic longitude/latitude
coordinates in EPSG:4326. Coordinate bounds and polygon validity
are checked, but the original coordinate reference system cannot
be independently verified from coordinate values alone.

The command selects all NWM channel reaches intersecting the
polygon using the existing channel hydrofabric.

The default maximum is 100 reaches for requests involving
`--bbox` or `--polygon`, including combined selections.
This is a provisional CLI safeguard, not a benchmarked NWM
retrieval limit. Use `--max-reaches` to configure it.

Requests exceeding the limit are rejected without truncation.
Duplicate NWM feature IDs are rejected.

Geographic selection currently supports CONUS.



## Design

- **CLI first.** Core logic lives in a Python library; the CLI is a thin
  wrapper. The website will call the same library through the CLI.
- **One adapter per source**, behind a common interface:
  `fetch(reach_ids, start, end, variable) -> time series`.
- **Output:** CSV to start, Parquet later.

## Development

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repo>
cd streamflow_getter
uv sync
uv run streamflow-getter --help
uv run pytest
```

Run every Python command through `uv run`.

## Layout

```
src/streamflow_getter/   library and CLI
tests/                   tests
```

## Contributing

`main` is protected: no direct pushes. All changes arrive by pull request and
need one approval and a passing `test` check. PRs are squash-merged.

**Maintainer:** work on a branch in this repo.

```bash
git switch -c my-change
# ...edit, commit...
git push -u origin my-change
gh pr create --fill
```

**Contributors:** work from your own fork.

```bash
gh repo fork jameshalgren/streamflow_getter --clone
cd streamflow_getter
git remote -v                      # origin = your fork, upstream = this repo
git switch -c my-change
# ...edit, commit...
git push -u origin my-change
gh pr create --repo jameshalgren/streamflow_getter --fill
```

Keep your fork current before starting new work:

```bash
gh repo sync <your-username>/streamflow_getter
git switch main && git pull
```

Keep branches short-lived and PRs small.
