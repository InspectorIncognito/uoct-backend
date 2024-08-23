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
    if start_date is None or end_date is None:
        delta = datetime.timedelta(minutes=15)
        end_date = timezone.localtime().replace(second=0, microsecond=0)
        start_date = end_date - delta

    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj = generate_grid()

    vm = VehicleManager(grid_obj)

    queryset = grid_obj.filter_gps(start_date, end_date)
    print(f"Retrieved {len(queryset)} GPS Pulses.")

    start_time = time.time()
    for (i, gps) in enumerate(queryset):
        vm.add_data(gps)
    end_time = time.time()
    print(f"GPS processed in {int(end_time - start_time)} seconds.")

    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
    speed_records = vm.calculate_speed(segment_criteria)
    df = pd.DataFrame.from_records(speed_records)[
        ['shape_id', 'spatial_segment_index', 'local_temporal_segment_index', 'distance_mts', 'time_secs']]

    df = df.groupby(['shape_id', 'spatial_segment_index', 'local_temporal_segment_index']).agg({
        'distance_mts': 'sum',
        'time_secs': 'sum'
    }).reset_index()
    df = df.round({'distance_mts': 2, 'time_secs': 2})

    df['speed(km/h)'] = round(df['distance_mts'] / df['time_secs'] * 3.6, 2)

    # Removing outliers
    # TODO: Remove outliers using historical data (with medians)
    lower_threshold = 4
    upper_threshold = 80
    df = df[(df['speed(km/h)'] > lower_threshold) & (df['speed(km/h)'] <= upper_threshold)]

    for row, data in df.iterrows():
        shape_id = data['shape_id']
        sequence = data['spatial_segment_index']
        temporal_segment = data['local_temporal_segment_index']
        distance = data['distance_mts']
        time_secs = data['time_secs']
        try:
            segment = Segment.objects.get(shape_id=shape_id, sequence=sequence)
        except Segment.DoesNotExist:
            print(f"Segment {sequence} from shape {shape_id} does not exists")
            continue
        else:
            speed_data = {
                "segment": segment,
                "distance": distance,
                "time_secs": time_secs,
                "day_type": today_weekday,
                "temporal_segment": temporal_segment,
            }
            Speed.objects.create(**speed_data)
    print("Speed records up to date.")
