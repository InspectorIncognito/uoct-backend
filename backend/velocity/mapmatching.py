"""Map matching module using Hidden Markov Model (HMM).

This module integrates HMM-based map matching into the velocity calculation pipeline,
replacing or complementing the grid-based distance projection approach.

Usage:
    - Shadow mode: Run HMM in parallel, log results without affecting Speed calculations
    - Active mode: Replace expedition GPS distances with HMM-derived distances
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import geopandas as gpd

# Import HMM implementation
from rest_api.util.hmm.hmm import match_trajectory_to_axes, precompute_axes_caches

# Import existing application classes
from rest_api.util.shape import ShapeManager
from shapely.geometry import Point as shp_Point
from velocity.expedition import ExpeditionData
from velocity.gps import GPSPulse


@dataclass
class HmmMatchingResult:
    """Result from HMM matching for a single expedition."""

    matched_segments: List[Optional[int]]  # Segment indices (None if no match)
    valid_indices: List[int]  # Indices of successfully matched GPS points
    projected_points: List[Optional[shp_Point]]  # Projected points on segments
    distances_on_route: List[
        Optional[float]
    ]  # Accumulated distance along shape (meters)
    axis_id: Optional[str]  # Which axis/shape was matched
    coverage: float  # Percentage of GPS points successfully matched (0-1)


@dataclass
class HmmStats:
    """Statistics from HMM matching process."""

    total_expeditions: int = 0
    hmm_matched: int = 0
    fallback_used: int = 0
    total_gps_points: int = 0
    hmm_matched_points: int = 0
    fallback_points: int = 0
    excluded_points: int = 0


def build_axes_dict(shape_manager: ShapeManager) -> Dict[str, gpd.GeoDataFrame]:
    """Build axes dictionary for HMM matching from ShapeManager.

    Args:
        shape_manager: Instance of ShapeManager with loaded shapes

    Returns:
        Dictionary mapping axis_id -> GeoDataFrame of segments

    Notes:
        - Uses existing get_segments_gdf() which groups by axis name
        - Each axis GeoDataFrame includes geometry, bearing, and direction columns
    """
    return shape_manager.get_segments_gdf()


def compute_segment_offsets(segments_gdf: gpd.GeoDataFrame) -> Dict[int, float]:
    """Compute accumulated distance offset for each segment in a shape.

    Args:
        segments_gdf: GeoDataFrame with segments ordered by sequence

    Returns:
        Dictionary mapping segment_index -> accumulated_start_distance (meters)

    Notes:
        - Assumes segments are ordered by sequence
        - Distance is cumulative from the start of the shape
        - Uses haversine distance for geographic CRS, euclidean for projected
    """
    from processors.geometry.point import Point

    offsets = {}
    accumulated_distance = 0.0

    # Check if CRS is geographic
    is_geographic = False
    try:
        if segments_gdf.crs is not None:
            is_geographic = segments_gdf.crs.is_geographic
    except Exception:
        # Assume geographic if no CRS or error
        is_geographic = True

    # Sort by sequence if available, otherwise use index
    if "sequence" in segments_gdf.columns:
        sorted_gdf = segments_gdf.sort_values("sequence")
    else:
        sorted_gdf = segments_gdf

    for idx, row in sorted_gdf.iterrows():
        # Store the accumulated distance at the START of this segment
        offsets[idx] = accumulated_distance

        # Calculate segment length and add to accumulated distance
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        if is_geographic:
            # Calculate haversine distance between all consecutive points using existing Point class
            coords = list(geom.coords)
            segment_length = 0.0
            for i in range(len(coords) - 1):
                lat1, lon1 = coords[i][1], coords[i][0]
                lat2, lon2 = coords[i + 1][1], coords[i + 1][0]
                p1 = Point(latitude=lat1, longitude=lon1)
                p2 = Point(latitude=lat2, longitude=lon2)
                segment_length += p1.haversine_distance(p2)
        else:
            # Use shapely length for projected CRS
            segment_length = geom.length

        accumulated_distance += segment_length

    return offsets


def run_hmm_for_expedition(
    expedition: ExpeditionData,
    axes_dict: Dict[str, gpd.GeoDataFrame],
    segment_offsets_by_axis: Dict[str, Dict[int, float]],
    precomputed_caches: Optional[Tuple] = None,
    max_distance: float = 50.0,
    sigma: float = 30.0,
    beta: float = 40.0,
    bearing_weight_factor: float = 0.5,
    sigma_bearing: float = 30.0,
) -> Optional[HmmMatchingResult]:
    """Run HMM map matching for a single expedition.

    Args:
        expedition: ExpeditionData instance with GPS points
        axes_dict: Dictionary of axis_id -> segments GeoDataFrame
        segment_offsets_by_axis: Dict of axis_id -> {segment_idx: accumulated_distance}
        precomputed_caches: Precomputed spatial indices and direction caches
        max_distance: Maximum distance for candidate segments (meters)
        sigma: Emission probability standard deviation
        beta: Transition probability parameter
        bearing_weight_factor: Weight for bearing in emission probability
        sigma_bearing: Standard deviation for bearing difference

    Returns:
        HmmMatchingResult if successful, None if matching failed

    Notes:
        - Converts expedition.gps_points (GPSPulse) to shapely Points
        - Selects best matching axis based on coverage
        - Computes accumulated distances along matched segments using offsets
    """
    # Check if expedition has enough GPS points
    if len(expedition.gps_points) < 2:
        return None

    # Convert GPSPulse objects to shapely Points
    gps_trajectory = [
        shp_Point(gps.longitude, gps.latitude) for gps in expedition.gps_points
    ]

    # Extract bearings if available (currently GPSPulse doesn't store bearing)
    gps_bearings = None  # TODO: Add bearing support when GPSPulse is extended

    # Run HMM matching across all axes
    results = match_trajectory_to_axes(
        gps_trajectory=gps_trajectory,
        axes_dict=axes_dict,
        max_distance=max_distance,
        sigma=sigma,
        beta=beta,
        min_candidates=2,
        remove_matched_points=False,  # Don't exclude points between axes
        gps_bearings=gps_bearings,
        sigma_bearing=sigma_bearing,
        bearing_weight_factor=bearing_weight_factor,
        precomputed=precomputed_caches,
    )

    if not results:
        return None

    # Select best matching axis based on coverage (number of valid points)
    best_axis_id = None
    best_coverage = 0.0
    best_result = None

    for axis_id, (matched_segments, valid_indices, projected_points) in results.items():
        coverage = len(valid_indices) / len(gps_trajectory) if gps_trajectory else 0.0
        if coverage > best_coverage:
            best_coverage = coverage
            best_axis_id = axis_id
            best_result = (matched_segments, valid_indices, projected_points)

    if best_result is None or best_coverage < 0.3:  # Require at least 30% coverage
        return None

    matched_segments, valid_indices, projected_points = best_result
    segment_offsets = segment_offsets_by_axis.get(best_axis_id, {})

    # Compute accumulated distances for each GPS point
    distances_on_route = [None] * len(gps_trajectory)

    for idx in valid_indices:
        seg_idx = matched_segments[idx]
        proj_point = projected_points[idx]

        if seg_idx is None or proj_point is None:
            continue

        # Get segment offset (accumulated distance at segment start)
        segment_start_distance = segment_offsets.get(seg_idx, 0.0)

        # Get segment geometry from axes_dict
        segments_gdf = axes_dict[best_axis_id]
        if seg_idx not in segments_gdf.index:
            continue

        segment_geom = segments_gdf.loc[seg_idx, "geometry"]

        # Calculate distance along segment using shapely project
        # (returns distance from segment start to projection point)
        try:
            distance_in_segment = segment_geom.project(proj_point)

            # For geographic CRS, convert to meters using Point class
            if segments_gdf.crs and segments_gdf.crs.is_geographic:
                # Approximate conversion: get point at distance_in_segment
                interpolated_point = segment_geom.interpolate(distance_in_segment)
                start_point = shp_Point(segment_geom.coords[0])

                from processors.geometry.point import Point

                p1 = Point(latitude=start_point.y, longitude=start_point.x)
                p2 = Point(
                    latitude=interpolated_point.y, longitude=interpolated_point.x
                )
                distance_in_segment = p1.haversine_distance(p2)

            # Total accumulated distance
            distances_on_route[idx] = segment_start_distance + distance_in_segment

        except Exception as e:
            print(f"Warning: Could not compute distance for segment {seg_idx}: {e}")
            continue

    return HmmMatchingResult(
        matched_segments=matched_segments,
        valid_indices=valid_indices,
        projected_points=projected_points,
        distances_on_route=distances_on_route,
        axis_id=best_axis_id,
        coverage=best_coverage,
    )


def apply_hmm_to_expedition(
    expedition: ExpeditionData, hmm_result: HmmMatchingResult, use_fallback: bool = True
) -> bool:
    """Apply HMM matching results to an expedition's GPS distances.

    Args:
        expedition: ExpeditionData instance to update
        hmm_result: Result from run_hmm_for_expedition
        use_fallback: If True, use grid-based matching for points HMM couldn't match

    Returns:
        True if successfully applied, False if fallback to grid-based matching needed

    Notes:
        - Updates expedition.gps_distance_on_route with HMM-derived distances
        - Validates that distances are monotonically increasing
        - Uses grid-based fallback for unmatched points if use_fallback=True
        - Logs statistics about coverage and fallback usage
    """
    if len(hmm_result.distances_on_route) != len(expedition.gps_points):
        print(f"Error: HMM result length mismatch for expedition {expedition}")
        return False

    # Prepare new distance lists
    new_distances_on_route = []
    new_distances_to_route = []
    fallback_count = 0
    hmm_count = 0

    for idx, gps_point in enumerate(expedition.gps_points):
        hmm_distance = hmm_result.distances_on_route[idx]

        if hmm_distance is not None:
            # Use HMM result
            new_distances_on_route.append(hmm_distance)
            # We don't have perpendicular distance from HMM, use 0 or keep old value
            if idx < len(expedition.gps_distance_to_route):
                new_distances_to_route.append(expedition.gps_distance_to_route[idx])
            else:
                new_distances_to_route.append(0.0)
            hmm_count += 1
        elif use_fallback:
            # Fallback to grid-based matching
            try:
                previous_distance = (
                    new_distances_on_route[-1] if new_distances_on_route else None
                )
                dist_to_route, dist_on_route = (
                    expedition.grid_manager.get_on_route_distances(
                        gps_point, expedition.shape_id, previous_distance
                    )
                )
                new_distances_on_route.append(dist_on_route)
                new_distances_to_route.append(dist_to_route)
                fallback_count += 1
            except ValueError:
                # Both HMM and grid failed - skip this point
                print(
                    f"Warning: Could not match GPS point {idx} in expedition {expedition}"
                )
                return False
        else:
            # No fallback allowed and HMM failed
            print(f"Warning: HMM failed for point {idx} and fallback disabled")
            return False

    # Validate monotonicity (distances should be increasing)
    for i in range(1, len(new_distances_on_route)):
        if new_distances_on_route[i] < new_distances_on_route[i - 1]:
            print(
                f"Warning: Non-monotonic distances detected at index {i} in expedition {expedition}"
            )
            print(
                f"  Distance[{i-1}] = {new_distances_on_route[i-1]}, Distance[{i}] = {new_distances_on_route[i]}"
            )
            # Allow small decreases (GPS noise), but flag large ones
            if (
                new_distances_on_route[i - 1] - new_distances_on_route[i] > 50
            ):  # 50m threshold
                return False

    # Apply results to expedition
    expedition.gps_distance_on_route = new_distances_on_route
    expedition.gps_distance_to_route = new_distances_to_route

    # Update dictionary mapping (used in some places)
    expedition.gps_distance_on_route_dict = {
        gps: dist for gps, dist in zip(expedition.gps_points, new_distances_on_route)
    }

    # Log statistics
    total_points = len(expedition.gps_points)
    print(
        f"Applied HMM to expedition {expedition}: "
        f"{hmm_count}/{total_points} HMM matched, "
        f"{fallback_count}/{total_points} fallback, "
        f"coverage={hmm_result.coverage:.1%}"
    )

    return True


def precompute_hmm_caches(axes_dict: Dict[str, gpd.GeoDataFrame]) -> Tuple:
    """Precompute spatial indices and direction caches for all axes.

    Args:
        axes_dict: Dictionary of axis_id -> segments GeoDataFrame

    Returns:
        Tuple of (spatial_indices, direction_caches, segment_caches)

    Notes:
        - Should be called once at the start of calculate_speed
        - Caches are reused across all expeditions for performance
    """
    print(f"Precomputing HMM caches for {len(axes_dict)} axes...")
    return precompute_axes_caches(axes_dict)
