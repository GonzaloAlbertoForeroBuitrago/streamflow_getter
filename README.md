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
| `medium_range_mem2` | CONUS | 00, 06, 12, 18 | f001–f204 |
| `medium_range_mem3` | CONUS | 00, 06, 12, 18 | f001–f204 |
| `medium_range_mem4` | CONUS | 00, 06, 12, 18 | f001–f204 |
| `medium_range_mem5` | CONUS | 00, 06, 12, 18 | f001–f204 |
| `medium_range_mem6` | CONUS | 00, 06, 12, 18 | f001–f204 |
| `medium_range_blend` | CONUS | 00, 06, 12, 18 | f001–f240 |
| `medium_range_no_da` | CONUS | 00, 06, 12, 18 | f003–f240, every 3 hours |
| `long_range_mem1` | CONUS | 00, 06, 12, 18 | f006–f720, every 6 hours |


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


#### Long-range ensemble member 1

The `long_range_mem1` product supports CONUS forecasts
initialized at 00, 06, 12, and 18 UTC.

Forecast leads are available every six hours from
f006 through f720 (30 days).

The CLI currently includes `analysis_assim` at t0 by
default. This analysis pairing has been verified for
technical compatibility but has not yet been confirmed
as the scientifically intended initialization source
for the long-range ensemble.

Example:

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --product long_range_mem1 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 12 \
  --out long_range_mem1.csv
```

The inclusive forecast window selects f006 and f012,
plus analysis t0 by default.

Real-data validation confirmed matching Kerchunk/native
streamflow and timestamps at f006, and successful CLI
retrieval of t0, f006, and f012.

The f720 source was confirmed available, but its data
were not retrieved. Full-horizon and historical-version
compatibility remain unverified.


#### Medium-range without data assimilation

The `medium_range_no_da` product supports CONUS forecasts
initialized at 00, 06, 12, and 18 UTC.

Forecast leads are available every three hours from
f003 through f240.

Unlike other currently supported products, its default
analysis t0 source is `analysis_assim_no_da`, rather than
`analysis_assim`.

Example:

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --product medium_range_no_da \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 6 \
  --out medium_range_no_da.csv
```

The inclusive forecast window selects only available leads.
For this example, the output contains analysis t0, f003,
and f006.

Real-data validation confirmed:

- NOAA native NetCDF and CIROH Kerchunk availability.
- Matching streamflow values for analysis t0 and f003.
- Correct no-DA analysis source selection.
- Successful CLI retrieval of t0, f003, and f006.
- Correct product identities and timestamps.

Full 240-hour retrieval and historical NWM version
compatibility remain unverified.


### Operational forecast lead scheduling

Operational NWM forecast requests use inclusive forecast-hour
windows. The library selects only the forecast leads available
for the configured product.

ProductSpec includes `lead_step_hours`, defaulting to 1 hour.
This preserves the behavior of existing short-range and
medium-range ensemble products.

The scheduling interface also supports products with longer
forecast intervals:

- Hourly: 1, 2, 3, 4, ...
- Three-hourly: 3, 6, 9, 12, ...
- Six-hourly: 6, 12, 18, 24, ...

For example, a three-hourly product requested over hours
4 through 12 selects f006, f009, and f012.

Individual forecast filenames must use valid scheduled leads.
Requests containing no available forecast leads are rejected.

Analysis t0 remains optional and is included by default.

Three-hour and six-hour scheduling have been validated using
temporary product configurations and automated tests.
Additional operational products are not enabled by this change.


### Operational NWM CLI product selection

The `nwm-operational` command supports two validated CONUS
product configurations:

- `short_range` (default): hourly cycles, f001–f018.
- `medium_range_mem1`: cycles 00, 06, 12, and 18 UTC,
  f001–f240.

Example: retrieve medium-range member 1 streamflow:

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --product medium_range_mem1 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 2 \
  --out medium_range.csv
```

Analysis `t0` is included by default. Use `--no-t0` to exclude it.

The CLI validates product-specific cycles and forecast-hour
ranges before retrieval.

Real-data validation was completed for April 19, 2026,
cycle t00z, NWM feature ID 3586192. The installed CLI
successfully retrieved analysis t0, f001, and f002 through
Kerchunk and wrote three CSV records with validated timestamps.

Other medium-range ensemble members, domains, and forecast
products are not yet supported.


#### Medium-range blend

The `medium_range_blend` product is supported for CONUS
forecasts with cycles at 00, 06, 12, and 18 UTC and hourly
forecast leads f001–f240.

Example:

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --product medium_range_blend \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 2 \
  --out medium_range_blend.csv
```

Analysis `t0` is included by default from `analysis_assim`.

Real-data validation for April 19, 2026, cycle t00z,
feature ID 3586192, confirmed agreement between Kerchunk
and native NetCDF at f001.

The installed CLI also successfully retrieved analysis t0,
f001, and f002, producing three CSV records with verified
timestamps and product identities.

Full 240-hour retrieval and compatibility across historical
NWM versions have not yet been validated.


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

Example


Medium-range ensemble members 1–6 are supported through the
same Kerchunk-first retrieval backend, with native NetCDF fallback
for supported access failures. Each member retains its product
identity in output records and cache paths.

For April 19, 2026, native NOAA files and CIROH Kerchunk references
were confirmed for all six members. Members 2–6 were individually
validated at f001 against both Kerchunk and native NetCDF using
feature ID 3586192. The installed CLI was additionally validated
for member 2 using analysis t0, f001, and f002.

These checks do not establish full 204-hour or 240-hour retrieval
coverage, compatibility across all historical NWM versions, or
equivalence between ensemble members.


uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --product medium_range_mem2 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 2 \
  --out medium_range_mem2.csv
