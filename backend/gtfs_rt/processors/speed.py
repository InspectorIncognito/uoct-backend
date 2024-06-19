import time
import datetime
import pandas as pd
from django.utils import timezone
from rest_api.models import Segment, Speed
from gtfs_rt.models import GPSPulse
from gtfs_rt.config import TIMEZONE
from gtfs_rt.utils import median_absolute_deviation
from velocity.vehicle import VehicleManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid


def calculate_speed_old(start_date: datetime.date = None, end_date: datetime = None):
    end_date_hardcode = datetime.datetime(year=2024, month=5, day=22, hour=16, minute=0, second=0)
    end_date = end_date_hardcode.astimezone(TIMEZONE)
    start_date = (end_date_hardcode - datetime.timedelta(minutes=5)).astimezone(TIMEZONE)
    queryset = GPSPulse.objects.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    print(f"Got {len(queryset)} GPS pulses.")

    print("Creating Grid Object")
    grid_obj = generate_grid()
    print("Creating Vehicle Manager")
    vm = VehicleManager(grid_obj)

    for gps in queryset:
        vm.add_data(gps)

    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
    speed_records = vm.calculate_speed(segment_criteria)
    return speed_records


def calculate_speed(start_date: datetime.datetime = None, end_date: datetime.datetime = None):
    print("Running calculate_speed")
    delta = datetime.timedelta(minutes=15)

    if end_date is None:
        end_date = timezone.localtime()
        end_date = end_date.replace(second=0, microsecond=0)
    else:
        if end_date.tzinfo is None:
            end_date = timezone.make_aware(end_date, timezone.get_current_timezone())
        end_date.replace(second=0, microsecond=0)
    if start_date is None:
        start_date = end_date - delta

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
