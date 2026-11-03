"""Configuration and validated extraction for operational NWM forecasts."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import numbers

import numpy as np


@dataclass(frozen=True)
class ForecastConfig:
    """Identify one operational NWM short-range CONUS forecast cycle."""

    date: str = "2026-04-19"
    cycle: int = 0
    product: str = "short_range"
    domain: str = "conus"

    def __post_init__(self):
        try:
            if not isinstance(self.date, str) or date.fromisoformat(self.date).isoformat() != self.date:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc

        if isinstance(self.cycle, bool) or not isinstance(self.cycle, int):
            raise ValueError("cycle must be an integer")
        if not 0 <= self.cycle <= 23:
            raise ValueError("cycle must be between 0 and 23")
        if self.product != "short_range":
            raise ValueError("Only short_range is currently supported")
        if self.domain != "conus":
            raise ValueError("Only the CONUS domain is currently supported")

    @property
    def date_folder(self) -> str:
        return "nwm." + self.date.replace("-", "")

    @property
    def cycle_name(self) -> str:
        return f"t{self.cycle:02d}z"

    def filename(self, hour: int) -> str:
        """Build a validated short-range channel_rt filename."""
        if isinstance(hour, bool) or not isinstance(hour, int):
            raise ValueError("Forecast lead hour must be an integer")
        if hour < 1:
            raise ValueError("Forecast lead hour must be positive")
        return (
            f"nwm.{self.cycle_name}.{self.product}."
            f"channel_rt.f{hour:03d}.{self.domain}.nc"
        )

    def native_url(self, hour: int) -> str:
        return (
            "https://storage.googleapis.com/national-water-model/"
            f"{self.date_folder}/{self.product}/{self.filename(hour)}"
        )

    def reference_path(self, hour: int) -> str:
        return (
            "ciroh-nwm-zarr-copy/national-water-model/"
            f"{self.date_folder}/{self.product}/{self.filename(hour)}.json"
        )

    def validate_timestamps(self, hour: int, valid_time, reference_time) -> None:
        """Verify forecast timestamps against the requested cycle."""
        self.filename(hour)
        expected_reference = datetime.combine(
            date.fromisoformat(self.date), datetime.min.time()
        ).replace(hour=self.cycle)
        expected_valid = expected_reference + timedelta(hours=hour)
        actual_reference = np.datetime64(reference_time, "s")
        actual_valid = np.datetime64(valid_time, "s")
        if actual_reference != np.datetime64(expected_reference, "s"):
            raise ValueError(f"Incorrect forecast reference time for f{hour:03d}")
        if actual_valid != np.datetime64(expected_valid, "s"):
            raise ValueError(f"Incorrect forecast valid time for f{hour:03d}")


def extract_streamflow(ds, reach_ids: list[int]) -> dict[int, float]:
    """Extract one-timestep streamflow by exact NWM feature ID.

    Preserve requested order and reject missing or duplicated requested IDs,
    duplicated matching dataset IDs, malformed IDs, and nonfinite values.
    """
    requested = list(reach_ids)
    if not requested:
        raise ValueError("At least one reach is required")
    if any(
        isinstance(reach, (bool, np.bool_))
        or not isinstance(reach, numbers.Integral)
        or int(reach) <= 0
        for reach in requested
    ):
        raise ValueError("Reach IDs must be positive integers")
    requested = [int(reach) for reach in requested]
    if len(requested) != len(set(requested)):
        raise ValueError("Duplicate reach IDs are not allowed")

    if "feature_id" not in ds or "streamflow" not in ds:
        raise ValueError("NWM dataset requires feature_id and streamflow")
    ids = np.asarray(ds["feature_id"].values)
    if ids.ndim != 1:
        raise ValueError("feature_id must be one-dimensional")

    mapping = {}
    wanted = set(requested)
    for position, raw_id in enumerate(ids):
        if isinstance(raw_id, (bool, np.bool_)) or not isinstance(raw_id, numbers.Integral):
            raise ValueError("NWM feature IDs must be integers")
        feature_id = int(raw_id)
        if feature_id in wanted:
            if feature_id in mapping:
                raise ValueError(f"Duplicate feature ID {feature_id}")
            mapping[feature_id] = position

    missing = wanted - mapping.keys()
    if missing:
        raise ValueError(f"Missing reaches: {sorted(missing)}")
    indices = [mapping[reach] for reach in requested]
    selected_ids = np.asarray(ds["feature_id"].isel(feature_id=indices).values)
    if not np.array_equal(selected_ids, np.asarray(requested)):
        raise ValueError("Feature-ID mismatch during streamflow extraction")

    flows = np.asarray(ds["streamflow"].isel(feature_id=indices).values, dtype=float)
    if flows.shape != (len(requested),):
        raise ValueError("Unexpected streamflow shape")
    if not np.isfinite(flows).all():
        raise ValueError("Non-finite streamflow values found")
    return {reach: float(flow) for reach, flow in zip(requested, flows)}



def read_kerchunk_forecast(
    config: ForecastConfig,
    hour: int,
    reach_ids: list[int],
    *,
    cache_dir=None,
) -> dict:
    """Read an operational NWM forecast through validated Kerchunk references.

    When cache_dir is None, use the original uncached reader.
    Otherwise, reuse or refresh a validated reference-cache record.
    """
    import json
    from pathlib import Path

    import fsspec
    import s3fs
    import xarray as xr

    from streamflow_getter.reference_cache import (
        fetch_remote_metadata,
        load_fresh_reference,
    )
    from streamflow_getter.reference_validation import (
        validate_reference,
        valid_source_identity,
    )

    config.filename(hour)

    reference_path = config.reference_path(hour)
    expected_url = config.native_url(hour)

    s3 = s3fs.S3FileSystem(anon=True)

    if cache_dir is None:
        # Preserve the existing uncached behavior.
        with s3.open(reference_path, "rb") as file:
            reference_bytes = file.read()

        reference = json.loads(reference_bytes)
        reference_json_bytes = len(reference_bytes)

    else:
        cache_root = Path(cache_dir).expanduser()

        cache_file = (
            cache_root
            / config.date_folder
            / config.product
            / f"{config.filename(hour)}.cache.json"
        )

        def metadata_provider():
            return fetch_remote_metadata(
                reference_path,
                expected_url,
                s3=s3,
            )

        def downloader():
            with s3.open(reference_path, "rb") as file:
                return file.read()

        reference = load_fresh_reference(
            cache_file,
            expected_url,
            metadata_provider,
            downloader,
        )

        # This is the serialized reference size, not network bytes.
        reference_json_bytes = len(
            json.dumps(reference).encode("utf-8")
        )

    # Validate both cached and uncached references.
    if not validate_reference(reference):
        raise ValueError("Invalid Kerchunk reference structure")

    if not valid_source_identity(reference, expected_url):
        raise ValueError("Incorrect Kerchunk source identity")

    fs = fsspec.filesystem(
        "reference",
        fo=reference,
        remote_protocol="https",
        remote_options={"asynchronous": True},
        asynchronous=True,
        skip_instance_cache=True,
    )

    with xr.open_zarr(
        fs.get_mapper(""),
        consolidated=False,
        zarr_format=2,
    ) as ds:
        flows = extract_streamflow(ds, reach_ids)

        valid_time = ds.time.values[0]
        reference_time = ds.reference_time.values[0]

        config.validate_timestamps(
            hour,
            valid_time,
            reference_time,
        )

    return {
        "forecast_date": config.date,
        "forecast_cycle": config.cycle,
        "product": config.product,
        "domain": config.domain,
        "lead_hour": hour,
        "method": "kerchunk",
        "valid_time": str(valid_time),
        "reference_time": str(reference_time),
        "streamflow_m3s": flows,
        "reference_json_bytes": reference_json_bytes,
    }



def read_native_forecast(
    config: ForecastConfig,
    hour: int,
    reach_ids: list[int],
) -> dict:
    """Read and validate one operational NWM forecast via native NetCDF."""
    import fsspec
    import xarray as xr

    # Validate the requested forecast before remote access.
    config.filename(hour)
    url = config.native_url(hour)

    with fsspec.open(
        url,
        mode="rb",
        block_size=1024 * 1024,
        cache_type="bytes",
    ) as remote_file:
        with xr.open_dataset(
            remote_file,
            engine="h5netcdf",
        ) as ds:
            flows = extract_streamflow(ds, reach_ids)

            valid_time = ds.time.values[0]
            reference_time = ds.reference_time.values[0]

            config.validate_timestamps(
                hour,
                valid_time,
                reference_time,
            )

    return {
        "forecast_date": config.date,
        "forecast_cycle": config.cycle,
        "product": config.product,
        "domain": config.domain,
        "lead_hour": hour,
        "method": "native_remote",
        "valid_time": str(valid_time),
        "reference_time": str(reference_time),
        "streamflow_m3s": flows,
        "reference_json_bytes": 0,
    }




def fetch_operational_forecast(
    config: ForecastConfig,
    hour: int,
    reach_ids: list[int],
    *,
    cache_dir=None,
) -> dict:
    """Fetch operational NWM data with controlled native fallback.

    Kerchunk is attempted first.

    With caching disabled, recognized access failures may trigger
    native NetCDF retrieval.

    With caching enabled, errors are propagated until cache-specific
    and remote-access failures can be distinguished reliably.
    """
    import json

    try:
        if cache_dir is None:
            return read_kerchunk_forecast(
                config,
                hour,
                reach_ids,
            )

        return read_kerchunk_forecast(
            config,
            hour,
            reach_ids,
            cache_dir=cache_dir,
        )

    except PermissionError:
        raise

    except (OSError, json.JSONDecodeError) as exc:
        if cache_dir is not None:
            raise

        kerchunk_error = exc

    try:
        result = read_native_forecast(
            config,
            hour,
            reach_ids,
        )
    except Exception as native_error:
        raise RuntimeError(
            "Both Kerchunk and native NWM retrieval failed"
        ) from native_error

    result["fallback_reason"] = (
        f"{type(kerchunk_error).__name__}: {kerchunk_error}"
    )

    return result
