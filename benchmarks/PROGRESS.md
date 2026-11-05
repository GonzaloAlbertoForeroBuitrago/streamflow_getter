
# NWM Operational Retrieval — Development Progress

**Last updated:** October 27, 2026  
**Branch:** `benchmark/nwm-kerchunk-native`  
**Requirements:** `docs/ROADMAP.md`  
**Status:** Benchmark development and validation in progress

## 1. Objective

Develop and evaluate reliable, efficient retrieval of operational National Water Model (NWM) streamflow using Kerchunk references and native NetCDF.

The work focuses on retrieval performance, network transfer, numerical agreement, reach resolution, and reference caching before integration into the operational package.

## 2. Reference Dataset

| Parameter | Configuration |
|---|---|
| Forecast date | 2026-04-19 |
| Product | `short_range` |
| Forecast cycle | `t00z` |
| Domain | CONUS |
| Variable | `streamflow` (m³/s) |
| Initial benchmark | `f001`–`f006` |
| Available forecast horizon | `f001`–`f018` |
| Available cycles | 24 hourly cycles |
| Total channel_rt files | 432 |
| Features per file | 2,776,734 |

The reference dataset was verified for the tested forecast date and product.

## 3. Completed Experiments

### Experiment 1 — Retrieval Method Comparison

Four methods were implemented and tested:

1. Kerchunk remote references
2. Native NetCDF through HTTP range requests
3. Native NetCDF full download and local read
4. Native NetCDF local read

**Repeated benchmark:** Six forecast hours, five trials per method and hour, one reach, 120 retrieval operations.

| Method | Median time |
|---|---:|
| Native remote | 0.3554 s |
| Kerchunk | 0.4753 s |
| Native download | 0.6416 s |
| Native local | 0.0600 s |

Accounted response-body totals across 30 operations per remote method:

| Method | Data transferred |
|---|---:|
| Kerchunk | 79.41 MB |
| Native remote | 123.89 MB |
| Native download | 429.95 MB |

Native remote was faster in this experiment, while Kerchunk required fewer accounted response-body bytes.

### Experiment 2 — Cache Behavior

Investigated same-process versus separate-process retrieval and Kerchunk reference caching.

| Cache experiment | Median time |
|---|---:|
| Same-process native remote | 0.491 s |
| Separate-process native remote | 0.943 s |
| Kerchunk without reference cache | 0.434 s |
| Kerchunk with memory cache | 0.320 s |
| Kerchunk with disk cache | 0.292 s |

The reference JSON was 7,887 bytes. Caching avoided repeated reference downloads but did not eliminate remote model-data chunk retrieval.

These timings were exploratory; network and cache conditions were not fully controlled.

### Experiment 3 — Reference Validation and Persistence

Developed an experimental single-record reference-cache implementation with:

- Structural and external byte-range validation
- Source URL identity verification
- ETag and GCS generation metadata comparison
- SHA-256 integrity checks
- Atomic cache-file replacement
- Failed-refresh protection

The tested reference contained 32 entries, including seven external byte-range references.

### Experiment 4 — Live Cache Integration

Tested against the operational NWM forecast for reach `3586192`, hour `f001`.

| Execution | Cache retrieval time |
|---|---:|
| First (reference downloaded) | 0.748 s |
| Second (reference reused) | 0.429 s |

Both executions returned `0.40999999083578587 m³/s`, with valid time `2026-04-19 01:00 UTC` and reference time `2026-04-19 00:00 UTC`.

The experiment verified cross-process reference reuse, not a controlled performance improvement.

### Experiment 5 — Multi-Reach Retrieval

Verified five feature IDs at consistent array indices across six forecast hours.

| Feature ID | Array index | f001 streamflow (m³/s) |
|---|---:|---:|
| 1122645 | 100,000 | 7.08 |
| 3586192 | 351,819 | 0.41 |
| 7144704 | 750,000 | 0.00 |
| 14191043 | 1,500,000 | 16,062.71 |
| 23610484 | 2,500,000 | 0.01 |

