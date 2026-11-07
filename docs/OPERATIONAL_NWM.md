# Operational NWM Retrieval

Retrieve streamflow forecasts from the NOAA National Water Model (NWM) for river reaches in the contiguous United States (CONUS).

The `nwm-operational` command supports multiple forecast products, river-reach selection methods, validated Kerchunk reference caching, and CSV or Parquet output.

> **Scope:** This guide describes implemented capabilities. Some forecast products have been validated only for selected dates, cycles, and reaches. Full historical availability and scientific compatibility are not guaranteed.

## Contents

- [Quick start](#quick-start)
- [Installation](#installation)
- [Retrieval workflow](#retrieval-workflow)
- [Forecast products](#forecast-products)
- [Forecast timing](#forecast-timing)
- [Selecting reaches](#selecting-reaches)
- [Output formats](#output-formats)
- [Reference caching](#reference-caching)
- [Validation and limitations](#validation-and-limitations)

## Quick start

Retrieve a short-range forecast for NWM feature ID `3586192`:

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 2 \
  --out forecast.csv
```

The command requests forecast hours `f001` and `f002`. By default, it also includes an analysis timestep (`t0`). Add `--no-t0` to exclude that timestep.

The date and feature ID are documented validation examples. Data availability depends on the source archive.

## Installation

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

From the repository root, install the dependencies needed for your workflow:

| Extra | Purpose |
|---|---|
| `operational` | Operational NetCDF access and fallback |
| `spatial` | Point, bounding-box, and polygon selection |
| `parquet` | Parquet export |

For standard operational retrieval:

```bash
uv sync --extra operational
```

For all optional capabilities:

```bash
uv sync --extra operational --extra spatial --extra parquet
```

To inspect available CLI options:

```bash
uv run --locked streamflow-getter nwm-operational --help
```

## Retrieval workflow

```mermaid
flowchart TD
    A[Select product, date, and cycle]
    B[Choose reach IDs or geographic area]
    C[Resolve NWM feature IDs]
    D[Read Kerchunk reference]
    E{Retrieval successful?}
    F[Read native NetCDF when fallback is supported]
    G[Validate and extract streamflow]
    H[Write CSV or Parquet]

    A --> B
    B --> C
    C --> D
    D --> E
    E -->|Yes| G
    E -->|Supported fallback| F
    F --> G
    G --> H
```

The operational reader prefers Kerchunk references and uses native NetCDF for supported fallback conditions. The local reference cache can avoid downloading unchanged reference metadata.

## Forecast products

The following configurations are available through the operational CLI for CONUS.

| Product | Forecast cycles (UTC) | Available forecast leads |
|---|---|---|
| `short_range` | Every hour | f001–f018, hourly |
| `medium_range_mem1` | 00, 06, 12, 18 | f001–f240, hourly |
| `medium_range_mem2`–`medium_range_mem6` | 00, 06, 12, 18 | f001–f204, hourly |
| `medium_range_blend` | 00, 06, 12, 18 | f001–f240, hourly |
| `medium_range_no_da` | 00, 06, 12, 18 | f003–f240, every 3 hours |
| `long_range_mem1`–`long_range_mem4` | 00, 06, 12, 18 | f006–f720, every 6 hours |

The table describes the implemented product configurations. It does not establish complete source availability for every date or historical NWM version.

### Medium-range example

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --product medium_range_mem2 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 2 \
  --out medium_range.csv
```

### Long-range example

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --cycle 0 \
  --product long_range_mem2 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 12 \
  --no-t0 \
  --out long_range.csv
```

The long-range example selects `f006` and `f012`. It excludes `t0` because the scientific interpretation of the default analysis-to-long-range pairing has not been fully validated.

## Forecast timing

Forecast-hour windows are inclusive. The CLI selects only leads supported by the requested product.

| Product schedule | Example request | Selected leads |
|---|---|---|
| Hourly | Hours 1–3 | f001, f002, f003 |
| Every 3 hours | Hours 4–12 | f006, f009, f012 |
| Every 6 hours | Hours 1–12 | f006, f012 |

If the requested interval contains no valid forecast leads, the request is rejected.

### Analysis timestep (`t0`)

The operational CLI includes an initial analysis timestep by default.

- Most supported forecast products use `analysis_assim`.
- `medium_range_no_da` uses `analysis_assim_no_da`.
- The analysis and forecast records can have different reference times.
- Use `--no-t0` when only forecast lead records are required.

The analysis-to-forecast pairing for long-range ensembles has been tested for technical compatibility but has not been fully established as the scientifically intended initialization.

## Selecting reaches

Operational forecasts can be requested by NWM feature ID, USGS gage, geographic point, bounding box, or GeoJSON polygon.

| Method | Options | Required local dataset |
|---|---|---|
| Feature ID | `--reach` | None |
| USGS station | `--gage`, `--routelink` | Compatible RouteLink NetCDF |
| Point | `--point`, `--hydrofabric` | NWM channel hydrofabric |
| Bounding box | `--bbox`, `--hydrofabric` | NWM channel hydrofabric |
| Polygon | `--polygon`, `--hydrofabric` | NWM channel hydrofabric |

### NWM feature IDs

Use `--reach` to request a specific NWM channel. Repeat the option for multiple reaches.

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --reach 3586192 \
  --reach 1122645 \
  --start-hour 1 \
  --end-hour 2 \
  --out reaches.csv
```

### USGS gage IDs

Use `--gage` with a compatible local RouteLink NetCDF file.

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --gage 08165500 \
  --routelink /path/to/RouteLink_CONUS.nc \
  --start-hour 1 \
  --end-hour 2 \
  --out gage_forecast.csv
```

Preserve leading zeros in USGS station identifiers. RouteLink provides the mapping between station IDs and NWM feature IDs. Compatibility with historical NWM network versions must be verified separately.

### Geographic point

Use longitude and latitude in EPSG:4326.

```bash
uv run --locked --extra operational --extra spatial \
  streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --point -99.3217121935161 30.0699307434853 \
  --hydrofabric /path/to/NWM_v3_hydrofabric.gdb \
  --max-distance-m 500 \
  --start-hour 1 \
  --end-hour 1 \
  --out point_forecast.csv
```

The command selects the nearest NWM channel within the configured maximum distance.

**Important:** The nearest geographic channel is not necessarily the correct hydrologic reach, especially near tributary junctions.

### Geographic bounding box

Supply coordinates in this order:

`WEST SOUTH EAST NORTH`

```bash
uv run --locked --extra operational --extra spatial \
  streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --bbox -99.35 30.05 -99.30 30.09 \
  --hydrofabric /path/to/NWM_v3_hydrofabric.gdb \
  --max-reaches 100 \
  --start-hour 1 \
  --end-hour 1 \
  --out bbox_forecast.csv
```

The command selects NWM channels intersecting the bounding box.

### GeoJSON polygon

```bash
uv run --locked --extra operational --extra spatial \
  streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --polygon /path/to/region.geojson \
  --hydrofabric /path/to/NWM_v3_hydrofabric.gdb \
  --max-reaches 100 \
  --start-hour 1 \
  --end-hour 1 \
  --out polygon_forecast.csv
```

Supported inputs include Polygon and MultiPolygon geometries, Features containing those geometries, and FeatureCollections containing exactly one polygonal Feature.

Coordinates must represent longitude and latitude in EPSG:4326. Coordinate values alone cannot independently establish the source coordinate reference system.

### Geographic selection safeguards

The default limit for bounding-box and polygon requests is 100 reaches. Use `--max-reaches` to configure the limit.

Requests exceeding the limit are rejected rather than silently truncated. This limit is a CLI safeguard, not a measured maximum retrieval capacity.

Duplicate NWM feature IDs are rejected. Geographic selection currently supports CONUS only.

## Output formats

Operational retrieval supports CSV and Parquet. Streamflow values are expressed in cubic meters per second (m³/s).

### CSV

```bash
uv run --locked --extra operational streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 2 \
  --format csv \
  --out forecast.csv
```

### Parquet

Parquet requires the `parquet` optional dependency group.

```bash
uv run --locked --extra operational --extra parquet \
  streamflow-getter nwm-operational \
  --date 2026-04-19 \
  --reach 3586192 \
  --start-hour 1 \
  --end-hour 2 \
  --format parquet \
  --out forecast.parquet
```

Operational records include streamflow values and source/forecast metadata. The output implementation defines the authoritative column schema.

## Reference caching

The operational reader can store validated Kerchunk reference records locally.

The cache implementation checks reference structure, source identity, SHA-256 integrity, remote ETag, source generation, and consistency of remote metadata during downloads.

Cached references are reused when their metadata remains valid. Corrupted records can be replaced with validated downloads; source-generation changes are rejected when compatibility cannot be established.

Use `--cache-dir` to choose the cache location.

## Validation and limitations

### Validated behavior

Automated and selected real-data tests have verified:

- Kerchunk and native NetCDF retrieval agreement for selected forecast products and leads.
- Forecast timestamps, source identity, and product-specific lead schedules.
- USGS station resolution through RouteLink.
- Geographic point, bounding-box, and polygon selection.
- CSV and Parquet output.
- Reference-cache integrity, reuse, and recovery.

The tests demonstrate these behaviors for the cases examined, not every possible NWM file.

### Known limitations

1. Operational geographic retrieval is currently limited to CONUS.
2. Full forecast horizons have not been retrieved and verified for every supported product.
3. Historical model versions may differ in product availability, feature IDs, and network definitions.
4. RouteLink and hydrofabric versions must be compatible with the intended NWM data.
5. The nearest geographic channel may not represent the intended hydrologic reach.
6. The scientific suitability of `analysis_assim` as `t0` for long-range ensemble forecasts requires further confirmation.
7. The default geographic reach limit is a safeguard, not a performance benchmark.
8. Further NWM retrospective and GEOGLOWS development requires the technical coordination specified in the project roadmap.

## Related documentation

- [Main README](../README.md) — project overview and quick start.
- [Project roadmap](ROADMAP.md) — requirements and development priorities.
- [NWM notes](nwm-notes.md) — background on NWM data and network versions.
- [Benchmark documentation](../benchmarks/README.md) — reproducible retrieval experiments.
- [Research progress](../benchmarks/PROGRESS.md) — historical validation evidence.