
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



## Operational NWM GeoJSON polygon CLI integration — November 5, 2026

### Objective

Expose polygon-based NWM reach selection through the operational
CLI, following docs/ROADMAP.md and reusing existing hydrofabric
geographic-selection functions.

### Implementation

Modules:
- src/streamflow_getter/spatial_resolution.py
- src/streamflow_getter/cli.py

Features:
- Added reusable load_geojson_polygon().
- Supported Polygon and MultiPolygon geometries.
- Supported Feature and single-feature FeatureCollection inputs.
- Validated polygon geometry and geographic coordinate bounds.
- Added --polygon GEOJSON_PATH to the operational CLI.
- Reused reaches_in_polygon() for hydrofabric intersection.
- Preserved existing --reach, --gage, --point, and --bbox methods.
- Extended the provisional reach-count safeguard to requests
  involving --bbox or --polygon.
- Rejected empty selections and duplicate feature IDs.
- Preserved validation before remote NWM retrieval.

### Real-data validation

Dataset:
- NOAA NWM v3 CONUS channel hydrofabric.

Reference polygon:
- West: -99.35
- South: 30.05
- East: -99.30
- North: 30.09

Results:
- 19 NWM reaches selected.
- 19 unique feature IDs.
- NWM feature ID 3586192 included.
- GeoJSON-to-hydrofabric-to-CLI integration passed.

Remote NWM retrieval was mocked during the integration test.
No forecast data was downloaded or output file created.

### Automated validation

- 316 complete repository tests passed.
- GeoJSON geometry, Feature, and FeatureCollection tested.
- Polygon and MultiPolygon tested.
- Missing files and unsupported geometries rejected.
- Self-intersecting polygons rejected.
- Out-of-range longitude/latitude coordinates rejected.
- Malformed JSON rejected before remote NWM retrieval.
- Empty polygon selections and reach-limit violations tested.
- Duplicate selections rejected.
- Remote retrieval protection tested for invalid selections.
- Git whitespace validation passed.

### Limitations

- Operational polygon selection currently supports CONUS.
- GeoJSON input requires EPSG:4326 longitude/latitude.
- Numeric coordinate validation does not prove source CRS.
- FeatureCollections with multiple features are not supported.
- The 100-reach default is provisional and not benchmarked.
- No live end-to-end NWM forecast retrieval using --polygon
  has been performed.
- Historical NWM version compatibility remains unverified.

### Next

- Verify standard and spatial test environments.
- Review complete source and documentation changes.
- Commit the polygon CLI milestone.
- Reassess remaining roadmap priorities with James before
  expanding functionality.



## Operational NWM medium-range member 1 configuration — November 5, 2026

### Objective

Extend the existing operational NWM backend to support a
validated medium-range CONUS ensemble member while preserving
short-range behavior and reusing the Kerchunk/native readers.

### Implementation

Modules:
- src/streamflow_getter/operational_nwm.py
- tests/test_operational_product_config.py

Changes:
- Added immutable ProductSpec configuration.
- Added validated medium_range_mem1 source conventions.
- Preserved short_range as the default product.
- Validated medium-range cycles at 00, 06, 12, and 18 UTC.
- Validated medium-range forecast hours f001–f240.
- Preserved ensemble-member identity in output and cache paths.
- Reused analysis_assim tm00 for the tested analysis t0.
- Rejected invalid forecast ranges before remote retrieval.
- Reused existing Kerchunk-first and native-fallback logic.

### Real-data validation

Reference:
- Date: 2026-04-19
- Cycle: t00z
- Domain: CONUS
- Product: medium_range_mem1
- NWM feature ID: 3586192

Source conventions:
- Directory: medium_range_mem1
- Filename product: medium_range
- Channel family: channel_rt_1

Analysis t0:
- Valid time: 2026-04-19 00:00 UTC
- Reference time: 2026-04-18 21:00 UTC

Forecast f001:
- Valid time: 2026-04-19 01:00 UTC
- Reference time: 2026-04-19 00:00 UTC
- Kerchunk streamflow: 0.40999999083578587 m3/s
- Native streamflow: 0.40999999083578587 m3/s

Live retrieval:
- Analysis t0, f001, and f002 succeeded using Kerchunk.
- Three time-series rows returned.
- Forecast and analysis feature-ID arrays matched.
- No source-identity or timestamp validation errors.

### Automated validation

- 343 complete repository tests passed.
- 27 product-configuration tests passed.
- Invalid cycles and forecast hours rejected.
- Invalid forecast ranges rejected before remote retrieval.
- Forecast and analysis source identities tested.
- Cache isolation tested.
- Recoverable Kerchunk access failure triggered mocked native fallback.
- Existing short-range regression tests passed.
- Git whitespace validation passed.