Implemented shared batch extraction for native local, native remote, and Kerchunk readers. The full benchmark also supports native download followed by batch reading.

**Five-reach benchmark:** One forecast hour, one trial, four methods.

| Method | Elapsed time | Accounted bytes |
|---|---:|---:|
| Native download | 0.595 s | 14,324,480 |
| Native remote | 0.868 s | 4,131,132 |
| Kerchunk | 0.901 s | 2,648,518 |
| Native local | 0.059 s | 0 |

All methods returned matching streamflow and forecast timestamps.

Performance and scientific outputs are separated into:

- `benchmarks/results/repeated_benchmark.csv`
- `benchmarks/results/repeated_benchmark_flows.csv`

## 4. Automated Validation

**61 tests passed**, including eight benchmark-specific tests.

Verified behavior includes batch extraction, feature-ID identity and ordering, single-reach compatibility, non-finite value rejection, CSV output structure, streamflow mismatch detection, and timestamp mismatch detection.

The existing package tests remain passing.

## 5. Remaining Limitations

- Multi-reach timing has been measured for only one forecast hour and one trial.
- Full 18-hour cycles and multi-day or multi-week benchmarks remain pending.
- Network and cache conditions were not fully controlled.
- Accounted response-body bytes exclude some HTTP metadata and protocol overhead.
- Reach resolution is excluded from timed retrievals.
- Remote reference/source version compatibility is not fully established.
- Concurrent cache refresh and operational cache integration remain untested.
- RouteLink-based geographic and gage resolution is not implemented.

## 6. Next Development Priorities

Following `docs/ROADMAP.md`:

1. **Complete benchmarking:** Expand to 18 forecast hours, multiple cycles, several reaches, and days/weeks. Investigate reference age/version compatibility and reproducible performance.
2. **Reach resolution:** Implement RouteLink/hydrofabric mapping for gages and spatial selections.
3. **Operational retrieval:** Integrate Kerchunk-first access, native NetCDF fallback, reference preprocessing/cache, product selection, ensembles, and default `analysis_assim` t0 handling.
4. **Outputs and compatibility:** Add Parquet alongside CSV, preserve forecast reference/valid times and lead time, and validate products, domains, and model versions.

GEOGLOWS and further NWM retrospective development remain subject to the approval gates in `docs/ROADMAP.md`.

## 7. Development Practices

Development remains on the current branch. Reuse existing implementations, avoid redundant scripts and unnecessary backup files, maintain automated test coverage, and use Git for version history.

Pull-request preparation is postponed until development and validation are complete.


## Complete 18-hour forecast benchmark — 2026-10-27

Configuration:
- Forecast: 2026-04-19, short_range, t00z, CONUS
- Forecast hours: f001–f018
- Reaches: 5
- Methods: 4
- Trials: 1
- Retrieval operations: 72
- Streamflow records: 360

Results:

| Method | Median time (s) | Accounted bytes |
|---|---:|---:|
| Native remote | 0.476 | 74245753 |
| Kerchunk | 0.497 | 47558690 |
| Native download | 0.545 | 257304483 |
| Native local | 0.061 | 0 |

Scientific validation:
- All 18 forecast hours passed.
- Streamflow agreement verified for all five reaches.
- Forecast valid and reference times matched.
- No duplicate records detected.

Limitations:
- One forecast cycle and one trial per hour.
- Reach resolution excluded from timing.
- Network and cache conditions not controlled.
- Accounted bytes do not include complete HTTP overhead.

Next:
- Repeat full-cycle measurements.
- Expand to multiple forecast cycles and dates.
- Investigate reference age/version compatibility.


## Complete 18-hour benchmark — Three trials (2026-10-27)

Configuration:
- NWM short_range, CONUS, 2026-04-19, t00z
- Forecast hours: f001–f018
- Reaches: 5
- Trials: 3
- Methods: Kerchunk, native remote, native download, native local

