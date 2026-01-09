import datetime
import time

import numpy as np
import pandas as pd
from rest_api.models import Segment, Speed
from velocity.grid import GridManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager

from gtfs_rt.utils import get_last_temporal_range


def apply_mad_filter(
    df: pd.DataFrame,
    group_cols,
    speed_col="speed(km/h)",
    z_incident=3.0,
    z_outlier=4.5,
    min_group_size=5,
):
    """
    Apply MAD (Median Absolute Deviation) filtering by group to:
    - Remove hard outliers (z > z_outlier) that are likely sensor errors
    - Flag possible incidents (z > z_incident) for downstream alert processing

    MAD is more robust than standard deviation for speed data with outliers.
    Possible incidents are kept in the returned data since they may represent
    real traffic conditions needed for alert generation.

    Args:
        df: DataFrame with speed data
        group_cols: Columns to group by (e.g., shape_id, segment indices)
        speed_col: Name of speed column
        z_incident: Z-score threshold for flagging incidents (default 3.0)
        z_outlier: Z-score threshold for removing outliers (default 4.5)
        min_group_size: Minimum group size for filtering (default 5)

    Returns:
        tuple: (df_filtered, df_outliers)
            - df_filtered: Data with outliers removed (includes normal + possible_incident)
            - df_outliers: Hard outliers removed from data (z > z_outlier)
    """
    df = df.copy()

    # Initialize diagnostic columns
    df["median_speed"] = np.nan
    df["mad"] = np.nan
    df["z_mad"] = np.nan
    df["status"] = "normal"

    def _process_group(group):
        """Process a single group for MAD-based outlier detection."""
        # Filter out NaN/infinite speeds first
        valid_mask = group[speed_col].notna() & np.isfinite(group[speed_col])
        n_valid = valid_mask.sum()

        # Mark groups with insufficient data
        if n_valid < min_group_size:
            group.loc[valid_mask, "status"] = "insufficient_data"
            return group

        valid_speeds = group.loc[valid_mask, speed_col]

        # Calculate MAD statistics
        median = valid_speeds.median()
        mad = np.median(np.abs(valid_speeds - median))

        # Avoid division by zero - if MAD=0, all values are identical
        if mad == 0 or np.isnan(mad):
            group.loc[valid_mask, "median_speed"] = median
            group.loc[valid_mask, "mad"] = mad
            group.loc[valid_mask, "z_mad"] = 0.0
            return group

        # Calculate modified Z-scores (1.4826 converts MAD to ~std deviation)
        z_scores = np.abs(valid_speeds - median) / (1.4826 * mad)

        # Assign statistics to valid rows
        group.loc[valid_mask, "median_speed"] = median
        group.loc[valid_mask, "mad"] = mad
        group.loc[valid_mask, "z_mad"] = z_scores.values

        # Classify observations
        outlier_mask = valid_mask & (group["z_mad"] > z_outlier)
        incident_mask = (
            valid_mask & (group["z_mad"] > z_incident) & (group["z_mad"] <= z_outlier)
        )

        group.loc[outlier_mask, "status"] = "outlier"
        group.loc[incident_mask, "status"] = "possible_incident"

        return group

    # Apply MAD processing to each group
    df = df.groupby(group_cols, group_keys=False).apply(_process_group)

    # Keep everything except hard outliers (normal + possible_incident)
    df_filtered = df[df["status"] != "outlier"].copy()
    df_outliers = df[df["status"] == "outlier"].copy()

    # Count by status for reporting
    n_normal = (df["status"] == "normal").sum()
    n_incidents = (df["status"] == "possible_incident").sum()
    n_outliers = len(df_outliers)
    n_insufficient = (df["status"] == "insufficient_data").sum()

    # Log summary statistics
    print("MAD Filter Results:")
    print(f"  - Normal observations: {n_normal} ({100 * n_normal / len(df):.1f}%)")
    print(
        f"  - Possible incidents (flagged): {n_incidents} ({100 * n_incidents / len(df):.1f}%)"
    )
    print(f"  - Outliers removed: {n_outliers} ({100 * n_outliers / len(df):.1f}%)")
    print(f"  - Insufficient data: {n_insufficient}")
    print(f"  - Retained for processing: {len(df_filtered)} records")

    return df_filtered, df_outliers


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

    # Apply MAD-based outlier filtering
    # Removes only hard outliers (sensor errors), keeps incidents for alert generation
    df, df_outliers = apply_mad_filter(
        df,
        group_cols=[
            "shape_id",
            "spatial_segment_index",
            "local_temporal_segment_index",
        ],
        speed_col="speed(km/h)",
        z_incident=3.0,  # Flag speeds >3 MAD from median as possible incidents
        z_outlier=4.5,  # Remove speeds >4.5 MAD from median as hard outliers
        min_group_size=5,  # Need at least 5 observations for reliable statistics
    )

    # Note: df now contains normal observations + flagged incidents (status column preserved)
    # Incidents are kept because they may represent real slow traffic needed for alerts

    # Drop MAD diagnostic columns before DB insertion (they're not part of Speed model)
    # Keep them in df if you want to export for analysis later
    df_to_save = df.drop(
        columns=["median_speed", "mad", "z_mad", "status"], errors="ignore"
    )

    for row, data in df_to_save.iterrows():
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
