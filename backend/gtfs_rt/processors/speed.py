import datetime
import time

import pandas as pd
from rest_api.models import Segment, Speed
from velocity.grid import GridManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager

from gtfs_rt.utils import get_last_temporal_range

MAX_SPEED_KMH = 85.0  # Maximum speed threshold in km/h


def calculate_speed(
    start_date: datetime.datetime = None, end_date: datetime.datetime = None
):
    print("Calling calculate_speed command...")
    speed_start_time = time.time()
    if start_date is None or end_date is None:
        start_date, end_date = get_last_temporal_range()
    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj: GridManager = generate_grid()

    vm = VehicleManager(grid_obj)

    gps_df: pd.DataFrame = grid_obj.filter_gps_from_dates(start_date, end_date)
    print(f"Retrieved {len(gps_df)} GPS Pulses.")

    start_time = time.time()
    for gps in gps_df.itertuples():
        vm.add_data(gps)
    end_time = time.time()
    print(f"GPS processed in {int(end_time - start_time)} seconds.")

    print("Running HMM map matching for speed calculation...")
    start_time = time.time()
    # Use parallel HMM map matching for better performance on multi-core systems.
    # Falls back to serial processing automatically if workers=1 or few expeditions.
    grid_obj.run_hmm_map_matching_parallel(vm)
    end_time = time.time()
    print(f"HMM map matching completed in {int(end_time - start_time)} seconds.")

    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
    speed_records = vm.calculate_speed(segment_criteria)
    df = pd.DataFrame.from_records(speed_records)[
        [
            "shape_id",
            "route_id",
            "spatial_segment_index",
            "local_temporal_segment_index",
            "distance_mts",
            "time_secs",
        ]
    ]
    df = (
        df.groupby(
            ["shape_id", "spatial_segment_index", "local_temporal_segment_index"]
        )
        .agg(
            {
                "distance_mts": "sum",
                "time_secs": "sum",
                "route_id": lambda x: list(x.unique()),
            }
        )
        .reset_index()
    )
    df = df.round({"distance_mts": 2, "time_secs": 2})

    df["speed(km/h)"] = round(3.6 * df["distance_mts"] / df["time_secs"], 2)

    # Rename column to match HistoricSpeed model field name
    # The speed calculation uses local timezone temporal segments
    df = df.rename(columns={"local_temporal_segment_index": "temporal_segment"})

    # Filter out speeds above MAX_SPEED_KMH threshold
    initial_count = len(df)
    df = df[df["speed(km/h)"] <= MAX_SPEED_KMH]
    filtered_count = initial_count - len(df)
    if filtered_count > 0:
        print(f"Filtered {filtered_count} records with speed > {MAX_SPEED_KMH} km/h")

    df_to_save = df

    # Convert shape_id to integer (it comes as string from shape_pk in segments_gdf)
    df_to_save["shape_id"] = df_to_save["shape_id"].astype(int)

    unique_shape_ids = df_to_save["shape_id"].unique()
    segments_dict = {
        (s.shape.id, s.sequence): s
        for s in Segment.objects.filter(shape__id__in=unique_shape_ids).select_related(
            "shape"
        )
    }
    print(f"Loaded {len(segments_dict)} segments from database.")

    # Build Speed objects in memory for bulk insert
    speed_records = []
    missing_segments = []
    fallback_segments = []

    for row, data in df_to_save.iterrows():
        shape_id = data["shape_id"]
        sequence = data["spatial_segment_index"]

        # Try direct lookup first
        segment = segments_dict.get((shape_id, sequence))

        # Handle missing segment with edge case fallback
        if segment is None:
            # Get max sequence for this shape from prefetched data
            shape_sequences = [
                seq for (sid, seq) in segments_dict.keys() if sid == shape_id
            ]
            if shape_sequences and sequence == max(shape_sequences):
                # Edge case: assign to last segment
                segment = segments_dict.get((shape_id, max(shape_sequences)))
                fallback_segments.append((shape_id, sequence))
            else:
                missing_segments.append((shape_id, sequence))
                continue

        # Create Speed object (not saved yet)
        speed_records.append(
            Speed(
                segment=segment,
                temporal_segment=data["temporal_segment"],
                day_type=today_weekday,
                distance=data["distance_mts"],
                time_secs=data["time_secs"],
                timestamp=start_date,
                services=data["route_id"],
            )
        )

    # Report issues
    if missing_segments:
        print(f"Skipped {len(missing_segments)} records with missing segments")
    if fallback_segments:
        print(f"Used fallback for {len(fallback_segments)} edge case segments")

    Speed.objects.bulk_create(speed_records, batch_size=1000)
    print("Speed records up to date.")
    speed_end_time = time.time()
    print(
        f"Speed calculation completed in {int(speed_end_time - speed_start_time)} seconds."
    )