Validation:
- 216 retrieval operations
- 1,080 streamflow records
- All streamflow and forecast timestamps matched
- No duplicate records
- Last automated test suite: 63 passed

| Method | Median (s) | Accounted bytes |
|---|---:|---:|
| Kerchunk | 0.482 | 142676070 |
| Native remote | 0.477 | 222737259 |
| Native download | 0.536 | 771913449 |
| Native local | 0.060 | 0 |

Findings:
- Kerchunk used 35.9% fewer accounted bytes than native remote.
- Kerchunk used 81.5% fewer than full native downloads.
- Kerchunk and native remote had similar median retrieval times.
- Cache and network conditions were not fully controlled.
- Reach resolution was excluded from timed retrievals.

Next:
- Extend benchmarking to multiple forecast cycles and dates.
- Investigate CIROH reference age/version compatibility.



**Last updated:** October 29, 2026

**Current status:** Configurable multi-reach NWM benchmark validated.

### Latest verified milestone

- Complete 18-hour short-range forecast cycle.
- Five NWM reaches.
- Four retrieval methods.
- Three repeated trials.
- 216 retrieval operations.
- 1,080 streamflow records.
- Numerical agreement across retrieval methods.
- Forecast date, cycle, and lead-hour validation.
- Atomic native NetCDF downloads.
- Configurable forecast paths and output filenames.
- Complete automated test suite: 64 passed.

### Next priority

Extend validated multi-day benchmarking to longer date ranges
and repeated trials, then evaluate performance consistency,
reference compatibility, and cache behavior.



## Automated three-day benchmark — October 29, 2026

Configuration:
- Forecast dates: 2026-04-19 through 2026-04-21
- Product: short_range, CONUS, t00z
- Forecast hour: f001
- Reaches: 5
- Retrieval methods: 4
- Trials: 1 per date

Validated results:
- 12 retrieval operations
- 60 streamflow records
- Correct forecast reference and valid times
- Numerical agreement across all four methods
- No duplicate records

| Method | Median time (s) | Accounted bytes |
|---|---:|---:|
| Kerchunk | 0.608 | 7865304 |
| Native remote | 0.632 | 12313146 |
| Native download | 0.501 | 42627027 |
| Native local | 0.060 | 0 |

Findings:
- Kerchunk transferred 36.1% fewer accounted bytes than native remote.
- Kerchunk transferred 81.5% fewer than full native downloads.
- Timing differences remain inconclusive.
- Cache and network conditions were not fully controlled.

Validation:
- Multi-day execution and date isolation tested.
- CSV overwrite protection and ordinary failure cleanup tested.
- Last automated test suite: 67 passed.

Next:
- Extend to longer date ranges with repeated trials.
- Investigate Kerchunk reference freshness and source compatibility.
- Review benchmark findings before operational integration.

## Kerchunk reference compatibility — October 29, 2026

Reference:
- Forecast: 2026-04-19, short_range, t00z, f001, CONUS
- Native source size: 14,324,480 bytes
- Kerchunk reference size: 7,887 bytes
- Reference entries: 32
- External byte ranges: 7
- Maximum referenced byte boundary: 14,324,480

Validation:
- Reference structure passed.
- External source URL identity passed.
- All external byte ranges fit within the native source.
- NWM version: v3.0
- NWM code version: v5.3.0-alpha1
- Previous Kerchunk/native streamflow comparisons passed.

Limitations:
- Reference JSON does not expose the original GCS source generation.
- Exact reference/source generation compatibility is not proven.
- Valid byte ranges do not guarantee identical source contents.
- Validation covers the selected forecast and tested reaches.
- Cache freshness detection does not establish original provenance.

Conclusion:
The tested reference is structurally valid and consistent with
the current native source size and selected streamflow values.
Retain conservative cache invalidation when source metadata changes.

Next:
- Proceed to operational reach resolution using RouteLink/hydrofabric.
- Preserve reference compatibility checks for future integration.

## Operational RouteLink reach resolution — October 29, 2026

