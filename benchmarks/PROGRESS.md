# NWM Operational Retrieval — Research and Validation Progress

**Last updated:** November 9, 2026
**Project:** `streamflow_getter`
**Development branch:** `research/nwm-historical-coverage`
**Requirements:** [Project roadmap](../docs/ROADMAP.md)
**Status:** Operational CONUS retrieval implemented; historical compatibility and scientific validation ongoing.

## 1. Research overview

This report consolidates the experimental evidence, implemented capabilities, and outstanding limitations for National Water Model (NWM) operational streamflow retrieval.

The research evaluates four retrieval methods, Kerchunk reference caching, NWM feature resolution, operational forecast products, historical model compatibility, and end-to-end data export.

The results distinguish three levels of evidence:

- **Implemented:** functionality exists in the production package.
- **Automated validation:** behavior has been tested using controlled or mocked inputs.
- **Real-data validation:** retrieval or processing has been tested using actual NWM data.

Successful retrieval on selected dates does not establish continuous historical coverage, full forecast-horizon compatibility, or hydrologic correctness for every location.

Current automated-test and CI status are recorded in [Development Status](../docs/DEVELOPMENT_STATUS.md).

## 2. Reference dataset and retrieval methods

### 2.1 Reference configuration

| Parameter | Configuration |
|---|---|
| Forecast date | 2026-04-19 |
| Product | `short_range` |
| Cycle | 00 UTC |
| Domain | CONUS |
| Variable | `streamflow` |
| Units | m³/s |
| Forecast leads | f001–f018 |
| Forecast cycles | 24 hourly cycles |
| Channel files for the tested date | 432 |
| Features per file | 2,776,734 |

### 2.2 Retrieval methods

Four retrieval approaches were evaluated:

1. Kerchunk remote references.
2. Native NetCDF through remote HTTP range requests.
3. Full native NetCDF download followed by local reading.
4. Native NetCDF reading from an existing local file.

The benchmarks measured elapsed retrieval time and accounted HTTP response-body bytes. The byte measurements do not include all protocol overhead.

## 3. Retrieval performance

### 3.1 Initial repeated benchmark

Six forecast hours, five trials per method and hour, one NWM reach, and 120 retrieval operations.

| Method | Median retrieval time | Accounted bytes |
|---|---:|---:|
| Native remote | 0.3554 s | 123.89 MB |
| Kerchunk | 0.4753 s | 79.41 MB |
| Native download | 0.6416 s | 429.95 MB |
| Native local | 0.0600 s | 0 |

Byte totals cover 30 operations per remote method.

Native remote retrieval was faster than Kerchunk in this experiment, while Kerchunk required fewer accounted response-body bytes.

### 3.2 Complete 18-hour forecast benchmark

**Configuration:** April 19, 2026; short-range CONUS; cycle 00 UTC; forecast leads f001–f018; five reaches; four methods; one trial per lead.

The experiment produced 72 retrieval operations and 360 streamflow records.

| Method | Median time | Accounted bytes |
|---|---:|---:|
| Native remote | 0.476 s | 74,245,753 |
| Kerchunk | 0.497 s | 47,558,690 |
| Native download | 0.545 s | 257,304,483 |
| Native local | 0.061 s | 0 |

All forecast leads passed the numerical and timestamp comparisons. No duplicate records were detected.

### 3.3 Complete 18-hour benchmark with three trials

**Configuration:** April 19, 2026; short-range CONUS; 18 forecast leads; five reaches; three trials per lead and method.

The experiment produced **216 retrieval operations and 1,080 streamflow records**.

| Method | Median time | Accounted bytes |
|---|---:|---:|
| Kerchunk | 0.482 s | 142,676,070 |
| Native remote | 0.477 s | 222,737,259 |
| Native download | 0.536 s | 771,913,449 |
| Native local | 0.060 s | 0 |

Kerchunk used approximately 35.9% fewer accounted bytes than native remote retrieval and 81.5% fewer than full native downloads.

Kerchunk and native remote retrieval had similar median times. The experiment does not establish a statistically controlled speed advantage.

### 3.4 Three-day benchmark

