import datetime
import time

import pandas as pd
from gtfs_rt.utils import get_last_temporal_range
from rest_api.models import Segment, Speed
from rest_api.util.shape import ShapeManager
from velocity.grid import GridManager

# Import HMM map matching module
from velocity.mapmatching import (
    HmmStats,
    apply_hmm_to_expedition,
    build_axes_dict,
    compute_segment_offsets,
    precompute_hmm_caches,
    run_hmm_for_expedition,
)
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager


def calculate_speed(
    start_date: datetime.datetime = None,
    end_date: datetime.datetime = None,
    use_hmm: bool = False,
    hmm_shadow_mode: bool = True,
    hmm_max_distance: float = 100.0,
    hmm_sigma: float = 25.0,
    hmm_beta: float = 30.0,
):
    print("Calling calculate_speed command...")
    if start_date is None or end_date is None:
        start_date, end_date = get_last_temporal_range()
    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj: GridManager = generate_grid()

    # Initialize HMM components if enabled
    hmm_caches = None
    axes_dict = None
    segment_offsets_by_axis = None
    hmm_stats = HmmStats()

    if use_hmm or hmm_shadow_mode:
        print(
            f"{'[SHADOW MODE] ' if hmm_shadow_mode else ''}Initializing HMM map matching..."
        )
        shape_manager = ShapeManager()

        # Build axes dictionary and precompute offsets
        axes_dict = build_axes_dict(shape_manager)
        print(f"Built axes dictionary with {len(axes_dict)} axes")

        # Compute segment offsets for each axis
        segment_offsets_by_axis = {}
        for axis_id, segments_gdf in axes_dict.items():
            segment_offsets_by_axis[axis_id] = compute_segment_offsets(segments_gdf)

        # Precompute HMM caches for performance
        hmm_caches = precompute_hmm_caches(axes_dict)
        print("HMM initialization complete")

    vm = VehicleManager(grid_obj)
    print("Input start:", start_date, "end:", end_date)
    print("Types:", type(start_date), type(end_date))

    # When using HMM, build trajectories directly without VehicleManager filtering
    if use_hmm and not hmm_shadow_mode:
        print("Building trajectories for HMM (no pre-filtering by route/shape)...")
        from gtfs_rt.models import GPSPulse
        from shapely.geometry import Point as shp_Point

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
            print(f"  - Duplicados removidos: {initial - len(gps_df)}")

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

            Returns None if trajectory is invalid (< 2 unique points).
            """
            # Sort by timestamp (should already be sorted, but ensure)
            group = group.sort_values("timestamp", ascending=True).reset_index(
                drop=True
            )

            # Remove consecutive points with same geometry
            group["prev_geom"] = group["geometry"].shift()
            group = group[group["geometry"] != group["prev_geom"]].drop(
                columns="prev_geom"
            )

            # Filter trajectories too short (< 2 points)
            if len(group) < 2:
                return None

            # Extract most frequent route_id and direction_id
            route_id = (
                group["route_id"].mode()[0]
                if not group["route_id"].isna().all()
                else None
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
                    "bearings": [None]
                    * len(group),  # GPSPulse doesn't store bearing yet
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
        print(
            f"Built {len(trajectories_df)} trajectories from {len(gps_df)} GPS points"
        )
        print(
            f"  - Average points per trajectory: {trajectories_df['n_points'].mean():.1f}"
        )

        # Apply HMM batch matching
        from rest_api.util.hmm.hmm import batch_match_trajectories_to_axes

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

        # Process HMM results to generate speed records
        print("Processing HMM results to calculate speeds...")
        speed_records = []
        skipped_trajectories = 0
        total_gps_matched = 0

        # Initialize segment criteria once
        from velocity.segment import FiveHundredMeterSegmentCriteria

        segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)

        # Build axis_id to shape_id mapping (axis_name -> {direction -> shape_pk})
        axis_to_shape = {}
        for shape in shape_manager.shapes:
            # Extract axis name and direction from shape name
            # e.g., "Eje Alameda_0" -> axis="Eje Alameda", direction="0"
            shape_name = shape.name
            if "_" in shape_name:
                axis_name, direction = shape_name.rsplit("_", 1)
            else:
                axis_name = shape_name
                direction = "0"  # default direction

            if axis_name not in axis_to_shape:
                axis_to_shape[axis_name] = {}
            axis_to_shape[axis_name][direction] = str(shape.pk)

        print(f"Built axis_to_shape mapping with {len(axis_to_shape)} axes")
        print(f"Sample mappings: {list(axis_to_shape.items())[:3]}")

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

            for idx in range(len(points)):
                if idx not in valid_indices:
                    distances_on_route.append(None)
                    continue

                seg_idx = matched_segments[idx]
                proj_point = projected_points[idx]

                if seg_idx is None or proj_point is None:
                    distances_on_route.append(None)
                    continue

                # Get segment offset and geometry
                segment_start_distance = segment_offsets.get(seg_idx, 0.0)

                if seg_idx not in segments_gdf.index:
                    distances_on_route.append(None)
                    continue

                segment_geom = segments_gdf.loc[seg_idx, "geometry"]

                # Calculate distance along segment
                try:
                    distance_in_segment = segment_geom.project(proj_point)

                    # For geographic CRS, convert to meters
                    if segments_gdf.crs and segments_gdf.crs.is_geographic:
                        from processors.geometry.point import Point

                        interpolated_point = segment_geom.interpolate(
                            distance_in_segment
                        )
                        start_point = segment_geom.coords[0]

                        p1 = Point(latitude=start_point[1], longitude=start_point[0])
                        p2 = Point(
                            latitude=interpolated_point.y,
                            longitude=interpolated_point.x,
                        )
                        distance_in_segment = p1.haversine_distance(p2)

                    total_distance = segment_start_distance + distance_in_segment
                    distances_on_route.append(total_distance)
                    total_gps_matched += 1

                except Exception as e:
                    distances_on_route.append(None)
                    continue

            # Generate speed records from consecutive valid GPS pairs
            route_id = traj_data.get("route_id")
            direction = traj_data.get("direction")

            # Map axis_id to shape_id using axis name and direction
            direction_str = str(direction) if direction is not None else "0"
            axis_shapes = axis_to_shape.get(best_axis_id)
            if axis_shapes is None:
                # Axis not found
                if skipped_trajectories == 0:
                    print(f"WARNING: Axis '{best_axis_id}' not found in mapping")
                    print(f"  Available axes: {list(axis_to_shape.keys())[:5]}")
                skipped_trajectories += 1
                continue

            shape_id = axis_shapes.get(direction_str)
            if shape_id is None:
                # Try alternative direction or default to first available
                if skipped_trajectories == 0:
                    print(
                        f"WARNING: Direction '{direction_str}' not found for axis '{best_axis_id}'"
                    )
                    print(f"  Available directions: {list(axis_shapes.keys())}")
                # Use first available direction as fallback
                shape_id = list(axis_shapes.values())[0] if axis_shapes else None
                if shape_id is None:
                    skipped_trajectories += 1
                    continue

            for i in range(1, len(distances_on_route)):
                if distances_on_route[i] is None or distances_on_route[i - 1] is None:
                    continue

                # Calculate delta
                delta_distance = distances_on_route[i] - distances_on_route[i - 1]
                delta_time = (timestamps[i] - timestamps[i - 1]).total_seconds()

                # Skip invalid deltas
                if delta_time <= 0 or delta_distance < 0:
                    continue

                # Skip if time gap too large (same as ExpeditionData.MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES)
                if delta_time >= 600:  # 10 minutes
                    continue

                # Use segment_criteria to get spatial segment
                try:
                    spatial_segment = segment_criteria.get_spatial_segment(
                        shape_id, distances_on_route[i]
                    )
                    temporal_segment_obj = segment_criteria.get_temporal_segment(
                        timestamps[i]
                    )

                    # Create speed record
                    speed_record = {
                        "route_id": route_id,
                        "shape_id": shape_id,
                        "pattern_id": "pattern",
                        "spatial_segment_index": spatial_segment.index,
                        "spatial_segment_name": spatial_segment.get_name(),
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
                    print(e)
                    continue

        print(f"Generated {len(speed_records)} speed records from HMM matching")
        print(f"  - Trajectories processed: {len(batch_results)}")
        print(f"  - Trajectories skipped: {skipped_trajectories}")
        print(f"  - GPS points matched: {total_gps_matched}")

        # Continue with aggregation (skip vm.calculate_speed since we already have records)

    else:
        # Use existing buffer-based filtering for grid method or shadow mode comparison
        gps_df: pd.DataFrame = grid_obj.filter_gps_from_dates(start_date, end_date)
        print(f"Retrieved {len(gps_df)} GPS Pulses (pre-filtered by buffer).")

        start_time = time.time()
        for _, gps in gps_df.iterrows():
            vm.add_data(gps)
        end_time = time.time()
        print(
            f"gps_ignored: {vm.gps_ignored}, vehicles: {len(vm.vehicles)}, total expeditions: {sum(len(v.expeditions) for v in vm.vehicles.values())}"
        )
        print(f"GPS processed in {int(end_time - start_time)} seconds.")

    # Apply HMM map matching to expeditions if enabled
    if use_hmm or hmm_shadow_mode:
        print(
            f"{'[SHADOW MODE] ' if hmm_shadow_mode else ''}Applying HMM to expeditions..."
        )
        hmm_start_time = time.time()

        for vehicle_data in vm.vehicles.values():
            for expedition in vehicle_data.expeditions.values():
                hmm_stats.total_expeditions += 1
                hmm_stats.total_gps_points += len(expedition.gps_points)

                # Store original distances for comparison in shadow mode
                if hmm_shadow_mode:
                    original_distances = expedition.gps_distance_on_route.copy()

                # Run HMM matching
                hmm_result = run_hmm_for_expedition(
                    expedition=expedition,
                    axes_dict=axes_dict,
                    segment_offsets_by_axis=segment_offsets_by_axis,
                    precomputed_caches=hmm_caches,
                    max_distance=hmm_max_distance,
                    sigma=hmm_sigma,
                    beta=hmm_beta,
                )

                if hmm_result is not None:
                    # Try to apply HMM results
                    if hmm_shadow_mode:
                        # In shadow mode: apply but then revert for comparison
                        success = apply_hmm_to_expedition(
                            expedition, hmm_result, use_fallback=True
                        )

                        if success:
                            hmm_stats.hmm_matched += 1
                            hmm_stats.hmm_matched_points += len(
                                hmm_result.valid_indices
                            )

                            # Log comparison (optional: could save to file/DB)
                            print(
                                f"  [SHADOW] Expedition {expedition.route_id}/{expedition.license_plate}: "
                                f"coverage={hmm_result.coverage:.1%}, axis={hmm_result.axis_id}"
                            )

                            # Revert to original distances (shadow mode)
                            expedition.gps_distance_on_route = original_distances
                        else:
                            hmm_stats.fallback_used += 1
                    else:
                        # Active mode: apply and keep
                        success = apply_hmm_to_expedition(
                            expedition, hmm_result, use_fallback=True
                        )
                        if success:
                            hmm_stats.hmm_matched += 1
                            hmm_stats.hmm_matched_points += len(
                                hmm_result.valid_indices
                            )
                        else:
                            hmm_stats.fallback_used += 1
                else:
                    # HMM failed, use grid-based (already populated)
                    hmm_stats.fallback_used += 1

        hmm_end_time = time.time()
        print(
            f"HMM processing completed in {int(hmm_end_time - hmm_start_time)} seconds"
        )
        print(
            f"HMM Stats: {hmm_stats.hmm_matched}/{hmm_stats.total_expeditions} expeditions matched"
        )
        print(
            f"  GPS Points: {hmm_stats.hmm_matched_points}/{hmm_stats.total_gps_points} HMM matched"
        )
        print(f"  Fallback: {hmm_stats.fallback_used} expeditions")

    # Calculate speed records: use HMM results if available, otherwise use VehicleManager
    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)

    if use_hmm and not hmm_shadow_mode and "speed_records" in locals():
        # HMM already generated speed_records - use them directly
        print(f"Using {len(speed_records)} speed records from HMM")
    else:
        # Use traditional VehicleManager approach
        speed_records = vm.calculate_speed(segment_criteria)

    # Check if we have any speed records to process
    if not speed_records:
        print("No speed records generated. Exiting.")
        return

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

    df["speed(km/h)"] = round(3.6 * df["distance_mts"] / df["time_secs"], 2)

    # Removing outliers
    # TODO: Remove outliers using historical data (with medians)
    lower_threshold = 4
    upper_threshold = 80
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
            )
            Speed.objects.create(**speed_data)
    print("Speed records up to date.")