Source:
- Repository: jameshalgren/troute-lab
- Source revision: bb24900e3229851f6e997b037c337a8643471562
- Dataset: NWM v3.1.6 RouteLink_CONUS.nc
- File size: 269,369,766 bytes
- SHA-256: 4957655896f4f27854f893d02fa084f9f79c1cf8e80ce77565a7356dadb6fc0e

Verified dataset:
- 2,776,734 unique NWM feature IDs.
- 8,735 unique gage associations.
- All five benchmark feature IDs found.
- USGS 08165500 maps to NWM feature_id 3586192.
- All associated RouteLink coordinates have valid numeric ranges.

Implementation:
- Added reusable operational gage resolver.
- Preserves identifiers as exact strings.
- No automatic leading-zero padding.
- Detects duplicate feature IDs and ambiguous gage mappings.
- Rejects noninteger feature IDs.
- Supports configurable RouteLink NetCDF loading.
- No permanent geospatial dependencies added.

Validation:
- Real RouteLink loader passed.
- Twenty USGS API pilot identifiers matched exactly.
- Point-to-point geographic distances ranged from 11.6 m to 2932.2 m.
- Complete automated test suite: 78 passed.

Limitations:
- Complete geographic and hydrologic association accuracy is not established.
- RouteLink v3.1.6 compatibility with all operational NWM versions is not proven.
- Point, bounding-box, and polygon resolution remain pending.
- NetCDF reading requires an available optional backend.



## Geographic NWM reach resolution — November 3, 2026

### Objective

Implement the geographic reach-selection functionality requested
in docs/ROADMAP.md using NWM RouteLink and channel hydrofabric.

### Implementation

Module: src/streamflow_getter/spatial_resolution.py

Supported operations:

- USGS gage resolution through RouteLink
  (reach_resolution.py).
- Geographic point selection using projected channel distances.
- Bounding-box selection using channel-geometry intersection.
- Polygon and MultiPolygon selection using channel-geometry
  intersection.

Geographic implementation:

- Input geographic coordinates: EPSG:4326.
- Verified CONUS hydrofabric CRS: EPSG:4269.
- Point distance calculations: EPSG:5070.
- Geographic candidate loading: pyogrio.
- Exact geometric intersection: GeoPandas/Shapely.
- Feature-ID validation rejects noninteger and nonpositive IDs.
- Hydrofabric CRS validation occurs before geographic loading.
- Spatial dependencies are optional under the `spatial` extra.

### Dataset provenance

Source: jameshalgren/troute-lab
Dataset: NWM v3.1.6 channel hydrofabric

Local source:
~/Documents/troute-lab/data/NWM_v3_hydrofabric.gdb

Original archive:
NWM_channel_hydrofabric.tar.gz

Source URL:
https://www.nohrsc.noaa.gov/owp_files/nwm/data_tools/NWM_channel_hydrofabric.tar.gz

Published SHA-256:
77d8975b543ff864cdac0736cc4f455fe86d77049c4d8b1fb8e458ec755dbc94

Previously verified:
- 2,776,734 unique CONUS feature IDs.
- Exact RouteLink/hydrofabric feature-ID set correspondence.

### Validation

Automated:
- 26 spatial tests passed.
- 104 total tests passed with the spatial extra.
- Standard environment previously passed 78 tests with
  one optional module skipped.

Real hydrofabric:
- USGS 08165500 nearest reach: 3586192.
- Nearest channel distance: approximately 98.34 m.
- Bounding-box selection: 18 reaches.
- Polygon selection: 12 reaches.
- No missing or unexpected reaches in the earlier independent
  geographic subset comparisons.

### Limitations

- Current geographic implementation targets CONUS.
- Other NWM domains require domain-specific CRS and validation.
- Point distances are projected distances, not exact geodesic
  distances.
- Nearest-channel selection does not establish hydrologic
  connectivity or guarantee correct gage association.
- Geographic search-envelope completeness has not been
  established for all CONUS locations.
