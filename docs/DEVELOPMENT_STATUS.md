# Development Status — NWM Implementation Checkpoint

**Checkpoint date:** November 7, 2026
**Updated:** November 9, 2026
**Branch:** `research/nwm-historical-coverage`
**Status:** Implemented operational NWM backend submitted in PR #6; CI dependency correction validated locally; remaining backend and Alabama research work pending.

## 1. Completed Work

- Implemented operational NWM forecast retrieval across supported CONUS short-, medium-, and long-range products.
- Preserved retrospective NWM retrieval for versions 2.1 and 3.0.
- Implemented Kerchunk-first retrieval with native NetCDF fallback under supported conditions.
- Added optional reference caching with integrity and source validation.
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

## 3. Known Limitations and Remaining Work

- Reference caching is optional rather than enabled by default.
- Advance preprocessing of Kerchunk references remains incomplete.
- Cached retrieval failures do not always trigger native fallback.
- Historical NWM network compatibility requires version-specific verification.
- Complete forecast-horizon and historical product coverage have not been verified.
- Some analysis-to-forecast `t0` relationships require additional scientific review.
- NRDS and GEOGLOWS adapters remain future development work.

## 4. Next Research Phase — Alabama

`docs/ROADMAP.md` remains the controlling guide. Reconcile the root `research-plan.md` with verified NRDS data and the current upstream contributions before implementing the Alabama comparison. The next design task is to align product/version selection, CLI compatibility, and time and provenance fields with [PR #4](https://github.com/jameshalgren/streamflow_getter/pull/4) and [PR #5](https://github.com/jameshalgren/streamflow_getter/pull/5).

Close the backend gaps in reliability, request planning, and output metadata needed for the pilot before new NRDS implementation. Verify the actual geographic coverage and any version-matched mapping before selecting the pilot.

Planned activities:

1. Review the research plan and confirm data availability, temporal coverage, and spatial identifiers.
2. Reuse suitable version-matched mappings and develop only the NRDS access and matching components required by the verified pilot.
3. Align comparable forecasts, locations, and timestamps.
4. Implement reproducible comparison statistics and tests.
5. Document the methodology, results, assumptions, and limitations.

Continue Alabama work on `research/alabama-nwm-nrds-comparison`. At this update, that branch remains at `dbc5a27` while the CI and documentation corrections are made on `research/nwm-historical-coverage`. Website development follows backend acceptance.

## 5. Contribution Status

The NWM implementation has been submitted in [PR #6](https://github.com/jameshalgren/streamflow_getter/pull/6), from `research/nwm-historical-coverage`.

Maintain this existing contribution through focused corrections and validation. The CI dependency correction has passed local validation; GitHub Actions verification for the updated PR head remains pending.

Preserve the original roadmap, keep Git history traceable, and avoid unnecessary dependencies or duplicated implementations.