**Configuration:** April 19–21, 2026; short-range CONUS; cycle 00 UTC; lead f001; five reaches; four methods; one trial per date.

The experiment produced 12 retrieval operations and 60 streamflow records.

| Method | Median time | Accounted bytes |
|---|---:|---:|
| Kerchunk | 0.608 s | 7,865,304 |
| Native remote | 0.632 s | 12,313,146 |
| Native download | 0.501 s | 42,627,027 |
| Native local | 0.060 s | 0 |

Kerchunk used 36.1% fewer accounted bytes than native remote and 81.5% fewer than full native downloads.

All four methods returned matching streamflow and timestamps.

### 3.5 Five-reach benchmark

One forecast lead, one trial, five reaches.

| Method | Elapsed time | Accounted bytes |
|---|---:|---:|
| Native download | 0.595 s | 14,324,480 |
| Native remote | 0.868 s | 4,131,132 |
| Kerchunk | 0.901 s | 2,648,518 |
| Native local | 0.059 s | 0 |

The five tested feature IDs were:

| Feature ID | Array index | f001 streamflow (m³/s) |
|---|---:|---:|
| 1122645 | 100,000 | 7.08 |
| 3586192 | 351,819 | 0.41 |
| 7144704 | 750,000 | 0.00 |
| 14191043 | 1,500,000 | 16,062.71 |
| 23610484 | 2,500,000 | 0.01 |

These positions apply to the tested reference configuration and must not be assumed valid across historical NWM networks.

### 3.6 Benchmark interpretation

The repeated experiments support the conclusion that Kerchunk can substantially reduce accounted data transfer for selected streamflow queries.

They do not establish that Kerchunk is universally faster, because network conditions, cache state, and remote-service behavior were not fully controlled.

Reach-resolution time was excluded from the retrieval benchmarks.

Benchmark output includes:

- `benchmarks/results/repeated_benchmark.csv`
- `benchmarks/results/repeated_benchmark_flows.csv`

See [Benchmark documentation](README.md) for execution procedures.

### 3.7 Verification of archived benchmark results

On November 9, 2026, the existing local CSV pairs for Sections 3.3 and 3.4 were revalidated using implementation commit `5d1db8951f8917e5b77cd2bcff8cf27334a3cda3`. This was validation of stored results, not a new retrieval or performance experiment.

The files below are local generated artifacts under `benchmarks/results/`, covered by the existing Git ignore policy. Their SHA-256 fingerprints were unchanged between inventory and validation.

| File | Rows | SHA-256 |
|---|---:|---|
| `short_range_18h_5reaches_3trials.csv` | 216 | `3aba9e7ce044968245a6276169fa613737e67374aaf91f1608a10584b602dc9e` |
| `short_range_18h_5reaches_3trials_flows.csv` | 1,080 | `09da06e9164d6de8c0561596f1d1c63f1cbff164d4deb069a0c6680ee88850ba` |
| `short_range_20260419_20260421_t00z.csv` | 12 | `44eac1146b2dbf28368bf35f057f686420f18bd67f1b0f6d428f4a8a932a8981` |
| `short_range_20260419_20260421_t00z_flows.csv` | 60 | `d5014dd0c0ebaf3c207d1bee6346e45d8a06cbf02dfd7b304599c6e44126e205` |

Both pairs passed the following checks:

- Complete expected operation and flow keys, with no duplicate, missing, or unexpected combinations.
- Five expected reaches per operation: `1122645`, `3586192`, `7144704`, `14191043`, and `23610484`.
- Finite discharge values, with genuine zeros retained.
- Reference times equal to the selected forecast initialization and valid times equal to initialization plus forecast hour.
- Agreement across all methods and trials within each forecast/lead/reach group, using `rtol=1e-6` and `atol=1e-6`. The observed maximum absolute difference was `0 m3/s` in both experiments.
- Recomputed median retrieval times matched the rounded values in the existing tables, and accounted response-body byte totals matched exactly.

The 18-hour files contain 216 stored zero-valued flow rows; the three-day files contain 12. These counts include repeated method/trial rows. Both datasets have a discharge range of `0` to `16062.709641 m3/s`.