- Bounding boxes crossing the antimeridian are unsupported.
- Compatibility across all historical NWM versions is unverified.
- Spatial selection is not yet connected to operational
  streamflow retrieval.

### Next

- Review the final implementation and tests.
- Integrate reach selection with operational NWM retrieval.
- Continue Kerchunk-first access, native fallback, and caching
  according to docs/ROADMAP.md.



## Operational NWM retrieval — November 3, 2026

### Objective

Implement the initial operational NWM retrieval workflow described
in docs/ROADMAP.md, reusing the existing benchmark implementations.

### Scope

Initial supported configuration:

- NWM product: short_range
- Domain: CONUS
- Output variable: streamflow
- Forecast data: channel_rt
- Reference case: 2026-04-19, t00z, f001

Other products, domains, ensemble members, and analysis t0 remain
outside the validated implementation.

### Production implementation

Modules:

- src/streamflow_getter/operational_nwm.py
- src/streamflow_getter/reference_validation.py
- src/streamflow_getter/reference_cache.py

Implemented functionality:

- Forecast configuration and source identification.
- Forecast reference-time and valid-time validation.
- Multi-reach streamflow extraction using feature IDs.
- Kerchunk-first operational retrieval.
- Native NetCDF remote retrieval.
- Controlled native fallback for selected access failures.
- Optional reference caching.
- Reference structure and source-identity validation.
- SHA-256 cache-record integrity validation.
- Atomic cache-record persistence.
- Reference ETag and source-generation freshness checks.
- Rejection of unresolved source-generation changes.

Caching is opt-in through cache_dir.

When caching is enabled, the coordinator currently propagates
retrieval errors rather than automatically attempting native fallback.

### Validation

Automated:

- 177 tests passed with spatial and operational extras.
- Git whitespace validation passed.

Live reference forecast:

- Date: 2026-04-19
- Cycle: t00z
- Product: short_range
- Lead hour: f001
- Domain: CONUS
- Feature ID: 3586192
- Streamflow: 0.40999999083578587 m3/s
- Valid time: 2026-04-19 01:00 UTC
- Reference time: 2026-04-19 00:00 UTC

Verified:

- Kerchunk retrieval.
- Native NetCDF retrieval.
- Controlled native fallback after simulated Kerchunk failure.
- Cached Kerchunk retrieval and cache-record reuse.
- Compatibility with existing benchmark extraction and cache behavior.

### Known limitations

- Initial production support is limited to short_range CONUS.
- Forecast t0 from analysis_assim is not yet implemented.
- Medium-range, long-range, ensemble, and other-domain support
  remains pending.
- Cache metadata comparison does not independently prove that
  Kerchunk references were generated against the current NetCDF
  source generation.
- Cached requests currently disable automatic native fallback.
- Broad OSError classification for uncached fallback requires
  further refinement.
- Reference JSON size is not equivalent to network bytes transferred.
- Production CLI integration is not yet implemented.
- Parquet output is not yet implemented.
- Operational availability across dates and model versions has
  not been comprehensively validated.

### Next

- Review the final implementation and staged changes.
- Refine source compatibility and fallback error classification.
- Integrate the operational reader with the CLI.
- Implement forecast t0 handling according to docs/ROADMAP.md.
- Add structured CSV/Parquet output with forecast reference time
  and lead time.

## NWM analysis t0 integration — November 3, 2026

### Objective

Implement default analysis_assim t0 retrieval for operational
short_range CONUS forecasts, following docs/ROADMAP.md.

### Implementation

Module: src/streamflow_getter/operational_nwm.py

- Resolve analysis_assim channel_rt tm00 for lead hour zero.
- Preserve existing short_range forecast retrieval for positive leads.
- Reuse Kerchunk-first and native NetCDF retrieval.
- Preserve controlled fallback and optional reference caching.
- Separate analysis_assim and short_range cache records.
- Validate source identity, feature IDs, and timestamps.
- Preserve the original analysis reference_time.
- Assemble t0 and forecast hours into a pandas DataFrame.
- Include t0 by default, with include_t0=False available.
- Reject invalid reach IDs before remote retrieval.
- Reject inconsistent forecast identity and nonfinite streamflow.

