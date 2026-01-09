import datetime
import time

import pandas as pd
from rest_api.models import Segment, Speed
from velocity.grid import GridManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager

from gtfs_rt.utils import get_last_temporal_range


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

    # Removing outliers
    # TODO: Remove outliers using historical data (with medians)
    lower_threshold = 2
    upper_threshold = 85
    df = df[
        (df["speed(km/h)"] > lower_threshold) & (df["speed(km/h)"] <= upper_threshold)
    ]

    for row, data in df.iterrows():
        shape_id = data["shape_id"]
        sequence = data["spatial_segment_index"]
        temporal_segment = data["local_temporal_segment_index"]
        distance = data["distance_mts"]
        time_secs = data["time_secs"]
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
                timestamp=start_date,
                services=data["route_id"],
            )
            Speed.objects.create(**speed_data)
    print("Speed records up to date.")
    speed_end_time = time.time()
    print(
        f"Speed calculation completed in {int(speed_end_time - speed_start_time)} seconds."
    )


def calculate_speed_parallel(
    start_date: datetime.datetime = None,
    end_date: datetime.datetime = None,
    workers: int = 8,
):
    """
    Calculate speed using parallel HMM map matching.
    Returns timing metrics along with speed records.
    """
    print("[PARALLEL] Calling calculate_speed_parallel command...")
    speed_start_time = time.time()

    if start_date is None or end_date is None:
        start_date, end_date = get_last_temporal_range()
    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj: GridManager = generate_grid()
    vm = VehicleManager(grid_obj)

    gps_df: pd.DataFrame = grid_obj.filter_gps_from_dates(start_date, end_date)
    print(f"[PARALLEL] Retrieved {len(gps_df)} GPS Pulses.")

    # GPS processing
    gps_start = time.time()
    for gps in gps_df.itertuples():
        vm.add_data(gps)
    gps_time = time.time() - gps_start
    print(f"[PARALLEL] GPS processed in {gps_time:.2f} seconds.")

    # Parallel HMM map matching
    print(f"[PARALLEL] Running parallel HMM map matching with {workers} workers...")
    hmm_start = time.time()
    grid_obj.run_hmm_map_matching_parallel(vm, num_workers=workers)
    hmm_time = time.time() - hmm_start
    print(f"[PARALLEL] HMM map matching completed in {hmm_time:.2f} seconds.")

    # Speed calculation
    speed_calc_start = time.time()
    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
    speed_records = vm.calculate_speed(segment_criteria)
    speed_calc_time = time.time() - speed_calc_start

    total_time = time.time() - speed_start_time

    timing_metrics = {
        "method": "parallel",
        "workers": workers,
        "gps_pulses": len(gps_df),
        "gps_processing_time": round(gps_time, 2),
        "hmm_matching_time": round(hmm_time, 2),
        "speed_calculation_time": round(speed_calc_time, 2),
        "total_time": round(total_time, 2),
    }

    print(f"[PARALLEL] Total execution time: {total_time:.2f} seconds.")

    return speed_records, timing_metrics


def calculate_speed_serial(
    start_date: datetime.datetime = None, end_date: datetime.datetime = None
):
    """
    Calculate speed using serial (non-parallel) HMM map matching.
    Returns timing metrics along with speed records.
    """
    print("[SERIAL] Calling calculate_speed_serial command...")
    speed_start_time = time.time()

    if start_date is None or end_date is None:
        start_date, end_date = get_last_temporal_range()
    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj: GridManager = generate_grid()
    vm = VehicleManager(grid_obj)

    gps_df: pd.DataFrame = grid_obj.filter_gps_from_dates(start_date, end_date)
    print(f"[SERIAL] Retrieved {len(gps_df)} GPS Pulses.")

    # GPS processing
    gps_start = time.time()
    for gps in gps_df.itertuples():
        vm.add_data(gps)
    gps_time = time.time() - gps_start
    print(f"[SERIAL] GPS processed in {gps_time:.2f} seconds.")

    # Serial HMM map matching
    print("[SERIAL] Running serial HMM map matching...")
    hmm_start = time.time()
    grid_obj.run_hmm_map_matching(vm)
    hmm_time = time.time() - hmm_start
    print(f"[SERIAL] HMM map matching completed in {hmm_time:.2f} seconds.")

    # Speed calculation
    speed_calc_start = time.time()
    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
    speed_records = vm.calculate_speed(segment_criteria)
    speed_calc_time = time.time() - speed_calc_start

    total_time = time.time() - speed_start_time

    timing_metrics = {
        "method": "serial",
        "workers": 1,
        "gps_pulses": len(gps_df),
        "gps_processing_time": round(gps_time, 2),
        "hmm_matching_time": round(hmm_time, 2),
        "speed_calculation_time": round(speed_calc_time, 2),
        "total_time": round(total_time, 2),
    }

    print(f"[SERIAL] Total execution time: {total_time:.2f} seconds.")

    return speed_records, timing_metrics