### Limitations

- Live validation covered one date, cycle, reach, and two forecast hours.
- The full 240-hour forecast was not retrieved.
- Other ensemble members are not yet enabled.
- The CLI does not yet expose operational product selection.
- Historical model-version compatibility remains unverified.
- Cached retrieval failures still propagate without native fallback.
- Additional domains and no-DA analysis pairings require validation.

### Next

- Review and commit this product-configuration milestone.
- Add validated operational product selection to the CLI.
- Extend support incrementally to other NWM products and ensembles.
- Continue following the original roadmap coordination gates.


## Operational NWM product CLI integration — November 5, 2026

### Objective

Expose the validated medium_range_mem1 configuration through
the operational CLI without duplicating the retrieval backend.

### Implementation

- Added --product to nwm-operational.
- Preserved short_range as the default.
- Added medium_range_mem1 as a supported choice.
- Passed product selection into ForecastConfig.
- Validated product-specific cycles and forecast hours.
- Reused existing reach selection, Kerchunk retrieval,
  native fallback, and CSV/Parquet output.

### Real-data validation

Configuration:
- Date: 2026-04-19
- Cycle: t00z
- Product: medium_range_mem1
- Domain: CONUS
- NWM feature ID: 3586192
- Forecast leads: analysis t0, f001, f002

Results:
- Installed CLI execution succeeded.
- Three CSV records generated.
- All records retrieved using Kerchunk.
- Analysis and forecast product identities preserved.
- Valid times and reference times verified.
- Streamflow values were finite.
- Temporary output directory cleaned automatically.

### Automated validation

- 352 complete repository tests passed.
- Unsupported medium-range cycles rejected.
- Unsupported forecast hours rejected before retrieval.
- Existing short-range CLI behavior preserved.
- Python compilation passed.
- Git whitespace validation passed.

### Limitations

- Real CLI validation covered one date, cycle, reach,
  and two forecast hours.
- Other ensemble members and domains remain unsupported.
- Full 240-hour retrieval has not been validated.
- Cached retrieval errors still propagate rather than
  automatically triggering native fallback.

### Next

- Review and commit the CLI product-selection milestone.
- Continue validating additional operational NWM products.
- Preserve the original roadmap's coordination requirements.


## Operational NWM medium-range ensemble expansion — November 5, 2026

### Objective

Extend validated operational NWM support from medium_range_mem1
to medium_range_mem2 through medium_range_mem6 without changing
the existing retrieval backend.

### Implementation

- Added ProductSpec configurations for members 2–6.
- Preserved short_range and medium_range_mem1 behavior.
- Enabled all six members through the --product CLI argument.
- Used validated forecast cycles 00, 06, 12, and 18 UTC.
- Preserved the 240-hour horizon for member 1.
- Applied the 204-hour horizon to members 2–6.
- Reused Kerchunk-first retrieval, native fallback,
  source validation, timestamp validation, and caching.
- Preserved ensemble-member identity in output and cache paths.

### Real-data validation

Date: 2026-04-19
Cycle: t00z
Domain: CONUS
Feature ID: 3586192

Native NOAA objects and CIROH Kerchunk references were
confirmed available for all six ensemble members.

Members 2–6 were tested individually at f001 using the
existing read_kerchunk_forecast and read_native_forecast
functions.

For each member:
- Kerchunk retrieval succeeded.
- Native NetCDF retrieval succeeded.
- Streamflow values matched.
- Valid times matched.
- Reference times matched.
- Product and forecast lead identities were preserved.

All five members returned approximately 0.41 m3/s at the
tested reach and forecast hour.

### CLI integration

The installed CLI successfully retrieved medium_range_mem2
with analysis t0, f001, and f002.

- Three CSV records generated.
- All three records used Kerchunk.
- Valid and reference timestamps verified.
- Product and feature identities verified.
- Streamflow values finite.

### Automated validation

- 412 repository tests passed.
- 77 product-configuration tests passed.
- 87 operational CLI tests passed.
- Product-specific forecast horizons validated.
- Invalid forecast hours rejected before retrieval.
- Existing short-range and member 1 tests passed.
- Git whitespace validation passed.

### Limitations

- Real-data comparisons covered one date, cycle, reach,
  and forecast hour per additional member.
- CLI real-data validation covered member 2 only.
- Complete 204-hour and 240-hour forecasts were not retrieved.
- Historical model-version compatibility remains unverified.
- Additional operational products and domains remain pending.
- Cached retrieval errors do not automatically trigger
  native fallback.

### Next

- Complete documentation review and commit this milestone.
- Continue original roadmap operational-product coverage.
- Validate additional forecast families and domains separately.



## Operational NWM forecast scheduling — November 5, 2026