The 18-hour CSVs predate the forecast metadata columns. Their documented context (`2026-04-19`, cycle `00`, `short_range`, `conus`) was supplied only in memory for validation. The three-day CSVs already contain these fields. Both experiments contain forecast leads without analysis t0; the reference-time check above does not define the rule for analysis-derived t0 rows.

This validates the stored coverage, timing, and agreement between retrieval methods for these specific experiments. It does not establish continuous archive coverage, controlled cache performance, or a universal retrieval-speed advantage.

## 4. Reference caching and validation

### 4.1 Cache performance

| Experiment | Median time |
|---|---:|
| Same-process native remote | 0.491 s |
| Separate-process native remote | 0.943 s |
| Kerchunk without reference cache | 0.434 s |
| Kerchunk with memory cache | 0.320 s |
| Kerchunk with disk cache | 0.292 s |

The tested reference JSON contained 7,887 bytes.

Caching avoids repeated reference downloads but does not eliminate retrieval of remote model-data chunks.

A separate live experiment returned:

| Execution | Retrieval time |
|---|---:|
| First retrieval | 0.748 s |
| Cached retrieval | 0.429 s |

Both returned `0.40999999083578587 m³/s` for feature ID `3586192`, valid at April 19, 2026, 01:00 UTC.

These measurements establish cache reuse, not a controlled performance improvement.

### 4.2 Reference validation

The production cache and validation implementation supports:

- Reference structure and external byte-range checks.
- Source URL identity verification.
- ETag and source-generation metadata comparison.
- SHA-256 integrity verification.
- Atomic cache-record persistence.
- Protection against failed refreshes.
- Rejection of unresolved source-generation changes.

The original reference validation experiment inspected 32 reference entries, including seven external byte ranges.

The tested native source size was 14,324,480 bytes; the maximum referenced byte boundary matched that size.

**Limitation:** valid byte ranges, ETag comparisons, and cache integrity do not independently prove that a reference was generated from the current source contents.

## 5. Operational NWM implementation

The production implementation uses reusable modules for forecast configuration, source resolution, Kerchunk and native NetCDF retrieval, reach selection, reference validation, caching, and output serialization.

Key modules include:

| Module | Responsibility |
|---|---|
| `operational_nwm.py` | Forecast products, retrieval, timestamps, and series assembly |
| `reference_cache.py` | Reference persistence and reuse |
| `reference_validation.py` | Reference integrity and source checks |
| `reach_resolution.py` | USGS gage to NWM feature mapping |
| `spatial_resolution.py` | Geographic channel selection |
| `output.py` | CSV and Parquet serialization |
| `cli.py` | Command-line integration |

### 5.1 Supported forecast products

| Product | Cycles (UTC) | Modern forecast schedule |
|---|---|---|
| `short_range` | 00–23 hourly | f001–f018, hourly |
| `medium_range_mem1` | 00, 06, 12, 18 | f001–f240, hourly |
| `medium_range_mem2`–`mem6` | 00, 06, 12, 18 | f001–f204, hourly |
| `medium_range_blend` | 00, 06, 12, 18 | f001–f240, hourly |
| `medium_range_no_da` | 00, 06, 12, 18 | f003–f240, every 3 hours |
| `long_range_mem1`–`mem4` | 00, 06, 12, 18 | f006–f720, every 6 hours |

Historical medium-range ensemble schedules differ, as documented in Section 7.

### 5.2 Analysis timestep

The operational CLI includes an analysis timestep (`t0`) by default.

Most supported products use `analysis_assim`. The `medium_range_no_da` product uses `analysis_assim_no_da`.

For the April 19, 2026, cycle 00 UTC reference case:

- Analysis valid time: 2026-04-19 00:00 UTC.
- Analysis reference time: 2026-04-18 21:00 UTC.
- Short-range f001 valid time: 2026-04-19 01:00 UTC.
- Forecast reference time: 2026-04-19 00:00 UTC.

The observed three-hour analysis reference-time offset must not be assumed universal.

Long-range products currently use the shared `analysis_assim` t0 specified in the project roadmap. This is technically validated for selected cases, but its equivalence to the ensemble members' internal initialization states is not established.