### Live validation

Reference date: 2026-04-19
Forecast cycle: t00z
Domain: CONUS
Feature ID: 3586192

Analysis t0:
- Product: analysis_assim
- Valid time: 2026-04-19 00:00 UTC
- Source reference time: 2026-04-18 21:00 UTC
- Streamflow: 0.40999999083578587 m3/s

Forecast f001:
- Product: short_range
- Valid time: 2026-04-19 01:00 UTC
- Source reference time: 2026-04-19 00:00 UTC
- Streamflow: 0.40999999083578587 m3/s

Kerchunk and native NetCDF returned matching t0 values and timestamps.

Nine analysis cycles were checked for the reference date.
All had valid times matching their requested cycle hours and
source reference times three hours earlier.

The analysis and forecast f001 files contained 2,776,734
feature IDs with identical membership and ordering.

The complete t0 + f001 series was retrieved successfully
through the production Kerchunk workflow.

### Automated validation

- 218 tests passed with spatial and operational extras.
- Python compilation passed.
- Git whitespace validation passed.

### Limitations

- Validated production support remains short_range CONUS.
- The observed three-hour analysis reference-time offset must
  not be assumed universal.
- Compatibility across other dates, products, domains, and
  NWM versions remains unverified.
- Medium-range and long-range ensemble t0 handling is pending.
- analysis_assim_no_da handling is pending.
- Operational CLI integration is pending.
- CSV/Parquet output integration is pending.
- Cached retrieval currently propagates errors rather than
  automatically attempting native fallback.

### Next

- Review staged changes and commit the t0 milestone.
- Implement CSV/Parquet output according to docs/ROADMAP.md.
- Integrate operational retrieval into the existing CLI.
- Expand product and domain support after source validation.

## CSV and Parquet output writer — November 3, 2026

### Objective

Implement reusable CSV and Parquet serialization following
README.md and docs/ROADMAP.md.

### Implementation

Module: src/streamflow_getter/output.py

- Reusable write_timeseries() library function.
- CSV and Parquet serialization using pandas.
- Optional pyarrow dependency through the parquet extra.
- Output format inferred from .csv or .parquet extensions.
- Explicit output_format selection supported.
- Conflicting explicit formats and extensions rejected.
- Existing output files protected from overwriting.
- Temporary-file serialization before publication.
- Cleanup after serialization or publication failures.
- Original DataFrame columns preserved.

### Validation

- 20 output-specific tests passed.
- 238 complete repository tests passed.
- Python syntax validation passed.
- Git whitespace validation passed.
- CSV and Parquet round-trip tests passed.
- Existing-file protection verified.
- Simulated partial-publication failure cleanup verified.

### Limitations

- Operational CLI integration is not yet implemented.
- The --format CLI argument is not yet implemented.
- The existing retrospective CLI still writes CSV directly.
- The writer does not independently validate scientific
  metadata; it expects a validated input DataFrame.
- CSV timestamps are serialized as text, while Parquet
  preserves supported column data types.

### Next

- Review and commit the validated output writer.
- Review James's CLI architecture and requirements.
- Integrate CSV/Parquet selection into the CLI.
- Preserve existing retrospective command behavior.

## Operational NWM CLI integration — November 3, 2026

### Objective

Expose validated operational NWM short-range CONUS retrieval through
the existing streamflow-getter command-line interface, following
README.md and docs/ROADMAP.md.

### Implementation

Module: src/streamflow_getter/cli.py

New subcommand: nwm-operational

Supported options:
- --date and --cycle
- Repeated --reach for direct NWM feature IDs
- --start-hour and --end-hour
- --no-t0 to exclude analysis_assim t0
- --cache-dir for optional reference caching
- --format csv/parquet, with extension inference
- --out for output destination

The CLI reuses ForecastConfig, fetch_operational_series,
and write_timeseries without duplicating retrieval or
serialization logic.

