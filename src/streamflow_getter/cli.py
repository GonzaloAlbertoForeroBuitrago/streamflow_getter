"""Command-line interface for streamflow_getter."""

import argparse
import math
from pathlib import Path

from streamflow_getter import __version__, nwm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="streamflow-getter",
        description="Download streamflow time series for specific reaches.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )

    sub = parser.add_subparsers(dest="source")

    # Preserve the existing retrospective command.
    p = sub.add_parser(
        "nwm",
        help="NWM retrospective, CONUS (hourly, 1979-)",
    )
    p.add_argument(
        "--reach",
        type=int,
        action="append",
        default=[],
        help="feature_id (COMID); repeat for several",
    )
    p.add_argument(
        "--gage",
        action="append",
        default=[],
        help="USGS gage ID, e.g. 01646500; repeat for several",
    )
    p.add_argument(
        "--version",
        dest="nwm_version",
        choices=["3.0", "2.1"],
        default="3.0",
        help="retrospective version (3.0 ends 2023-02, 2.1 ends 2020-12)",
    )
    p.add_argument("--start", required=True, help="e.g. 2020-01-01")
    p.add_argument("--end", required=True, help="e.g. 2020-01-31")
    p.add_argument("--variable", default="streamflow")
    p.add_argument("--out", required=True, help="output CSV path")

    # Operational NWM short-range CONUS retrieval.

    operational = sub.add_parser(
        "nwm-operational",
        help="Operational NWM CONUS forecasts",
    )
    operational.add_argument("--date", required=True)
    operational.add_argument("--cycle", type=int, default=0)

    operational.add_argument(
        "--product",
        choices=[
            "short_range",
            "medium_range_mem1",
            "medium_range_mem2",
            "medium_range_mem3",
            "medium_range_mem4",
            "medium_range_mem5",
            "medium_range_mem6",
        ],
        default="short_range",
        help="Operational NWM product (default: short_range)",
    )


    operational.add_argument(
        "--reach",
        type=int,
        action="append",
        default=[],
        help="NWM feature ID; repeat for several reaches",
    )
    operational.add_argument(
        "--gage",
        action="append",
        default=[],
        help="USGS gage ID; preserve leading zeros",
    )
    operational.add_argument(
        "--routelink",
        help="Path to local RouteLink NetCDF for gage resolution",
    )
    operational.add_argument(
        "--point",
        type=float,
        nargs=2,
        metavar=("LONGITUDE", "LATITUDE"),
        help="Select the nearest NWM channel to a geographic point",
    )
    operational.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Select NWM reaches intersecting a geographic bounding box",
    )

    operational.add_argument(
        "--polygon",
        metavar="GEOJSON_PATH",
        help="Select NWM reaches intersecting a GeoJSON Polygon or MultiPolygon",
    )

    operational.add_argument(
        "--hydrofabric",
        help="Path to the NWM channel hydrofabric geodatabase",
    )
    operational.add_argument(
        "--max-distance-m",
        type=float,
        default=500.0,
        help="Maximum point-to-channel distance in meters (default: 500)",
    )
    operational.add_argument(
        "--max-reaches",
        type=int,
        default=100,
        help="Maximum reaches allowed per operational request (default: 100)",
    )
    operational.add_argument(
        "--start-hour",
        type=int,
        default=1,
    )
    operational.add_argument(
        "--end-hour",
        type=int,
        default=18,
    )
    operational.add_argument(
        "--no-t0",
        action="store_true",
        help="Exclude analysis_assim t0",
    )
    operational.add_argument("--cache-dir")
    operational.add_argument(
        "--format",
        choices=["csv", "parquet"],
        dest="output_format",
    )
    operational.add_argument("--out", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.source == "nwm":
        if not (args.reach or args.gage):
            parser.error("nwm needs at least one --reach or --gage")

        ds = nwm.open_chrtout(args.nwm_version)
        reaches = list(args.reach) + list(
            nwm.gages_to_reaches(args.gage, ds).values()
        )

        df = nwm.fetch(
            reaches,
            args.start,
            args.end,
            args.variable,
            ds=ds,
        )
        df.to_csv(args.out, index=False)
        print(f"wrote {len(df)} rows to {args.out}")
        return 0

    if args.source == "nwm-operational":
        # Import operational dependencies only when requested.
        from streamflow_getter.operational_nwm import (
            ForecastConfig,
            fetch_operational_series,
        )
        from streamflow_getter.output import (
            resolve_output_format,
            write_timeseries,
        )


        config = ForecastConfig(
            date=args.date,
            cycle=args.cycle,
            product=args.product,
        )


        # Reject invalid forecast-hour ranges before remote access.
        if args.start_hour < 1 or args.end_hour < args.start_hour:
            raise ValueError(
                "Invalid forecast hour range: start_hour must be "
                "positive and end_hour must not precede start_hour"
            )


        # Validate product-specific forecast hours before remote access.
        config.forecast_hours(args.start_hour, args.end_hour)


        # Validate output before starting remote retrieval.
        resolve_output_format(args.out, args.output_format)

        destination_path = Path(args.out).expanduser()
        if destination_path.exists():
            raise FileExistsError(
                f"Output already exists: {destination_path}"
            )

        # Validate reach-selection arguments before remote NWM access.
        if not (
            args.reach or args.gage or args.point
            or args.bbox or args.polygon
        ):
            raise ValueError(
                "Provide at least one --reach, --gage, "
                "--point, --bbox, or --polygon"
            )

        if (
            args.point or args.bbox or args.polygon
        ) and not args.hydrofabric:
            raise ValueError(
                "--hydrofabric is required for geographic selection"
            )

        if args.point and (
            not math.isfinite(args.max_distance_m)
            or args.max_distance_m <= 0
        ):
            raise ValueError(
                "max_distance_m must be positive and finite"
            )

        if args.hydrofabric and not (
            args.point or args.bbox or args.polygon
        ):
            raise ValueError(
                "--hydrofabric requires --point, --bbox, or --polygon"
            )

        if args.max_reaches < 1:
            raise ValueError(
                "max_reaches must be a positive integer"
            )

        if args.gage and not args.routelink:
            raise ValueError(
                "--routelink is required when using --gage"
            )

        if args.routelink and not args.gage:
            raise ValueError(
                "--routelink requires at least one --gage"
            )

        reaches = list(args.reach)

        # Resolve geographic bounding-box selections locally.
        if args.bbox:
            from streamflow_getter.spatial_resolution import reaches_in_bbox

            selected_reaches = reaches_in_bbox(
                args.hydrofabric,
                tuple(args.bbox),
            )

            if not selected_reaches:
                raise ValueError(
                    "No NWM reaches found within the bounding box"
                )

            if len(selected_reaches) > args.max_reaches:
                raise ValueError(
                    f"Bounding box selected {len(selected_reaches)} reaches; "
                    f"maximum allowed is {args.max_reaches}"
                )

            reaches.extend(selected_reaches)

            print(
                f"Selected {len(selected_reaches)} NWM reaches "
                "from geographic bounding box"
            )



        # Resolve GeoJSON polygon selections locally.
        if args.polygon:
            from streamflow_getter.spatial_resolution import (
                load_geojson_polygon,
                reaches_in_polygon,
            )

            polygon = load_geojson_polygon(args.polygon)

            selected_reaches = reaches_in_polygon(
                args.hydrofabric,
                polygon,
            )

            if not selected_reaches:
                raise ValueError(
                    "No NWM reaches found within the polygon"
                )

            if len(selected_reaches) > args.max_reaches:
                raise ValueError(
                    f"Polygon selected {len(selected_reaches)} reaches; "
                    f"maximum allowed is {args.max_reaches}"
                )

            reaches.extend(selected_reaches)

            print(
                f"Selected {len(selected_reaches)} NWM reaches "
                "from GeoJSON polygon"
            )



        # Resolve the nearest NWM channel to a geographic point.
        if args.point:
            from streamflow_getter.spatial_resolution import (
                load_nearby_reaches,
                nearest_reaches,
            )

            longitude, latitude = args.point

            nearby = load_nearby_reaches(
                args.hydrofabric,
                longitude,
                latitude,
                max_distance_m=args.max_distance_m,
            )

            candidates = nearest_reaches(
                nearby,
                longitude,
                latitude,
                max_distance_m=args.max_distance_m,
                limit=1,
            )

            if not candidates:
                raise ValueError(
                    "No NWM reaches found within the maximum distance"
                )

            selected = candidates[0]
            reaches.append(selected["feature_id"])

            print(
                f"Selected NWM reach {selected['feature_id']} "
                f"at {selected['distance_m']:.2f} m"
            )

        # Resolve USGS gages through the local RouteLink index.
        if args.gage:
            from streamflow_getter.reach_resolution import (
                load_gage_index,
                resolve_gages,
            )

            index = load_gage_index(args.routelink)
            resolved = resolve_gages(args.gage, index)
            reaches.extend(resolved.values())

        # Validate the combined reach selection.
        if any(reach <= 0 for reach in reaches):
            raise ValueError(
                "Reach IDs must be positive integers"
            )

        if len(reaches) != len(set(reaches)):
            raise ValueError(
                "Duplicate NWM feature IDs are not allowed"
            )

        if (args.bbox or args.polygon) and len(reaches) > args.max_reaches:
            raise ValueError(
                f"Request contains {len(reaches)} reaches; "
                f"maximum allowed is {args.max_reaches}"
            )

        # Retrieve operational NWM streamflow after local validation.
        frame = fetch_operational_series(
            config,
            reaches,
            args.start_hour,
            args.end_hour,
            include_t0=not args.no_t0,
            cache_dir=args.cache_dir,
        )

        destination = write_timeseries(
            frame,
            args.out,
            output_format=args.output_format,
        )

        print(f"wrote {len(frame)} rows to {destination}")
        return 0

    return 0