The CLI supports `--no-t0`.

### 5.3 Selected product validation

| Product family | Real-data evidence |
|---|---|
| Short-range | Kerchunk/native agreement; CLI retrieval |
| Medium-range members 1–6 | Kerchunk/native agreement at selected f001 leads |
| Medium-range blend | Kerchunk/native agreement at f001; CLI t0–f002 |
| Medium-range no-DA | Correct analysis source; native/Kerchunk agreement for t0 and f003 |
| Long-range members 1–4 | Kerchunk/native agreement at f006; CLI t0, f006, f012 |

The principal modern validation case used April 19, 2026, cycle 00 UTC, feature ID `3586192`.

For `medium_range_no_da`, the tested t0, f003, and f006 values were approximately 0.30 m³/s.

For long-range members 1–4, the tested streamflow values were approximately 0.41 m³/s at t0, 0.33 m³/s at f006, and 0.23 m³/s at f012.

The availability of f720 source objects was sampled, but complete 720-hour retrieval was not validated.

## 6. USGS and geographic reach resolution

### 6.1 RouteLink

The validated NWM v3.1.6 RouteLink dataset contains:

- 2,776,734 unique NWM feature IDs.
- 8,735 gage-associated reaches.
- A verified association between USGS station `08165500` and NWM feature ID `3586192`.

Dataset provenance:

- Source repository: `jameshalgren/troute-lab`
- Source revision: `bb24900e3229851f6e997b037c337a8643471562`
- Dataset: `RouteLink_CONUS.nc`
- File size: 269,369,766 bytes
- SHA-256: `4957655896f4f27854f893d02fa084f9f79c1cf8e80ce77565a7356dadb6fc0e`

USGS identifiers are preserved as strings, including leading zeros. Ambiguous associations, invalid feature IDs, and duplicate selections are rejected.

### 6.2 Geographic hydrofabric

The validated NWM v3 CONUS channel hydrofabric uses EPSG:4269, while geographic input coordinates use EPSG:4326. Point-to-channel distances are calculated in EPSG:5070.

Dataset source:

`https://www.nohrsc.noaa.gov/owp_files/nwm/data_tools/NWM_channel_hydrofabric.tar.gz`

Published SHA-256:

`77d8975b543ff864cdac0736cc4f455fe86d77049c4d8b1fb8e458ec755dbc94`

### 6.3 Real-data selection results

| Selection method | Result |
|---|---|
| Point near USGS 08165500 | Feature ID 3586192 |
| Point-to-channel distance | Approximately 98.34 m |
| Geographic bounding box | 19 unique reaches |
| GeoJSON polygon | 19 unique reaches |

Reference bounding box:

- West: -99.35
- South: 30.05
- East: -99.30
- North: 30.09

An earlier independent geographic subset comparison returned 18 bounding-box reaches and 12 polygon reaches. These results came from a different validation stage and should not be treated as identical test configurations.

The CLI geographic tests used real hydrofabric data with remote NWM retrieval mocked. They did not establish live end-to-end forecast retrieval for the point, bounding-box, or polygon options.

### 6.4 Geographic limitations

Geographic selection currently targets CONUS.

The nearest channel may not represent the intended hydrologic reach, especially near confluences or parallel channels.

The default limit of 100 reaches for bounding-box and polygon requests is a safeguard, not a measured performance threshold.

Compatibility with historical NWM hydrofabric and RouteLink versions remains under investigation.

## 7. Historical NWM compatibility

### 7.1 Historical Kerchunk and native NetCDF agreement

The production operational reader was tested on selected historical NWM files using the same feature ID, `3586192`.

All comparisons below used CONUS, cycle 00 UTC, and the specified forecast lead.

| Date | Product | Lead | Kerchunk (m³/s) | Native (m³/s) | Absolute difference |
|---|---|---|---:|---:|---:|
| 2019-01-01 | short_range | f001 | 2.699999939650297 | 2.699999939650297 | 0 |
| 2022-01-01 | medium_range_mem1 | f001 | 0.9299999792128801 | 0.9299999792128801 | 0 |
| 2024-01-01 | short_range | f001 | 0.8799999803304672 | 0.8799999803304672 | 0 |
| 2019-01-01 | long_range_mem1 | f006 | 3.519999921321869 | 3.519999921321869 | 0 |
| 2022-01-01 | long_range_mem1 | f006 | 0.5999999865889549 | 0.5999999865889549 | 0 |
| 2024-01-01 | long_range_mem1 | f006 | 0.6299999859184027 | 0.6299999859184027 | 0 |

