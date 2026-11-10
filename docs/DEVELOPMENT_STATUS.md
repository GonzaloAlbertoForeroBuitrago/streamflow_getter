# Development Status — NWM Implementation Checkpoint

**Checkpoint date:** November 7, 2026
**Updated:** November 10, 2026
**Branch:** `research/nwm-historical-coverage`
**Status:** Operational NWM backend submitted in PR #6; shared single-reference and batch preparation validated locally; remaining backend and Alabama research work pending.

## 1. Completed Work

- Implemented operational NWM forecast retrieval across supported CONUS short-, medium-, and long-range products.
- Preserved retrospective NWM retrieval for versions 2.1 and 3.0.
- Implemented Kerchunk-first retrieval with native NetCDF fallback under supported conditions.
- Added optional reference caching with integrity and source validation.
- Added shared single-reference preparation and batch preparation with request validation and source deduplication.
- Implemented reach selection using NWM feature IDs, USGS gages, geographic points, bounding boxes, and polygons.
- Added analysis timestep (`t0`) handling, forecast metadata, and CSV/Parquet output.
- Consolidated production modules, tests, benchmarks, and documentation.
- Integrated upstream's `research-plan.md` without modifying the original `docs/ROADMAP.md`.

## 2. Verification Completed

### Original checkpoint — November 7, 2026 (`dbc5a27`)

- 638 automated tests passed.
- Python package import and CLI commands verified.
- Wheel and source distribution built successfully.
- Wheel installation and CLI execution verified in an isolated environment.
- Git formatting checks passed.
- Working tree clean at the checkpoint.
- Historical coverage, source agreement, reference caching, and retrieval performance documented in `benchmarks/PROGRESS.md`.

These checks validate the tested software behavior and selected research cases; they do not establish complete scientific validation of every NWM product or historical period.

### CI dependency correction — November 9, 2026

- Updated the CI workflow to install the `operational`, `spatial`, and `parquet` extras, using `--locked` for synchronization and execution.
- Local environment: macOS ARM64, Python 3.14.6, uv 0.13.4.
- Full test suite result: **638 passed in 1.90 seconds**.
- `git diff --check` passed; `pyproject.toml` and `uv.lock` were unchanged.

Validated commands:

    uv sync --locked --extra operational --extra spatial --extra parquet
    uv run --locked --extra operational --extra spatial --extra parquet pytest -q -ra

This is local validation. Verify the GitHub Actions result for the updated PR head after pushing the commit.

### Live geographic retrieval and controlled fallback — November 9, 2026

At implementation commit `55c2ab571393429cadb9cf801f89bd5da9493af0`:

- Live production CLI retrieval passed for a point CSV, bounding-box CSV, and equivalent rectangular-polygon Parquet: 1, 19, and 19 rows, all through Kerchunk. See [PROGRESS Section 6.5](../benchmarks/PROGRESS.md#65-live-geographic-retrieval-and-export).
- Controlled missing-reference injection led the production coordinator to retrieve real native NetCDF data for reach `3586192`. Method, fallback reason, metadata, timestamps, and numerical agreement with the accepted point records passed. See [PROGRESS Section 5.4](../benchmarks/PROGRESS.md#54-controlled-native-fallback-integration).

These local acceptance cases cover April 19, 2026, cycle 00, short-range CONUS f001 with reference caching disabled. Exact UTC execution times, configurations, limitations, and artifact fingerprints are recorded in the linked sections. Full-suite results and hosted-CI verification are tracked separately in this section.

### Local cache I/O correction — recorded November 10, 2026

Validated the correction in a working tree based on `2aca2e78a455c63139f9924b22931c66e0ab2cf3`.

- `load_cache_record` preserves recovery for missing or invalid cached records and propagates other local filesystem errors.
- Three regression cases cover `PermissionError`, `IsADirectoryError`, and `OSError` with `errno.EIO`. They verify that the same exception propagates, the reference-body downloader is not called, and existing cache bytes remain unchanged.
- Local environment: macOS ARM64, Python 3.14.6, pytest 9.1.1.
- Locked full-suite result: **641 passed in 1.90 seconds**.
- `git diff --check` passed; `pyproject.toml`, `uv.lock`, and `docs/ROADMAP.md` were unchanged.

Validated command:

    uv run --locked --extra operational --extra spatial --extra parquet pytest -q -ra

Remote freshness metadata is still checked before the local cache read. This is local automated validation; verify GitHub Actions for the published PR head.

### Reference preparation and reuse — recorded November 10, 2026

Validated in working trees based on `e857f6987a07fafe7d3781307c528102bf99199d`. The operational-module fingerprints distinguish the intermediate and completed implementations in [PROGRESS Section 4.3](../benchmarks/PROGRESS.md#43-shared-reference-preparation).

- The Kerchunk reader and preparation APIs share source resolution, reference validation, and the existing cache implementation.
- Batch requests are validated before acquisition, follow product-specific lead schedules, include analysis t0 by default, and deduplicate by reference path plus native URL. Results contain compact source summaries; acquisition errors propagate unchanged.
- Local environment: macOS ARM64, Python 3.14.6, pytest 9.1.1.
- Intermediate single-reference implementation (C3): **643 passed in 1.32 seconds**.
- Completed batch implementation (C5): **655 passed in 0.92 seconds**, using the locked full-suite command recorded above.
- Live single-reference preparation followed by production retrieval passed (C4); see [PROGRESS Section 4.4](../benchmarks/PROGRESS.md#44-live-preparation-followed-by-cached-retrieval).
- Live preparation of five unique analysis/forecast references and unchanged warm-cache reuse passed (C6); see [PROGRESS Section 4.5](../benchmarks/PROGRESS.md#45-live-batch-preparation-and-reuse).

The final documentation consolidation preserves the source and test fingerprints validated in C5 and C6. These are local results; verify GitHub Actions for the published PR head separately.

## 3. Known Limitations and Remaining Work

- Reference caching is optional rather than enabled by default.
- Explicit batch reference preparation is implemented; date-range, recent-period, and event request planning and CLI integration remain pending.
- Shared analysis reference preparation does not yet share decoded t0 flow rows across ensemble series.
- Cached retrieval errors currently propagate rather than invoking native fallback.
- Historical NWM network compatibility requires version-specific verification.
- Complete forecast-horizon and historical product coverage have not been verified.
- Some analysis-to-forecast `t0` relationships require additional scientific review.
- NRDS and GEOGLOWS adapters remain future development work.

**Next backend task:** Classify remote availability, local cache I/O, and integrity failures before changing cached-path fallback or default-cache behavior. Build date-range, recent-period, and event request planning on the validated preparation APIs, with the product/time/provenance coordination described below.

## 4. Next Research Phase — Alabama

`docs/ROADMAP.md` remains the controlling guide. Reconcile the root `research-plan.md` with verified NRDS data and the current upstream contributions before implementing the Alabama comparison. The next design task is to align product/version selection, CLI compatibility, and time and provenance fields with [PR #4](https://github.com/jameshalgren/streamflow_getter/pull/4) and [PR #5](https://github.com/jameshalgren/streamflow_getter/pull/5).

Close the backend gaps in reliability, request planning, and output metadata needed for the pilot before new NRDS implementation. Verify the actual geographic coverage and any version-matched mapping before selecting the pilot.

Planned activities:

1. Review the research plan and confirm data availability, temporal coverage, and spatial identifiers.
2. Reuse suitable version-matched mappings and develop only the NRDS access and matching components required by the verified pilot.
3. Align comparable forecasts, locations, and timestamps.
4. Implement reproducible comparison statistics and tests.
5. Document the methodology, results, assumptions, and limitations.

Continue Alabama work on `research/alabama-nwm-nrds-comparison`; its last recorded checkpoint is `dbc5a27`. Backend corrections and reference-preparation development continue on `research/nwm-historical-coverage`. Website development follows backend acceptance.

## 5. Contribution Status

The NWM implementation has been submitted in [PR #6](https://github.com/jameshalgren/streamflow_getter/pull/6), from `research/nwm-historical-coverage`.

Maintain this existing contribution through focused corrections and validation. The reference-preparation contribution consolidates implementation, regression coverage, and bounded live acceptance evidence. Local validation has passed; GitHub Actions must be checked for the published PR head.

Preserve the original roadmap, keep Git history traceable, and avoid unnecessary dependencies or duplicated implementations.
