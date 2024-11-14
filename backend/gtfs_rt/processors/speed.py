import time
import datetime
import pandas as pd
from django.utils import timezone
from rest_api.models import Segment, Speed
from rest_api.util.temporal_segment import get_last_temporal_segment_dates
from velocity.grid import GridManager
from velocity.vehicle import VehicleManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid


def calculate_speed(start_date: datetime.datetime = None, end_date: datetime.datetime = None):
    print("Calling calculate_speed command...")
    if start_date is None or end_date is None:
        start_date, end_date = get_last_temporal_segment_dates()
    print("Start date:", start_date)
    print("End date:", end_date)
    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj: GridManager = generate_grid()

    vm = VehicleManager(grid_obj)

    gps_df: pd.DataFrame = grid_obj.filter_gps_from_dates(start_date, end_date)
    print(f"Retrieved {len(gps_df)} GPS Pulses.")

    start_time = time.time()
    for _, gps in gps_df.iterrows():
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

    df['speed(km/h)'] = round(3.6 * df['distance_mts'] / df['time_secs'], 2)

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
            speed_data = dict(
                segment=segment,
                temporal_segment=temporal_segment,
                day_type=today_weekday,
                distance=distance,
                time_secs=time_secs,
                timestamp=start_date
            )
            Speed.objects.create(**speed_data)
    print("Speed records up to date.")