### Objective

Support product-specific forecast lead intervals while
preserving existing hourly operational NWM behavior.

### Implementation

- Added lead_step_hours to ProductSpec.
- Preserved hourly scheduling as the default.
- Added schedule-aware forecast lead selection.
- Validated individual forecast-hour alignment.
- Updated operational CLI forecast-window validation.
- Ensured series retrieval selects available leads only.
- Preserved optional analysis t0 handling.

### Automated validation

- 450 repository tests passed.
- 38 forecast-scheduling tests passed.
- Hourly, three-hourly, and six-hourly schedules tested.
- Invalid lead hours and empty windows rejected.
- Three-hourly series retrieval verified using a mock.
- Existing short-range and medium-range ensemble tests passed.
- Git whitespace validation passed.

### Limitations

- No additional NOAA forecast products were enabled.
- Three-hour and six-hour schedules were tested using
  temporary product configurations.
- Subhourly products are not yet supported.
- Real-data validation of additional product families
  remains pending.

### Next

- Commit the scheduling milestone.
- Validate medium_range_blend source conventions.
- Validate medium_range_no_da with analysis_assim_no_da.
- Validate long-range products and ensemble schedules.


## Operational NWM medium-range blend — November 5, 2026

### Objective

Enable the validated medium_range_blend operational NWM
product using the existing Kerchunk-first retrieval backend.

### Implementation

- Added medium_range_blend to ProductSpec configuration.
- Enabled product selection through the operational CLI.
- Configured CONUS cycles 00, 06, 12, and 18 UTC.
- Configured hourly forecast leads f001–f240.
- Preserved default analysis_assim t0 handling.
- Reused existing Kerchunk/native retrieval, timestamp
  validation, caching, and CSV/Parquet output.
- Added product configuration and CLI regression tests.

### Real-data validation

Date: 2026-04-19
Cycle: t00z
Domain: CONUS
Feature ID: 3586192

- NOAA native NetCDF source available.
- CIROH Kerchunk reference available.
- Kerchunk and native streamflow matched at f001.
- Forecast valid and reference times matched.
- Installed CLI retrieved analysis t0, f001, and f002.
- Three CSV records generated using Kerchunk.
- Product identities and timestamps verified.
- Streamflow values were finite.

### Automated validation

- 463 repository tests passed.
- 88 product configuration tests passed.
- 89 operational CLI tests passed.
- Python compilation passed.
- Git whitespace validation passed.

### Limitations

- Real-data validation covered one date, cycle, reach,
  and two forecast hours.
- Complete 240-hour retrieval remains unverified.
- Historical model-version compatibility remains unverified.
- Additional NWM products and regional domains remain pending.

### Next

- Review and commit medium_range_blend support.
- Validate medium_range_no_da and its analysis pairing.
- Continue validating long-range products separately.


## Operational NWM medium-range no-DA — November 5, 2026

### Objective

Enable `medium_range_no_da` with the correct
`analysis_assim_no_da` t0 source and three-hourly
forecast scheduling.

### Implementation

- Added `analysis_product` to `ProductSpec`, defaulting
  to `analysis_assim` for backward compatibility.
- Registered `medium_range_no_da` for CONUS.
- Configured cycles 00, 06, 12, and 18 UTC.
- Configured forecast leads f003–f240 at three-hour intervals.
- Configured `analysis_assim_no_da` as the analysis t0 source.
- Updated analysis filename, native URL, Kerchunk reference
  path, source resolution, and series product validation.
- Enabled `medium_range_no_da` in the operational CLI.
- Added configuration, source-selection, and CLI tests.

### Real-data validation

Date: 2026-04-19
Cycle: t00z
Domain: CONUS
Feature ID: 3586192

- NOAA native and CIROH Kerchunk sources available
  for analysis t0, f003, and f006.
- Kerchunk/native streamflow matched for analysis t0
  and forecast f003.
- Analysis t0 valid time: 2026-04-19 00:00 UTC.
- Analysis t0 reference time: 2026-04-18 21:00 UTC.
- Forecast f003 valid time: 2026-04-19 03:00 UTC.
- Forecast f003 reference time: 2026-04-19 00:00 UTC.
- Installed CLI retrieved analysis t0, f003, and f006.
- Three CSV records generated using Kerchunk.
- Product identities and timestamps verified.
- All three streamflow values approximately 0.30 m³/s.

### Automated validation

- 481 repository tests passed.
- 104 product configuration tests passed.
- 91 operational CLI tests passed.
- Git whitespace check clean.

### Limitations

- Real-data validation covered one date, cycle, and reach.
- Native comparison was performed for t0 and f003;
  f006 was retrieved through the CLI using Kerchunk.
