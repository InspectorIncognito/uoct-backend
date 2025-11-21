"""Speed calculation using HMM-based map matching.

This module calculates vehicle speeds by:
1. Building GPS trajectories from raw GPS pulses (no pre-filtering by route/shape)
2. Applying HMM batch matching to map trajectories to road segments
3. Calculating accumulated distances along matched shapes
4. Generating speed records from consecutive GPS points on the same shape
5. Aggregating and storing speed data in the database

Key implementation details:
- HMM matches GPS to combined axis GeoDataFrames (both directions)
- Each matched segment contains shape_id field with full direction info (e.g., "Eje Alameda_0")
- Speed records only generated for consecutive points on the SAME shape (same direction)
- Proper indexing: matched_segments/projected_points indexed by valid_indices, not GPS index
"""

import datetime
import time

import pandas as pd
from gtfs_rt.models import GPSPulse
from gtfs_rt.utils import get_last_temporal_range
from rest_api.models import Segment, Speed
from rest_api.util.hmm.hmm import batch_match_trajectories_to_axes
from rest_api.util.shape import ShapeManager
from shapely.geometry import Point as shp_Point
from velocity.grid import GridManager
from velocity.mapmatching import build_axes_dict, compute_segment_offsets
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid


def calculate_speed(
    start_date: datetime.datetime = None,
    end_date: datetime.datetime = None,
    hmm_max_distance: float = 100.0,
    hmm_sigma: float = 25.0,
    hmm_beta: float = 30.0,
):
    """Calculate speed using HMM map matching."""
    print("Calling calculate_speed with HMM...")
    if start_date is None or end_date is None:
        start_date, end_date = get_last_temporal_range()

    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj: GridManager = generate_grid()
    shape_manager = ShapeManager()

    # Initialize HMM components
    print("Initializing HMM map matching...")
    axes_dict = build_axes_dict(shape_manager)
    print(f"Built axes dictionary with {len(axes_dict)} axes")

    # Compute segment offsets for each axis
    # TODO: review how is calculated and used, because one axis_dict have two directions in it
    # e.g., "Eje Alameda_0" and "Eje Alameda_1" are in the same GeoDataFrame
    # Mabe is better tu use the FiveHundredCriteria class to get the segment offsets
    segment_offsets_by_axis = {}
    for axis_id, segments_gdf in axes_dict.items():
        segment_offsets_by_axis[axis_id] = compute_segment_offsets(segments_gdf)

    print("HMM initialization complete")

    print("Input start:", start_date, "end:", end_date)

    # Build trajectories from GPS data
    print("Building trajectories for HMM...")

    # Get ALL GPS without spatial or route filtering
    queryset = GPSPulse.objects.filter(
        timestamp__gte=start_date, timestamp__lte=end_date
    ).order_by("license_plate", "timestamp")

    # Convert to GeoDataFrame
    gps_df = grid_obj.get_gps_gdf(queryset)
    print(f"Retrieved {len(gps_df)} GPS Pulses (unfiltered).")

    # Clean duplicates
    initial = len(gps_df)
    gps_df = gps_df.drop_duplicates(
        subset=["license_plate", "timestamp", "route_id", "direction"]
    )
    if len(gps_df) < initial:
        print(f"  - Removed {initial - len(gps_df)} duplicates")

    # Ensure sorted by license_plate and timestamp
    gps_df = gps_df.sort_values(
        ["license_plate", "timestamp"], ascending=[True, True]
    ).reset_index(drop=True)

    # Validate timestamps
    if not pd.api.types.is_datetime64_any_dtype(gps_df["timestamp"]):
        print("  - Converting timestamps to datetime...")
        gps_df["timestamp"] = pd.to_datetime(gps_df["timestamp"])

    def process_trajectory_group(group):
        """Process trajectory for a vehicle: clean, validate, and structure.

        Steps:
        1. Sort GPS points by timestamp
        2. Remove consecutive duplicate geometries (same position)
        3. Filter out trajectories with < 2 points (too short for speed calculation)
        4. Extract most frequent route_id and direction (mode)

        Returns:
            pd.Series with trajectory data or None if invalid
        """
        # Sort by timestamp
        group = group.sort_values("timestamp", ascending=True).reset_index(drop=True)

        # Remove consecutive points with same geometry
        group["prev_geom"] = group["geometry"].shift()
        group = group[group["geometry"] != group["prev_geom"]].drop(columns="prev_geom")

        # Filter trajectories too short (< 2 points)
        if len(group) < 2:
            return None

        # Extract most frequent route_id and direction
        route_id = (
            group["route_id"].mode()[0] if not group["route_id"].isna().all() else None
        )
        direction = (
            group["direction"].mode()[0]
            if not group["direction"].isna().all()
            else None
        )

        return pd.Series(
            {
                "points": group.geometry.tolist(),
                "route_id": route_id,
                "direction": direction,
                "timestamps": group["timestamp"].tolist(),
                "bearings": [None] * len(group),
                "n_points": len(group),
            }
        )

    print("Constructing trajectories by vehicle...")
    trajectories_df = (
        gps_df.groupby("license_plate", as_index=False)
        .apply(process_trajectory_group, include_groups=False)
        .dropna(subset=["points"])
        .reset_index(drop=True)
    )
    print(f"Built {len(trajectories_df)} trajectories from {len(gps_df)} GPS points")
    print(
        f"  - Average points per trajectory: {trajectories_df['n_points'].mean():.1f}"
    )

    # Apply HMM batch matching

    print("Running HMM batch matching...")
    hmm_batch_start = time.time()
    batch_results = batch_match_trajectories_to_axes(
        trajectories_df,
        axes_dict,
        max_distance=hmm_max_distance,
        sigma=hmm_sigma,
        beta=hmm_beta,
        min_candidates=2,
        remove_matched_points=False,
        id_column="license_plate",
    )
    hmm_batch_end = time.time()
    print(
        f"HMM batch matching completed in {int(hmm_batch_end - hmm_batch_start)} seconds"
    )
    print(f"  - Matched {len(batch_results)} trajectories")

    def sumary_hmm_stats(batch_results):
        total_matched_points = 0
        total_valid_points = 0
        for traj_id, traj_data in batch_results.items():
            for axis_id, (
                matched_segments,
                valid_indices,
                projected_points,
            ) in traj_data.items():
                total_matched_points += len(matched_segments)
                total_valid_points += len(valid_indices)
        print(f"Total matched points across all trajectories: {total_matched_points}")
        print(f"Total valid points across all trajectories: {total_valid_points}")
        # Number of segments matched per shape
        shapes_stats = {}
        unique_segments_per_shape = {}
        for traj_id, traj_data in batch_results.items():
            for axis_id, (
                matched_segments,
                valid_indices,
                projected_points,
            ) in traj_data.items():
                for seg_idx in matched_segments:
                    if seg_idx is not None:
                        shape_id = axes_dict[axis_id].loc[seg_idx]["shape_id"]
                        shapes_stats[shape_id] = shapes_stats.get(shape_id, 0) + 1
                        if shape_id not in unique_segments_per_shape:
                            unique_segments_per_shape[shape_id] = set()
                        unique_segments_per_shape[shape_id].add(seg_idx)

        print(f"Total unique shapes matched: {len(shapes_stats)}")
        print("Matched segments per shape:")
        for shape_id, count in shapes_stats.items():
            print(f"  - Shape {shape_id}: {count} segments matched")
            print(
                f"  - Shape {shape_id}: {len(unique_segments_per_shape[shape_id])} unique segments matched"
            )

    print(
        "\n=========================================================================="
    )
    sumary_hmm_stats(batch_results)
    print(
        "==========================================================================\n"
    )

    # Process HMM results to generate speed records
    print("Processing HMM results to calculate speeds...")
    speed_records = []
    skipped_trajectories = 0
    total_gps_matched = 0
    shape_not_found_count = 0

    # Initialize segment criteria once
    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)

    # Build shape name to shape PK mapping for fast lookup
    shape_name_to_pk = {shape.name: str(shape.pk) for shape in shape_manager.shapes}
    print(f"Built shape mapping with {len(shape_name_to_pk)} shapes")

    for traj_idx, (license_plate, traj_data) in enumerate(
        zip(trajectories_df["license_plate"], trajectories_df.to_dict("records"))
    ):
        # Get HMM results for this trajectory
        traj_results = batch_results.get(str(license_plate))
        if not traj_results:
            skipped_trajectories += 1
            continue

        # Select best axis (highest coverage)
        best_axis_id = None
        best_coverage = 0.0
        best_result = None

        for axis_id, (
            matched_segments,
            valid_indices,
            projected_points,
        ) in traj_results.items():
            coverage = (
                len(valid_indices) / len(traj_data["points"])
                if traj_data["points"]
                else 0.0
            )
            if coverage > best_coverage:
                best_coverage = coverage
                best_axis_id = axis_id
                best_result = (matched_segments, valid_indices, projected_points)

        if best_result is None or best_coverage < 0.3:
            skipped_trajectories += 1
            continue

        matched_segments, valid_indices, projected_points = best_result
        segment_offsets = segment_offsets_by_axis.get(best_axis_id, {})
        segments_gdf = axes_dict[best_axis_id]

        # Calculate accumulated distances for each GPS point
        distances_on_route = []
        timestamps = traj_data["timestamps"]
        points = traj_data["points"]

        # Track which shape_id each matched point belongs to (from segment's shape_id field)
        shape_ids_per_point = []
        # Track the sequence number of each matched segment (for DB lookup)
        segment_sequences_per_point = []

        # Create lookup for matched results (valid_indices -> matched_segments/projected_points)
        valid_idx_lookup = {valid_idx: i for i, valid_idx in enumerate(valid_indices)}

        for idx in range(len(points)):
            if idx not in valid_idx_lookup:
                distances_on_route.append(None)
                shape_ids_per_point.append(None)
                segment_sequences_per_point.append(None)
                continue

            # Get matched segment and projected point using lookup
            result_idx = valid_idx_lookup[idx]
            seg_idx = matched_segments[result_idx]
            proj_point = projected_points[result_idx]

            if seg_idx is None or proj_point is None:
                distances_on_route.append(None)
                shape_ids_per_point.append(None)
                segment_sequences_per_point.append(None)
                continue

            # Get segment offset and geometry
            segment_start_distance = segment_offsets.get(seg_idx, 0.0)

            if seg_idx not in segments_gdf.index:
                distances_on_route.append(None)
                shape_ids_per_point.append(None)
                segment_sequences_per_point.append(None)
                continue

            segment_row = segments_gdf.loc[seg_idx]
            segment_geom = segment_row["geometry"]

            # Get the shape_id from the matched segment (this has the direction!)
            segment_shape_name = segment_row.get("shape_id")
            # Get the sequence number from the matched segment (for DB lookup)
            segment_sequence = segment_row.get("sequence")

            # Calculate distance along segment
            try:
                distance_in_segment = segment_geom.project(proj_point)

                # For geographic CRS, convert to meters
                if segments_gdf.crs and segments_gdf.crs.is_geographic:
                    from processors.geometry.point import Point

                    interpolated_point = segment_geom.interpolate(distance_in_segment)
                    start_point = segment_geom.coords[0]

                    p1 = Point(latitude=start_point[1], longitude=start_point[0])
                    p2 = Point(
                        latitude=interpolated_point.y,
                        longitude=interpolated_point.x,
                    )
                    distance_in_segment = p1.haversine_distance(p2)

                total_distance = segment_start_distance + distance_in_segment
                distances_on_route.append(total_distance)
                shape_ids_per_point.append(segment_shape_name)
                segment_sequences_per_point.append(segment_sequence)
                total_gps_matched += 1

            except Exception as e:
                distances_on_route.append(None)
                shape_ids_per_point.append(None)
                segment_sequences_per_point.append(None)
                continue

        # Generate speed records from consecutive valid GPS pairs
        route_id = traj_data.get("route_id")

        # Validate consistency: all lists must have the same length
        # This ensures no desynchronization occurred during distance calculation
        expected_length = len(points)
        if not (
            len(distances_on_route)
            == len(shape_ids_per_point)
            == len(segment_sequences_per_point)
            == len(timestamps)
            == expected_length
        ):
            print(f"WARNING: Inconsistent list lengths for trajectory {license_plate}")
            print(
                f"  Expected: {expected_length}, got distances: {len(distances_on_route)}, "
                f"shapes: {len(shape_ids_per_point)}, sequences: {len(segment_sequences_per_point)}"
            )
            skipped_trajectories += 1
            continue

        for i in range(1, len(distances_on_route)):
            if distances_on_route[i] is None or distances_on_route[i - 1] is None:
                continue

            if shape_ids_per_point[i] is None or shape_ids_per_point[i - 1] is None:
                continue

            if (
                segment_sequences_per_point[i] is None
                or segment_sequences_per_point[i - 1] is None
            ):
                continue

            # Both points must belong to the same shape (same direction)
            if shape_ids_per_point[i] != shape_ids_per_point[i - 1]:
                continue

            # Get shape_pk from the shape name
            shape_name = shape_ids_per_point[i]
            shape_id = shape_name_to_pk.get(shape_name)

            if shape_id is None:
                if shape_not_found_count == 0:
                    print(f"WARNING: Shape '{shape_name}' not found in database")
                shape_not_found_count += 1
                continue

            # Calculate delta
            delta_distance = distances_on_route[i] - distances_on_route[i - 1]
            delta_time = (timestamps[i] - timestamps[i - 1]).total_seconds()

            # Skip invalid deltas
            if delta_time <= 0 or delta_distance < 0:
                continue

            # Skip if time gap too large
            if delta_time >= 600:  # 10 minutes
                continue

            # Use segment_criteria to get spatial and temporal segments
            try:
                # Get spatial segment for the distance (used for naming)
                spatial_segment = segment_criteria.get_spatial_segment(
                    shape_id, distances_on_route[i]
                )
                temporal_segment_obj = segment_criteria.get_temporal_segment(
                    timestamps[i]
                )

                # IMPORTANT: Use the actual segment sequence from the matched HMM segment
                # NOT the spatial_segment.index (which is for 500m segmentation)
                # The segment_sequence comes from the database Segment.sequence field
                actual_segment_sequence = segment_sequences_per_point[i]

                # Create speed record
                speed_record = {
                    "route_id": route_id,
                    "shape_id": shape_id,
                    "pattern_id": "pattern",
                    "spatial_segment_index": actual_segment_sequence,  # Use HMM segment sequence
                    "spatial_segment_name": spatial_segment.get_name(),  # Keep 500m name for reference
                    "utc_date": timestamps[i].date().strftime("%Y-%m-%d"),
                    "utc_day_type": (
                        "L"
                        if timestamps[i].weekday() < 5
                        else "S" if timestamps[i].weekday() == 5 else "D"
                    ),
                    "utc_temporal_segment_index": temporal_segment_obj.index,
                    "utc_temporal_segment_name": temporal_segment_obj.get_name(),
                    "local_date": temporal_segment_obj.start_time.date().strftime(
                        "%Y-%m-%d"
                    ),
                    "local_day_type": segment_criteria.get_day_type(timestamps[i]),
                    "local_temporal_segment_index": temporal_segment_obj.index,
                    "local_temporal_segment_name": temporal_segment_obj.get_name(),
                    "distance_mts": delta_distance,
                    "time_secs": delta_time,
                }
                speed_records.append(speed_record)

            except (ValueError, KeyError) as e:
                continue

    print(f"Generated {len(speed_records)} speed records from HMM matching")
    print(f"  - Trajectories processed: {len(batch_results)}")
    print(f"  - Trajectories skipped: {skipped_trajectories}")
    print(f"  - GPS points matched: {total_gps_matched}")
    if shape_not_found_count > 0:
        print(
            f"  - Shape name not found in database: {shape_not_found_count} occurrences"
        )

    # Check if we have any speed records to process
    if not speed_records:
        print("No speed records generated. Exiting.")
        return

    # Aggregate speed records by shape, spatial segment, and temporal segment
    # This combines multiple GPS observations for the same segment/time window
    df = pd.DataFrame.from_records(speed_records)[
        [
            "shape_id",
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
        .agg({"distance_mts": "sum", "time_secs": "sum"})
        .reset_index()
    )
    df = df.round({"distance_mts": 2, "time_secs": 2})

    # Calculate speed in km/h: (distance_m / time_s) * 3.6
    df["speed(km/h)"] = round(3.6 * df["distance_mts"] / df["time_secs"], 2)

    # Remove outliers: speeds below 4 km/h or above 80 km/h
    # These thresholds filter stopped vehicles and unrealistic speeds
    lower_threshold = 4
    upper_threshold = 100
    discarded_count = df[
        (df["speed(km/h)"] <= lower_threshold) | (df["speed(km/h)"] > upper_threshold)
    ].shape[0]
    print("=" * 80)
    print(f"Discarded {discarded_count} outlier speed records")
    df = df[
        (df["speed(km/h)"] > lower_threshold) & (df["speed(km/h)"] <= upper_threshold)
    ]
    print("=" * 80)
    # Save to database
    for row, data in df.iterrows():
        shape_id = data["shape_id"]
        sequence = data["spatial_segment_index"]
        temporal_segment = data["local_temporal_segment_index"]
        distance = data["distance_mts"]
        time_secs = data["time_secs"]
        try:
            segment = Segment.objects.get(shape_id=shape_id, sequence=sequence)
        except Segment.DoesNotExist:
            print(f"Segment {sequence} from shape {shape_id} does not exist")
            continue
        else:
            speed_data = dict(
                segment=segment,
                temporal_segment=temporal_segment,
                day_type=today_weekday,
                distance=distance,
                time_secs=time_secs,
                timestamp=start_date,
            )
            Speed.objects.create(**speed_data)

    print("Speed records up to date.")
