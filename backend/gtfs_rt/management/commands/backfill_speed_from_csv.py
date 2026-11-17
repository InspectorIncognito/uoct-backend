import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
from django.core.management import BaseCommand, CommandError
from gtfs_rt.processors.csv_backfill import (
    CSV_TIMEZONE,
    get_file_date,
    load_gps_gdf,
    load_route_dictionary,
)
from gtfs_rt.processors.speed import calculate_speed
from rest_api.models import Segment, Shape, Speed
from velocity.constants import TEMPORAL_SEGMENT_SECONDS
from velocity.utils import generate_grid



class Command(BaseCommand):
    help = (
        "Calculate speeds from daily GPS CSV exports "
        "(Detalle_Registros_GPS_REP_YYYYMMDD.csv or .zip)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            required=True,
            help="CSV/zip file or folder with daily CSV/zip files.",
        )
        parser.add_argument(
            "--dictionary",
            required=True,
            help="Services dictionary CSV (Diccionario-Servicios_YYYYMMDD.csv).",
        )
        parser.add_argument(
            "--from-hour",
            type=int,
            default=0,
            help="First local hour (America/Santiago) to process, inclusive. Default 0.",
        )
        parser.add_argument(
            "--to-hour",
            type=int,
            default=24,
            help="Last local hour (America/Santiago) to process, exclusive. Default 24.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing Speed records of each processed day before inserting.",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        if input_path.is_dir():
            files = sorted(
                p
                for p in input_path.iterdir()
                if p.suffix.lower() in (".csv", ".zip") and get_file_date(p)
            )
        elif input_path.is_file():
            files = [input_path]
        else:
            raise CommandError(f"{input_path} not found")
        if not files:
            raise CommandError(f"No GPS files found in {input_path}")

        from_hour, to_hour = options["from_hour"], options["to_hour"]
        if not 0 <= from_hour < to_hour <= 24:
            raise CommandError("Hours must satisfy 0 <= --from-hour < --to-hour <= 24")

        if Shape.objects.count() == 0:
            raise CommandError("No shapes found")
        elif Segment.objects.count() == 0:
            raise CommandError("No segments found")

        exact, fallback = load_route_dictionary(options["dictionary"])
        print(f"Loaded {len(exact)} routes from dictionary.")

        grid_obj = generate_grid()

        for path in files:
            self.process_file(
                path, exact, fallback, grid_obj, options["replace"], from_hour, to_hour
            )

    def process_file(self, path, exact, fallback, grid_obj, replace, from_hour, to_hour):
        file_start_time = time.time()
        print(f"Processing {path.name}...")
        gps_gdf, stats = load_gps_gdf(path, exact, fallback)
        if gps_gdf.empty:
            print(f"No GPS pulses in {path.name}, skipping.")
            return
        unmapped_pct = 100 * stats["unmapped_pulses"] / max(stats["pulses"], 1)
        print(
            f"Read {stats['pulses']} GPS pulses ({unmapped_pct:.1f}% without route), "
            f"{stats['pulses_with_bearing']} kept after bearing calculation."
        )

        freq = f"{TEMPORAL_SEGMENT_SECONDS}s"
        first_window = gps_gdf["timestamp"].min().floor(freq)
        last_window = gps_gdf["timestamp"].max().floor(freq)
        windows = pd.date_range(first_window, last_window, freq=freq)
        local_hours = windows.tz_convert(CSV_TIMEZONE).hour
        windows = windows[(local_hours >= from_hour) & (local_hours < to_hour)]
        if windows.empty:
            print(f"No windows between {from_hour}:00 and {to_hour}:00 in {path.name}, skipping.")
            return
        day_start = windows[0].to_pydatetime()
        day_end = (windows[-1] + timedelta(seconds=TEMPORAL_SEGMENT_SECONDS)).to_pydatetime()

        if replace:
            deleted, _ = Speed.objects.filter(
                timestamp__gte=day_start, timestamp__lt=day_end
            ).delete()
            print(f"Deleted {deleted} existing Speed records.")

        speed_count_before = Speed.objects.filter(
            timestamp__gte=day_start, timestamp__lt=day_end
        ).count()

        gps_gdf = gps_gdf.sort_values("timestamp")
        timestamps = gps_gdf["timestamp"]
        for window_start in windows:
            window_end = window_start + timedelta(seconds=TEMPORAL_SEGMENT_SECONDS)
            window_gdf = gps_gdf[(timestamps >= window_start) & (timestamps < window_end)]
            if window_gdf.empty:
                continue
            print(f"Window {window_start} - {window_end}")
            calculate_speed(
                window_start.to_pydatetime(),
                window_end.to_pydatetime(),
                gps_df=window_gdf,
                grid_obj=grid_obj,
            )

        speed_count_after = Speed.objects.filter(
            timestamp__gte=day_start, timestamp__lt=day_end
        ).count()
        print(
            f"{path.name}: created {speed_count_after - speed_count_before} Speed records "
            f"in {int(time.time() - file_start_time)} seconds."
        )
