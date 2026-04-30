import datetime
import time
from collections import defaultdict

from gtfs_rt.utils import get_last_temporal_range
from rest_api.models import Segment, Speed
from velocity.grid import GridManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager

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

    gps_df = grid_obj.filter_gps_from_dates(start_date, end_date)
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
    grouped_records = defaultdict(
        lambda: {"distance_mts": 0.0, "time_secs": 0.0, "route_ids": list()}
    )

    for record in speed_records:
        key = (
            record["shape_id"],
            record["spatial_segment_index"],
            record["local_temporal_segment_index"],
        )
        grouped_records[key]["distance_mts"] += record["distance_mts"]
        grouped_records[key]["time_secs"] += record["time_secs"]
        grouped_records[key]["route_ids"].append(f"{record['route_id']}|{record['license_plate']}")

    grouped_rows = []
    for (
        shape_id,
        spatial_segment_index,
        temporal_segment,
    ), values in grouped_records.items():
        distance_mts = round(values["distance_mts"], 2)
        time_secs = round(values["time_secs"], 2)
        if time_secs <= 0:
            continue
        speed_kmh = round(3.6 * distance_mts / time_secs, 2)
        grouped_rows.append(
            {
                "shape_id": int(shape_id),
                "spatial_segment_index": spatial_segment_index,
                "temporal_segment": temporal_segment,
                "distance_mts": distance_mts,
                "time_secs": time_secs,
                "speed_kmh": speed_kmh,
                "route_id": list(values["route_ids"]),
            }
        )

    # Filter out speeds above MAX_SPEED_KMH threshold
    initial_count = len(grouped_rows)
    grouped_rows = [r for r in grouped_rows if r["speed_kmh"] <= MAX_SPEED_KMH]
    filtered_count = initial_count - len(grouped_rows)
    if filtered_count > 0:
        print(f"Filtered {filtered_count} records with speed > {MAX_SPEED_KMH} km/h")

    unique_shape_ids = {row["shape_id"] for row in grouped_rows}
    segments_dict = {
        (s.shape.id, s.sequence): s
        for s in Segment.objects.filter(shape__id__in=unique_shape_ids).select_related(
            "shape"
        )
    }
    shape_max_sequence = {}
    for shape_id, sequence in segments_dict.keys():
        current_max = shape_max_sequence.get(shape_id)
        if current_max is None or sequence > current_max:
            shape_max_sequence[shape_id] = sequence

    print(f"Loaded {len(segments_dict)} segments from database.")

    # Build Speed objects in memory for bulk insert
    speed_records = []
    missing_segments = []
    fallback_segments = []

    for data in grouped_rows:
        shape_id = data["shape_id"]
        sequence = data["spatial_segment_index"]

        # Try direct lookup first
        segment = segments_dict.get((shape_id, sequence))

        # Handle missing segment with edge case fallback
        if segment is None:
            max_sequence = shape_max_sequence.get(shape_id)
            if max_sequence is not None and sequence == max_sequence:
                # Edge case: assign to last segment
                segment = segments_dict.get((shape_id, max_sequence))
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