Invalid forecast-hour ranges, output formats, and existing
output destinations are rejected before retrieval.

The original nwm retrospective command remains available
with its existing behavior and help descriptions.

### Validation

- 22 operational CLI tests passed.
- 260 complete repository tests passed.
- Operational and retrospective help commands passed.
- CSV and Parquet output integration passed using mocked retrieval.
- Retrospective execution regression test passed.
- Git whitespace validation passed.

### Limitations

- Operational CLI supports direct feature IDs only.
- RouteLink gage and geographic selection are not yet exposed.
- Validated operational retrieval is limited to short_range CONUS.
- Other NWM products, domains, ensembles, and model-version
  compatibility require additional validation.
- Cached retrieval errors currently propagate rather than
  automatically attempting native fallback.
- The new operational CLI has not yet undergone a live
  end-to-end invocation through the installed command.

### Next

- Validate the operational CLI with real NWM data.
- Extend reach selection using existing RouteLink functions.
- Review operational support across NWM versions.
- Prepare focused contributions following James's PR workflow.

## Operational USGS gage CLI integration — November 3, 2026

### Objective

Expose RouteLink-based USGS gage resolution through the operational
NWM CLI, following docs/ROADMAP.md.

### Implementation

Module: src/streamflow_getter/cli.py

- Added repeatable --gage selection.
- Added --routelink for local RouteLink NetCDF files.
- Preserved direct --reach selection.
- Supported combined reach and gage requests.
- Reused existing RouteLink resolution functions.
- Preserved leading zeros in USGS gage identifiers.
- Rejected missing, unknown, and duplicate selections.
- Performed reach resolution before remote NWM retrieval.

### Real-data validation

RouteLink:
- File: RouteLink_CONUS.nc
- Reaches: 2,776,734
- Mapped USGS gages: 8,735

Reference station:
- USGS gage: 08165500
- NWM feature ID: 3586192

Forecast:
- Date: 2026-04-19
- Cycle: t00z
- Product: short_range CONUS
- Method: Kerchunk

Analysis t0:
- Valid time: 2026-04-19 00:00 UTC
- Reference time: 2026-04-18 21:00 UTC

Forecast f001:
- Valid time: 2026-04-19 01:00 UTC
- Reference time: 2026-04-19 00:00 UTC

The complete USGS gage to RouteLink to operational NWM
to CSV workflow passed.

### Automated validation

- 29 operational CLI tests passed.
- 267 complete repository tests passed.
- Git whitespace validation passed.

### Limitations

- RouteLink compatibility across all NWM versions is not proven.
- Geographic point, bounding-box, and polygon CLI selection
  remain pending.
- Operational support remains limited to short_range CONUS.
- Real-data CLI validation covered one USGS gage and one
  forecast cycle.

### Next

- Review and commit the gage CLI milestone.
- Extend geographic CLI selection using existing spatial
  resolution functions.
- Validate compatibility across NWM versions.

## Operational NWM geographic point CLI integration — November 5, 2026

### Objective

Expose existing NWM hydrofabric point-to-reach resolution through
the operational CLI, following docs/ROADMAP.md and the geographic
selection approach established in jameshalgren/troute-lab.

### Implementation

Modules:
- src/streamflow_getter/cli.py
- src/streamflow_getter/spatial_resolution.py (reused, unchanged)

CLI arguments:
- --point LONGITUDE LATITUDE
- --hydrofabric PATH
- --max-distance-m DISTANCE (default: 500)

Behavior:
- Resolve geographic coordinates to the nearest NWM channel.
- Use actual hydrofabric channel geometries.
- Calculate distances using the CONUS projected CRS.
- Select the nearest candidate within the requested radius.
- Reuse existing spatial-resolution functions.
- Preserve direct --reach and RouteLink-based --gage selection.
- Support combined reach-selection methods.
- Reject duplicate feature IDs.
- Validate invalid search radii before accessing the hydrofabric.
- Resolve geographic selections before remote NWM retrieval.

### Real-data validation

