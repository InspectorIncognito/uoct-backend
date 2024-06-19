import datetime
import time

from django.core.management import BaseCommand
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager
from velocity.segment import FiveHundredMeterSegmentCriteria
import pandas as pd
from gtfs_rt.utils import median_absolute_deviation
from rest_api.models import Speed, Segment
from django.utils import timezone


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
        print("Running calculate_speed")
        delta = datetime.timedelta(minutes=15)

        if not options["start_time"]:
            start_date = timezone.localtime()
            start_date = start_date.replace(second=0, microsecond=0)
        else:
            start_date = datetime.datetime.strftime(options["start_time"], "%Y-%m-%d %H:%M:%S")
            start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
            start_date.replace(second=0, microsecond=0)
        end_date = start_date - delta

        today_weekday = start_date.weekday()
        today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

        print(f"Start date: {start_date}")
        print(f"End date: {end_date}")

        # Filters GPS inside the grid bbox
        print("Creating Grid Object")
        grid_obj = generate_grid()

        print("Creating Vehicle Manager")
        vm = VehicleManager(grid_obj)

        print("Querying GPS pulses...")
        queryset = grid_obj.filter_gps(start_date, end_date)
        print(f"Got {len(queryset)} GPS pulses.")

        print("Adding GPS Pulses...")
        start_time = time.time()
        for (i, gps) in enumerate(queryset):
            percent = (i + 1) / len(queryset) * 100
            print(f'\rProgress: {percent:.2f}% ({i + 1}/{len(queryset)} pulses) [{int(time.time() - start_time)} s]',
                  end='')
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

        medians = df.groupby(by=['shape_id', 'spatial_segment_index', 'local_temporal_segment_index'])[
            'speed(km/h)'].transform(
            'median')
        df["threshold"] = (df["speed(km/h)"] - medians) / df["MAD"]

        threshold_min = -2
        threshold_max = 2
        df_filtered = df[(df['threshold'] > threshold_min) & (df['threshold'] < threshold_max)]

        # Sort df by spatial_segment_index
        df = df_filtered.groupby(['shape_id', 'spatial_segment_index']).agg({
            'speed(km/h)': 'mean'
        })
        for row, data in df.iterrows():
            shape_id = row[0]
            sequence = row[1]
            speed_data = {
                "segment": Segment.objects.get(shape__pk=shape_id, sequence=sequence),
                "speed": data['speed(km/h)'],
                "day_type": today_weekday
            }

            Speed.objects.create(**speed_data)
        print("Speed records up to date.")
