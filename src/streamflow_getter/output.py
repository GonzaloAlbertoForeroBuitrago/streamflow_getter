
"""CSV and Parquet output for streamflow time series."""

import os
import tempfile
from pathlib import Path

import pandas as pd


SUPPORTED_FORMATS = {"csv", "parquet"}


def resolve_output_format(path, output_format=None):
    """Resolve CSV or Parquet from an explicit format or file extension."""
    path = Path(path)

    if output_format is not None:
        if not isinstance(output_format, str):
            raise ValueError("Output format must be csv or parquet")

        selected = output_format.lower()

        if selected not in SUPPORTED_FORMATS:
            raise ValueError("Output format must be csv or parquet")

        suffix = path.suffix.lower().lstrip(".")

        if suffix in SUPPORTED_FORMATS and suffix != selected:
            raise ValueError(
                "Output format conflicts with file extension"
            )

        return selected

    suffix = path.suffix.lower().lstrip(".")

    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(
            "Cannot infer output format; use .csv, .parquet, "
            "or specify output_format"
        )

    return suffix


def write_timeseries(
    frame: pd.DataFrame,
    path,
    *,
    output_format=None,
):
    """Safely write a validated time-series DataFrame.

    Existing files are not overwritten. A temporary file is
    serialized first, then published with exclusive creation.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Expected a pandas DataFrame")

    if frame.empty:
        raise ValueError("Cannot write an empty time series")

    destination = Path(path).expanduser()
    selected = resolve_output_format(destination, output_format)

    if destination.exists():
        raise FileExistsError(
            f"Output already exists: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None
    published = False

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=".streamflow-output-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        if selected == "csv":
            frame.to_csv(temporary_path, index=False)
        else:
            frame.to_parquet(
                temporary_path,
                engine="pyarrow",
                index=False,
            )

        with destination.open("xb") as output:
            published = True

            with temporary_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)

    except Exception:
        if published:
            destination.unlink(missing_ok=True)
        raise

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return destination