- Complete 240-hour retrieval remains unverified.
- Historical model-version compatibility remains unverified.
- Regional domains and other NWM products remain pending.

### Next

- Review and commit medium-range no-DA support.
- Continue operational NWM product coverage, including
  validation of long-range ensemble products.


## Operational NWM long-range member 1 — November 5, 2026

### Objective

Enable `long_range_mem1` using the existing operational
NWM Kerchunk-first retrieval backend and six-hourly
forecast scheduling.

### Implementation

- Registered `long_range_mem1` in `PRODUCT_SPECS`.
- Configured CONUS cycles 00, 06, 12, and 18 UTC.
- Configured forecast leads f006–f720 at six-hour intervals.
- Used `long_range_mem1` as the source directory.
- Used `long_range` as the filename product.
- Used `channel_rt_1` as the channel file family.
- Enabled the product in the operational CLI.
- Reused existing Kerchunk/native retrieval and validation.
- Added configuration and CLI regression tests.
- Retained `analysis_assim` as the provisional t0 source.

### Real-data validation

Date: 2026-04-19
Cycle: t00z
Domain: CONUS
Feature ID: 3586192

- NOAA native and CIROH Kerchunk sources available
  for f006, f012, and f720.
- Kerchunk/native streamflow matched at f006.
- Forecast f006 valid time: 2026-04-19 06:00 UTC.
- Forecast f006 reference time: 2026-04-19 00:00 UTC.
- Installed CLI retrieved analysis t0, f006, and f012.
- Three CSV records generated using Kerchunk.
- Product identities and timestamps verified.
- Streamflow: t0 = 0.41, f006 = 0.33,
  f012 = 0.23 m³/s.

### Automated validation

- 499 repository tests passed.
- 120 product configuration tests passed.
- 93 operational CLI tests passed.
- Python compilation passed.
- Git whitespace check clean.

### Limitations

- Real-data retrieval covered one date, cycle, and reach.
- Native comparison was performed for f006 only.
- The f720 source exists but was not retrieved.
- `analysis_assim` t0 pairing remains scientifically
  unverified for the long-range ensemble.
- Complete 720-hour retrieval remains unverified.
- Historical model-version compatibility remains unverified.

### Next

- Review and commit long-range member 1 support.
- Investigate long-range ensemble analysis conventions.
- Continue validation of additional long-range members.


## Operational NWM long-range ensemble members 2–4 — November 5, 2026

### Objective

Enable long-range ensemble members 2, 3, and 4 using
the existing Kerchunk-first operational NWM backend.

### Implementation

- Registered `long_range_mem2`, `long_range_mem3`,
  and `long_range_mem4` in `PRODUCT_SPECS`.
- Configured CONUS cycles 00, 06, 12, and 18 UTC.
- Configured six-hourly forecast leads f006–f720.
- Used `long_range` as the filename product.
- Used `channel_rt_2`, `channel_rt_3`, and `channel_rt_4`.
- Enabled all three products in the operational CLI.
- Reused existing source resolution, forecast scheduling,
  Kerchunk/native retrieval, and output handling.
- Added parameterized configuration and CLI tests.

### Source availability

Date: 2026-04-19
Domain: CONUS

- Members 2–4 were present in NOAA native storage
  and CIROH Kerchunk references.
- Verified f006, f012, f120, f360, f540, and f720
  for cycles 00, 06, 12, and 18 UTC.
- Members 5 and 6 were not found for this date.

### Real-data validation

Date: 2026-04-19
Cycle: t00z
Feature ID: 3586192

- Kerchunk/native comparisons passed at f006
  for members 2, 3, and 4.
- f006 streamflow: approximately 0.33 m³/s
  for all three members.
- Forecast f006 valid time: 06:00 UTC.
- Forecast f006 reference time: 00:00 UTC.
- Installed CLI retrieved analysis t0, f006, and f012
  for all three members.
- All nine CLI records used Kerchunk.
- Streamflow values: t0 = 0.41, f006 = 0.33,
  f012 = 0.23 m³/s for the tested reach.
- Product identities and timestamps verified.

### Automated validation

- 553 repository tests passed.
- 168 product configuration tests passed.
- 99 operational CLI tests passed.
- Python compilation passed.
- Git whitespace check clean.

### Limitations

- Real-data retrieval covered one date, cycle, and reach.
- Native comparisons covered f006 only.
- Sampled file availability does not establish complete
  coverage of every lead through f720.
- `analysis_assim` t0 pairing remains scientifically
  unverified for long-range ensemble members.
- Full-horizon retrieval and historical-version
  compatibility remain unverified.

### Next

- Review and commit long-range ensemble members 2–4.
- Investigate long-range analysis pairing conventions.
- Continue the remaining operational NWM roadmap tasks.