Dataset:
- NOAA NWM v3 channel hydrofabric
- Layer: nwm_reaches_conus
- CRS: EPSG:4269

Reference location:
- USGS station: 08165500
- Longitude: -99.3217121935161
- Latitude: 30.0699307434853

Results:
- Selected NWM feature ID: 3586192
- Point-to-channel distance: approximately 98.34 m
- Selection agrees with the previously verified RouteLink association.

The operational CLI geographic-selection path was tested using
the real hydrofabric with remote forecast retrieval mocked.

No remote NWM retrieval or output-file publication was performed
during this geographic integration test.

### Automated validation

- 279 complete repository tests passed with the spatial extra.
- Invalid search radii (zero, negative, NaN, infinity) rejected.
- Missing hydrofabric arguments rejected.
- No-candidate selection rejected.
- Duplicate point/reach selection rejected.
- Combined point/gage selection tested.
- Git whitespace validation passed.

### Limitations

- Operational geographic point selection currently supports CONUS.
- Nearest geographic reach is not necessarily the correct
  hydrologic reach near confluences or parallel channels.
- Automatic nearest-reach selection uses distance and feature-ID
  ordering; it does not independently validate hydrologic topology.
- Geographic point selection has not yet undergone a live
  end-to-end NWM forecast retrieval.
- Bounding-box and polygon selection remain available in the
  Python library but are not exposed in the operational CLI.
- Compatibility across historical NWM versions remains unverified.

### Next

- Review CLI argument validation and combined selection behavior.
- Add operational CLI documentation to README.md.
- Perform final regression and source-diff checks.
- Commit the validated geographic point CLI milestone.
- Continue with geographic bounding-box and polygon CLI selection.



## Operational NWM bounding-box CLI integration — November 5, 2026

### Objective

Expose existing hydrofabric bounding-box reach selection through
the operational NWM CLI, following docs/ROADMAP.md.

### Implementation

- Added `--bbox WEST SOUTH EAST NORTH`.
- Reused `reaches_in_bbox()` from spatial_resolution.py.
- Preserved `--reach`, `--gage`, and `--point`.
- Required `--hydrofabric` for geographic selection.
- Added configurable `--max-reaches` (default: 100).
- Applied the configurable reach limit to requests involving
  --bbox, including combined reach-selection methods.
- Preserved the previous reach-count behavior for requests
  without --bbox.
- Rejected empty selections, duplicate IDs, and invalid coordinates.
- Preserved validation before remote NWM retrieval.
- Kept spatial dependencies optional.

### Real-data validation

Dataset: NWM v3 CONUS channel hydrofabric.

Bounding box:
- West: -99.35
- South: 30.05
- East: -99.30
- North: 30.09

Results:
- 19 NWM reaches selected.
- 19 unique feature IDs.
- Known USGS-associated NWM reach 3586192 included.
- Real hydrofabric-to-CLI integration passed.

The NWM retrieval function was mocked during this integration
test. No remote forecast data was downloaded.

### Automated validation

- 297 complete repository tests passed in both standard and
  spatial environments.
- Verified that the bbox limit does not restrict existing
  direct-reach requests.
- Successful multiple-reach selection tested.
- Empty selections rejected.
- Per-bbox and combined reach limits tested.
- Duplicate combined selections rejected.
- Invalid bounding-box coordinates rejected.
- Remote retrieval protection tested for invalid selections.
- Git whitespace validation passed.

### Limitations

- Geographic selection currently supports CONUS.
- The default 100-reach limit is provisional and has not been
  established through retrieval performance benchmarks.
- Large geographic selections may require additional performance
  and memory validation.
- No live end-to-end NWM retrieval using --bbox has been performed.
- Polygon selection is available in the Python library but not
  yet exposed in the operational CLI.
- Compatibility across NWM versions remains unverified.

### Next

- Review documentation and final source changes.
- Verify standard and spatial test environments.
- Commit the bounding-box CLI milestone.
- Continue with polygon selection following James's roadmap.