All six comparisons returned matching forecast valid and reference times.

This supports numerical agreement for the sampled files, not comprehensive compatibility across all historical NWM configurations.

### 7.2 Historical medium-range forecast schedule

CIROH reference inventories indicate a transition in medium-range ensemble forecast frequency between the April 20, 2021, 06 UTC and 12 UTC cycles.

| Initialization | Lead interval | Member 1 | Members 2–6 |
|---|---|---|---|
| Through 2021-04-20 06 UTC | 3 hours | f003–f240 | f003–f204 |
| From 2021-04-20 12 UTC | 1 hour | f001–f240 | f001–f204 |

The production forecast configuration now selects the appropriate lead schedule using the initialization date and cycle.

Real-data testing covered medium-range members 1 and 2 at 06 UTC and 12 UTC on April 20, 2021. Sixteen records were retrieved successfully.

The transition was inferred from sampled archive references, not independently confirmed from an authoritative NOAA release-history record.

### 7.3 Historical feature-ID sets

Complete feature-ID arrays were compared for CONUS short-range, cycle 00 UTC, lead f001.

| Date | Feature count | Data type |
|---|---:|---|
| 2019-01-01 | 2,729,077 | int32 |
| 2022-01-01 | 2,776,738 | int32 |
| 2024-01-01 | 2,776,734 | int64 |

| Comparison | Removed IDs | Added IDs | Identical ordering |
|---|---:|---:|---|
| 2019 → 2022 | 525 | 48,186 | No |
| 2022 → 2024 | 4 | 0 | No |
| 2019 → 2024 | 525 | 48,182 | No |

The four identifiers present in the 2022 sample but absent from 2024 were `4800002`, `4800004`, `4800006`, and `4800007`.

Of the 2,729,077 feature IDs in the 2019 sample, 2,728,552 (approximately 99.98%) were also present in 2024.

The production extractor resolves channels by feature ID rather than assuming fixed array positions. These findings do not independently justify a change to that implementation.

### 7.4 RouteLink v3.1.6 historical compatibility

The modern RouteLink identifier set was compared with the historical operational feature-ID arrays.

| Historical sample | RouteLink IDs absent from NWM | NWM IDs absent from RouteLink | Modern gage reaches absent | Exact set match |
|---|---:|---:|---:|---|
| 2019-01-01 | 48,182 | 525 | 347 | No |
| 2022-01-01 | 0 | 4 | 0 | No |
| 2024-01-01 | 0 | 0 | 0 | Yes |

For the 2019 sample, 8,388 of 8,735 modern gage-associated reaches were present, approximately 96.03%.

The 2024 operational feature-ID set matched RouteLink v3.1.6 exactly.

**Important:** identifier-set equality does not prove unchanged channel geometry, network connectivity, or USGS gage associations.

The existing RouteLink resolver should be retained. Historical version-specific gage-to-reach mapping requires authoritative metadata before automatic remapping is considered.

Existing network comparison work in `troute-lab/repro/network_stats/analyze.py` addresses network outlets and network-size differences. It does not directly establish historical USGS gage-to-feature associations.

### 7.5 Historical source coverage

| Source | Observed coverage evidence | Limitation |
|---|---|---|
| NOAA Google Cloud Storage | Successful native retrieval on sampled dates in 2019, 2022, 2024, and 2026 | Continuous availability not established |
| CIROH S3 Kerchunk | References discovered on sampled dates from 2018 through 2026 | Complete product coverage not established |
| NOAA S3 `noaa-nwm-pds` | Selected paths found in 2025 and 2026 | Earliest available date unverified |
| NOAA S3 before 2025 | Selected paths checked without success | Does not prove complete historical absence |

Historical source discovery, successful file retrieval, and continuous archive coverage are separate levels of evidence.

