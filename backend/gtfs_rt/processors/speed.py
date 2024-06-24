import time
import datetime
import pandas as pd
from django.utils import timezone
from rest_api.models import Segment, Speed, Shape
from velocity.vehicle import VehicleManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid
from gtfs_rt.utils import get_temporal_segment


def calculate_speed(start_date: datetime.datetime = None, end_date: datetime.datetime = None):
    print("Calling calculate_speed...")
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

    df['speed(km/h)'] = round(df['distance_mts'] / df['time_secs'] * 3.6, 2)

    # Removing outliers
    # TODO: Remove outliers using historical data (with medians)
    lower_threshold = 4
    upper_threshold = 80
    df = df[(df['speed(km/h)'] > lower_threshold) & (df['speed(km/h)'] <= upper_threshold)]

    # Sort df by spatial_segment_index
    df = df.groupby(['shape_id', 'spatial_segment_index']).agg({
        'speed(km/h)': 'mean'
    })
    for row, data in df.iterrows():
        shape_id = row[0]
        sequence = row[1]
        try:
            segment = Segment.objects.get(shape_id=shape_id, sequence=sequence)
        except Segment.DoesNotExist:
            print(f"Segment {sequence} from shape {shape_id} does not exists")
            continue
        else:
            temporal_segment = get_temporal_segment(end_date)
            speed_data = {
                "segment": segment,
                "speed": data['speed(km/h)'],
                "day_type": today_weekday,
                "temporal_segment": temporal_segment,
            }
            Speed.objects.create(**speed_data)
    print("Speed records up to date.")
