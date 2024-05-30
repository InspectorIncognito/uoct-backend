import os
import logging
import datetime
import time

from django.core.management import BaseCommand, CommandError
from gtfs_rt.models import GPSPulse
from gtfs_rt.config import TIMEZONE
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager
from velocity.segment import FiveHundredMeterSegmentCriteria
import pandas as pd
from gtfs_rt.utils import median_absolute_deviation


class Command(BaseCommand):
    help = 'Calculate speed for all segments of each shape in a range of time.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start_time',
            help="Start time of the GPS pulses. Format: yyyy-mm-dd HH:MM:SS",
            type=str
        )
        parser.add_argument(
            '--end_time',
            help="End time of the GPS pulses. Format: yyyy-mm-dd HH:MM:SS",
            type=str
        )

    def handle(self, *args, **options):
        # TODO: filter by start_date and end_date arguments
        # By default, calculates the commercial speed mean from the last 15 minutes of every segment.
        end_date_hardcode = datetime.datetime(year=2024, month=5, day=22, hour=17, minute=0, second=0)
        end_date = end_date_hardcode.astimezone(TIMEZONE)
        start_date = (end_date_hardcode - datetime.timedelta(hours=2)).astimezone(TIMEZONE)
        queryset = GPSPulse.objects.filter(timestamp__gte=start_date, timestamp__lte=end_date)
        print(f"Start date: {start_date}")
        print(f"End date: {end_date}")
        print(f"Got {len(queryset)} GPS pulses.")

        print("Creating Grid Object")
        grid_obj = generate_grid()
        print("Creating Vehicle Manager")
        vm = VehicleManager(grid_obj)
        gps_outside = 0
        print("Adding GPS Pulses...")
        start_time = time.time()
        for (i, gps) in enumerate(queryset):
            percent = (i + 1) / len(queryset) * 100
            print(f'\rProgress: {percent:.2f}% ({i + 1}/{len(queryset)} pulses) [{int(time.time() - start_time)} s.]', end='')
            if not grid_obj.contains_gps(gps):
                gps_outside += 1
                continue
            vm.add_data(gps)
        print()

        segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
        speed_records = vm.calculate_speed(segment_criteria)
        df = pd.DataFrame.from_records(speed_records)[
            ['shape_id', 'spatial_segment_index', 'local_temporal_segment_index', 'distance_mts', 'time_secs']]

        # Removing Outliers
        df['speed(km/h)'] = round(df['distance_mts'] / df['time_secs'] * 3.6, 2)
        mad_df = df.groupby(by=['shape_id', 'spatial_segment_index', 'local_temporal_segment_index'])[
            'speed(km/h)'].apply(
            lambda x: median_absolute_deviation(x))
        df = df.merge(mad_df.rename("MAD"),
                      left_on=["shape_id", "spatial_segment_index", "local_temporal_segment_index"],
                      right_index=True).sort_values(
            by=['shape_id', 'spatial_segment_index', 'local_temporal_segment_index'])

        medianas = df.groupby(by=['shape_id', 'spatial_segment_index', 'local_temporal_segment_index'])[
            'speed(km/h)'].transform(
            'median')
        df["threshold"] = (df["speed(km/h)"] - medianas) / df["MAD"]

        threshold_min = -2
        threshold_max = 2
        df_filtered = df[(df['threshold'] > threshold_min) & (df['threshold'] < threshold_max)]

        # Sort df by spatial_segment_index
        df = df_filtered.groupby(['shape_id', 'spatial_segment_index']).agg({
            'speed(km/h)': 'mean'
        })
        print(df.to_string())