No authoritative continuous start and end dates have been established for every product, cycle, lead, ensemble member, or domain.

## 8. End-to-end USGS-to-Parquet validation

### 8.1 Configuration

| Parameter | Value |
|---|---|
| Forecast date | 2026-04-19 |
| Product | short_range |
| Cycle | 00 UTC |
| Domain | CONUS |
| USGS station | 08165500 |
| NWM feature ID | 3586192 |
| RouteLink | v3.1.6 |
| Forecast leads | f001–f002 |
| Analysis t0 | Enabled |
| Output | Parquet |

### 8.2 Retrieved records

| Product | Lead | Valid time (UTC) | Streamflow (m³/s) | Method |
|---|---:|---|---:|---|
| analysis_assim | 0 | 2026-04-19 00:00 | 0.41 | Kerchunk |
| short_range | 1 | 2026-04-19 01:00 | 0.41 | Kerchunk |
| short_range | 2 | 2026-04-19 02:00 | 0.40 | Kerchunk |

All three records used feature ID `3586192`.

The analysis t0 source reference time was April 18, 2026, 21:00 UTC, while its valid time matched the forecast initialization at April 19, 2026, 00:00 UTC.

Validation confirmed:

- Successful installed CLI execution.
- Correct USGS-to-RouteLink resolution.
- Three successful Kerchunk retrievals.
- Parquet output with ten expected columns.
- No missing values or duplicate records.
- 123 focused integration tests passed.

Native fallback was not exercised in this end-to-end run.

The result validates one station, one forecast date, one cycle, and two forecast leads.

## 9. Scientific and technical limitations

### 9.1 Retrieval performance

Network and cache conditions were not fully controlled. Accounted HTTP bytes exclude some protocol overhead. Benchmark timings do not include reach resolution.

Additional repeated trials across dates, cycles, reaches, and network conditions are required before making general performance claims.

### 9.2 Source compatibility

A structurally valid Kerchunk reference does not independently establish source-generation equivalence.

Historical product availability varies. A successful sample retrieval does not prove continuous archive coverage.

### 9.3 Network compatibility

Historical feature-ID sets are not identical. Feature-ID persistence does not prove geometric or topological equivalence.

Version-specific RouteLink metadata is needed to validate historical USGS-to-reach associations.

### 9.4 Forecast initialization

The long-range shared `analysis_assim` t0 follows the project roadmap, but its interpretation as the internal initialization of each ensemble member is not scientifically established.

### 9.5 Spatial selection

The nearest channel is not necessarily the hydrologically correct channel. Geographic reach selection requires additional live end-to-end testing and broader CONUS validation.

### 9.6 Scope

The implemented operational geographic workflow targets CONUS. Full forecast horizons, historical dates, additional domains, and all ensemble combinations have not been exhaustively validated.

## 10. Remaining research priorities

1. Establish systematically verified historical source availability boundaries by product, cycle, lead, and domain.
2. Validate historical RouteLink associations using appropriate version-specific datasets.
3. Expand Kerchunk/native comparisons across additional historical configurations.
4. Repeat performance experiments under controlled network and cache conditions.
5. Validate complete medium- and long-range forecast horizons.
6. Investigate long-range ensemble initialization and shared t0 interpretation.
7. Perform live end-to-end retrieval for geographic selections.
8. Extend domain coverage only when explicitly authorized and technically validated.

Further NWM retrospective and GEOGLOWS development must follow the consultation and coordination requirements in [the project roadmap](../docs/ROADMAP.md).

## 11. Reproducibility and development practices

The benchmark implementations, tests, and recorded outputs are maintained in the repository.

- [Benchmark instructions](README.md)
- [Operational NWM guide](../docs/OPERATIONAL_NWM.md)
- [Project roadmap](../docs/ROADMAP.md)
- [Main project README](../README.md)

Historical experiment notes and milestone-by-milestone development records remain recoverable through Git history, including commit `1f0d795`.

This report is a consolidated account of documented validation evidence. It does not replace the original experimental outputs or imply that untested combinations have been verified.

Development should continue through focused changes, reusable production modules, automated regression tests, and reviewable Git commits.
