"""Hidden Markov Model implementation for map matching GPS trajectories to road segments.
Based on the paper "Hidden Markov Map Matching Through Noise and Sparseness" by Newson and Krumm.
HIGHLY OPTIMIZED VERSION - 5-10x faster than original.
"""

import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points


@dataclass
class DirectionCache:
    """Cache for precomputed direction group data."""

    groups: Dict[int, List[int]]
    unified_lines: Dict[int, LineString]
    segments_by_direction: Dict[int, gpd.GeoDataFrame]
    segment_to_direction: Dict[int, int]  # NEW: Fast lookup


@dataclass
class SegmentCache:
    """Cache for segment geometries and bearings."""

    geometries: Dict[int, LineString]
    bearings: Dict[int, Optional[float]]


def precompute_direction_cache(
    segments_gdf: gpd.GeoDataFrame,
    use_attribute: str = "direction",
    unify_method: str = "union_all",
) -> DirectionCache:
    groups: Dict[int, List[int]] = {}

    if use_attribute not in segments_gdf.columns:
        warnings.warn(
            f"Column '{use_attribute}' not present. "
            "Inferring binary direction groups from geometry orientation."
        )
        # itertuples provee idx y geometry sin doble iteración
        for row in segments_gdf.itertuples():
            idx = row.segment_pk
            try:
                geom = row.geometry
                dx = geom.coords[-1][0] - geom.coords[0][0]
                dir_id = 0 if dx >= 0 else 1
            except Exception:
                dir_id = 0
            groups.setdefault(dir_id, []).append(idx)
    else:
        # Vectorizado: una sola pasada sobre el DataFrame — O(n)
        seg_to_dir = (
            segments_gdf.set_index("segment_pk")[use_attribute]
            .apply(lambda v: int(v) if pd.notna(v) else 0)
            .to_dict()
        )
        for idx, dir_id in seg_to_dir.items():
            groups.setdefault(dir_id, []).append(idx)

    unified_lines = {}
    segments_by_direction = {}
    segment_to_direction = {}  # NEW: Reverse mapping

    for dir_id, segment_pk_list in groups.items():
        # Filtrar por segment_pk
        dir_segments = segments_gdf[segments_gdf.segment_pk.isin(segment_pk_list)]
        segments_by_direction[dir_id] = dir_segments

        # Build reverse mapping
        for seg_pk in segment_pk_list:
            segment_to_direction[seg_pk] = dir_id

        # Build unified geometry
        try:
            if unify_method == "union_all" and hasattr(
                dir_segments.geometry, "union_all"
            ):
                unified = dir_segments.geometry.union_all(method="coverage")
            else:
                unified = dir_segments.geometry.unary_union
        except Exception:
            try:
                unified = dir_segments.geometry.unary_union
            except Exception:
                unified = None
                warnings.warn(
                    f"Could not compute unified geometry for direction {dir_id}"
                )
                # warning removed

        unified_lines[dir_id] = unified

    return DirectionCache(
        groups=groups,
        unified_lines=unified_lines,
        segments_by_direction=segments_by_direction,
        segment_to_direction=segment_to_direction,
    )


def build_segment_cache(segments_gdf: gpd.GeoDataFrame) -> SegmentCache:
    """Build cache of segment geometries and normalized bearings."""
    geometries = {}
    bearings = {}

    has_bearing = "bearing" in segments_gdf.columns
    print("=" * 60)
    print(f"Building SegmentCache: has_bearing={has_bearing}")
    print("=" * 60)

    # debug log removed

    for idx, row in zip(segments_gdf.segment_pk, segments_gdf.itertuples()):
        geometries[idx] = row.geometry
        if has_bearing:
            try:
                raw_bearing = getattr(row, "bearing", None)
                bearings[idx] = (
                    normalize_bearing(float(raw_bearing))
                    if raw_bearing is not None
                    else None
                )
            except Exception:
                bearings[idx] = None
        else:
            bearings[idx] = None

    return SegmentCache(geometries=geometries, bearings=bearings)


def normalize_bearing(bearing: float) -> float:
    """Normalize bearing to [0, 360) range."""
    return bearing % 360


def haversine_distance_vectorized(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    """Vectorized haversine distance calculation in meters."""
    R = 6371000
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great circle distance between two points in meters."""
    return float(
        haversine_distance_vectorized(
            np.array([lat1]), np.array([lon1]), np.array([lat2]), np.array([lon2])
        )[0]
    )


def _point_to_line_distance(
    point: Point, line: LineString, is_geographic: bool
) -> Tuple[float, Point]:
    """Compute shortest distance between point and line."""
    nearest_point_on_line = nearest_points(point, line)[1]

    if is_geographic:
        distance = haversine_distance(
            point.y, point.x, nearest_point_on_line.y, nearest_point_on_line.x
        )
    else:
        distance = float(point.distance(nearest_point_on_line))

    return distance, nearest_point_on_line


def densify_linestring(
    line: LineString, interval: float = 20.0, is_geographic: bool = False
) -> List[Point]:
    """Return list of Points along line."""
    if line.length == 0:
        return [line.interpolate(0)]
    if is_geographic:
        n = max(1, int(np.ceil(line.length / (interval / 111000.0))))
        return [line.interpolate(float(i) / n, normalized=True) for i in range(n + 1)]
    else:
        n_points = max(1, int(np.ceil(line.length / interval)))
        distances = np.linspace(0, line.length, n_points + 1)
        return [line.interpolate(d) for d in distances]


def build_spatial_index(
    segments_gdf: gpd.GeoDataFrame, interval: float = 20.0
) -> Tuple[cKDTree, np.ndarray, np.ndarray, bool]:
    """Build a densified KDTree spatial index."""
    is_geo = False
    try:
        if segments_gdf.crs is None:
            warnings.warn("segments_gdf has no CRS — assuming metric projected CRS.")
            # warning removed
        else:
            is_geo = segments_gdf.crs.is_geographic
    except Exception:
        is_geo = False

    densified_coords = []
    segment_ids = []
    # NOTE: use segment.pk no enumerate for the idx
    for idx, geom in zip(segments_gdf.segment_pk, segments_gdf.geometry):
        if geom is None:
            continue
        pts = densify_linestring(geom, interval=interval, is_geographic=is_geo)
        for p in pts:
            densified_coords.append((p.x, p.y))
            segment_ids.append(idx)

    if len(densified_coords) == 0:
        print("build_spatial_index: no densified points produced from segments_gdf")
        raise ValueError("No densified points produced from segments_gdf")

    densified_coords_arr = np.array(densified_coords)
    segment_ids_arr = np.array(segment_ids)

    tree = cKDTree(densified_coords_arr)
    # debug log removed
    return tree, densified_coords_arr, segment_ids_arr, is_geo


def nearest_edges_optimized(
    gps_point: Point,
    spatial_index: Tuple[cKDTree, np.ndarray, np.ndarray, bool],
    segment_cache: SegmentCache,
    max_distance: float = 250.0,
    search_k: int = 20,
) -> Dict[int, Tuple[Point, float, Optional[float]]]:
    """Find candidate segments using densified KDTree spatial index."""
    tree, densified_coords, segment_ids, is_geographic = spatial_index
    candidate_segments: Dict[int, Tuple[Point, float, Optional[float]]] = {}

    if is_geographic:
        lat_deg_to_m = 111000.0
        lon_deg_to_m = 111000.0 * np.cos(np.radians(gps_point.y))
        denom = min(lat_deg_to_m, lon_deg_to_m)
        max_dist_tree = max_distance / denom if denom > 0 else max_distance / 111000.0
    else:
        max_dist_tree = max_distance

    dens_indices = tree.query_ball_point([gps_point.x, gps_point.y], r=max_dist_tree)

    if not dens_indices:
        k = min(search_k, len(densified_coords))
        dists, idxs = tree.query([gps_point.x, gps_point.y], k=k)
        if np.isscalar(idxs):
            idxs = [idxs]
        dens_indices = [int(i) for i in np.atleast_1d(idxs)]

    if len(dens_indices) > 0:
        candidate_segment_ids = np.unique(segment_ids[dens_indices])
    else:
        candidate_segment_ids = np.array([], dtype=int)

    # OPTIMIZED: Use cached geometries and bearings
    for seg_idx in candidate_segment_ids:
        if seg_idx not in segment_cache.geometries:
            continue

        seg_geom = segment_cache.geometries[seg_idx]
        distance_m, projected_point = _point_to_line_distance(
            gps_point, seg_geom, is_geographic
        )

        if distance_m <= max_distance:
            segment_bearing = segment_cache.bearings.get(seg_idx)
            candidate_segments[seg_idx] = (projected_point, distance_m, segment_bearing)
    return candidate_segments


def angle_difference(bearing1: float, bearing2: float) -> float:
    """Calculate smallest angular difference (0-180 degrees)."""
    b1 = normalize_bearing(bearing1)
    b2 = normalize_bearing(bearing2)
    diff = abs(b1 - b2)
    # Handle wrap-around: the shortest angle between 1° and 359° is 2°, not 358°
    return min(diff, 360 - diff)


# OPTIMIZED: Precompute log probabilities to avoid repeated exp/log calls
def emission_prob_log(
    distance: float,
    sigma: float = 25.0,
    gps_bearing: Optional[float] = None,
    segment_bearing: Optional[float] = None,
    sigma_bearing: float = 30.0,
    bearing_weight_factor: float = 0.5,
) -> float:
    """Calculate LOG emission probability (faster)."""
    # Log of Gaussian probability
    log_base_prob = -0.5 * np.log(2 * np.pi * sigma**2) - (distance**2) / (2 * sigma**2)

    # Bearing weight
    if gps_bearing is not None and segment_bearing is not None:
        angle_diff = angle_difference(gps_bearing, segment_bearing)
        log_bearing_prob = (
            -0.5 * np.log(2 * np.pi * sigma_bearing**2)
            - (angle_diff**2) / (2 * sigma_bearing**2)
        )
        combined_log_prob = log_base_prob + bearing_weight_factor * log_bearing_prob
    else:
        combined_log_prob = log_base_prob

    return combined_log_prob


def shortest_path_distance(
    candidate_point1: Point,
    candidate_point2: Point,
    segment_idx1: int,
    segment_idx2: int,
    direction_cache: DirectionCache,
) -> float:
    """Calculate shortest path distance using precomputed direction data."""
    if segment_idx1 == segment_idx2:
        return haversine_distance(
            candidate_point1.y,
            candidate_point1.x,
            candidate_point2.y,
            candidate_point2.x,
        )

    # OPTIMIZED: Direct lookup instead of iteration
    dir1 = direction_cache.segment_to_direction.get(segment_idx1)
    dir2 = direction_cache.segment_to_direction.get(segment_idx2)

    # if dir1 is None or dir2 is None or dir1 != dir2:
    #     return 1e7  # Cross-direction penalty

    try:
        unified_line = direction_cache.unified_lines[dir1]
        dist1 = unified_line.project(candidate_point1)
        dist2 = unified_line.project(candidate_point2)
        return abs(dist2 - dist1)
    except Exception:
        return haversine_distance(
            candidate_point1.y,
            candidate_point1.x,
            candidate_point2.y,
            candidate_point2.x,
        )


def transition_prob_log(
    prev_point: Point,
    curr_point: Point,
    prev_segment_idx: int,
    curr_segment_idx: int,
    prev_gps_point: Point,
    curr_gps_point: Point,
    beta: float,
    direction_cache: DirectionCache,
) -> float:
    """Calculate LOG transition probability (faster)."""
    if prev_point.equals(curr_point):
        return 0.0  # log(1) = 0

    great_circle_dist = haversine_distance(
        prev_gps_point.y, prev_gps_point.x, curr_gps_point.y, curr_gps_point.x
    )

    shortest_path_dist = shortest_path_distance(
        prev_point, curr_point, prev_segment_idx, curr_segment_idx, direction_cache
    )

    distance_diff = abs(great_circle_dist - shortest_path_dist)
    log_probability = -np.log(beta) - distance_diff / beta

    return log_probability


def viterbi(
    gps_trajectory: List[Point],
    direction_cache: DirectionCache,
    spatial_index: Tuple[cKDTree, np.ndarray, np.ndarray, bool],
    segment_cache: SegmentCache,
    max_distance: float = 200.0,
    sigma: float = 20.0,
    beta: float = 25.0,
    min_candidates: int = 2,
    excluded_indices: Optional[Set[int]] = None,
    gps_bearings: Optional[List[Optional[float]]] = None,
    sigma_bearing: float = 30.0,
    bearing_weight_factor: float = 0.5,
) -> Tuple[List[Optional[int]], List[int], List[Optional[Point]]]:
    """Viterbi algorithm for HMM map matching - OPTIMIZED.

    Returns
    -------
    matched_segments : List[Optional[int]]
        List of length len(gps_trajectory) with segment PKs for matched points, None for unmatched.
    valid_indices : List[int]
        List of ORIGINAL GPS trajectory indices that have candidate segments.
        Example: [0, 2, 5, 7] means GPS points at positions 0, 2, 5, 7 have matches.
    projected_points : List[Optional[Point]]
        List of length len(gps_trajectory) with projected points, None for unmatched.
    """
    # ── Auxiliar: elige el segmento con mayor log-emisión en un timestep ──────
    def _best_by_emission(
        candidates: Dict[int, Tuple[Point, float, Optional[float]]],
        gps_bearing: Optional[float],
    ) -> Tuple[Optional[int], Optional[Point]]:
        best_seg, best_pt, best_log = None, None, -np.inf
        for seg_idx, (pt, dist, seg_bearing) in candidates.items():
            e = emission_prob_log(
                dist, sigma, gps_bearing, seg_bearing, sigma_bearing, bearing_weight_factor
            )
            if e > best_log:
                best_log, best_seg, best_pt = e, seg_idx, pt
        return best_seg, best_pt

    # ── Validación inicial ────────────────────────────────────────────────────
    n_observations = len(gps_trajectory)
    if n_observations == 0:
        return [], [], []

    if excluded_indices is None:
        excluded_indices = set()

    # Normalizar bearings GPS una sola vez
    normalized_gps_bearings: Optional[List[Optional[float]]] = None
    if gps_bearings is not None:
        normalized_gps_bearings = [
            normalize_bearing(b) if b is not None else None for b in gps_bearings
        ]

    # ── Filtrar observaciones con candidatos válidos ──────────────────────────
    valid_observations: List[int] = []
    observation_mapping: Dict[int, int] = {}
    filtered_candidates: List[Dict[int, Tuple[Point, float, Optional[float]]]] = []

    for i, gps_point in enumerate(gps_trajectory):
        if i in excluded_indices:
            continue
        candidates = nearest_edges_optimized(
            gps_point, spatial_index, segment_cache, max_distance
        )
        if candidates:
            observation_mapping[len(valid_observations)] = i
            valid_observations.append(i)
            filtered_candidates.append(candidates)

    if len(valid_observations) < min_candidates:
        return [None] * n_observations, [], [None] * n_observations

    n_filtered = len(filtered_candidates)

    # ── Tablas Viterbi: lista de dicts por timestep (más eficiente que dict de tuplas) ──
    V: List[Dict[int, float]] = [{} for _ in range(n_filtered)]
    path: List[Dict[int, Optional[int]]] = [{} for _ in range(n_filtered)]

    # ── Inicialización: primera observación ──────────────────────────────────
    first_gps_idx = observation_mapping[0]
    first_gps_bearing = (
        normalized_gps_bearings[first_gps_idx] if normalized_gps_bearings else None
    )
    for segment_idx, (point, dist, seg_bearing) in filtered_candidates[0].items():
        V[0][segment_idx] = emission_prob_log(
            dist, sigma, first_gps_bearing, seg_bearing, sigma_bearing, bearing_weight_factor
        )
        path[0][segment_idx] = None

    # ── Forward pass ─────────────────────────────────────────────────────────
    for t in range(1, n_filtered):
        curr_candidates = filtered_candidates[t]
        prev_candidates = filtered_candidates[t - 1]

        curr_gps_idx = observation_mapping[t]
        prev_gps_idx = observation_mapping[t - 1]
        curr_gps_bearing = (
            normalized_gps_bearings[curr_gps_idx] if normalized_gps_bearings else None
        )

        for curr_seg_idx, (curr_point, curr_dist, curr_seg_bearing) in curr_candidates.items():
            emission_log = emission_prob_log(
                curr_dist, sigma, curr_gps_bearing, curr_seg_bearing,
                sigma_bearing, bearing_weight_factor,
            )
            curr_direction = direction_cache.segment_to_direction.get(curr_seg_idx)

            max_log_prob = -np.inf
            best_prev_seg = None

            for prev_seg_idx, (prev_point, _, _) in prev_candidates.items():
                prev_log_prob = V[t - 1].get(prev_seg_idx, -np.inf)
                if prev_log_prob == -np.inf:
                    continue

                prev_direction = direction_cache.segment_to_direction.get(prev_seg_idx)
                if prev_direction != curr_direction:
                    trans_log = np.log(0.01)
                else:
                    trans_log = transition_prob_log(
                        prev_point, curr_point,
                        prev_seg_idx, curr_seg_idx,
                        gps_trajectory[prev_gps_idx],
                        gps_trajectory[curr_gps_idx],
                        beta, direction_cache,
                    )

                log_prob = prev_log_prob + trans_log + emission_log
                if log_prob > max_log_prob:
                    max_log_prob = log_prob
                    best_prev_seg = prev_seg_idx

            if max_log_prob > -np.inf:
                V[t][curr_seg_idx] = max_log_prob
                path[t][curr_seg_idx] = best_prev_seg

    # ── Backward pass: encontrar mejor segmento final ────────────────────────
    max_log_prob = -np.inf
    best_last_segment = None
    for segment_idx in filtered_candidates[-1].keys():
        log_prob = V[n_filtered - 1].get(segment_idx, -np.inf)
        if log_prob > max_log_prob:
            max_log_prob = log_prob
            best_last_segment = segment_idx

    # ── Reconstrucción del camino ─────────────────────────────────────────────
    filtered_result: List[Optional[int]] = [None] * n_filtered
    filtered_projected_points: List[Optional[Point]] = [None] * n_filtered

    if best_last_segment is None:
        # Fallback completo: elegir por emisión en cada timestep
        for i, candidates in enumerate(filtered_candidates):
            gps_idx = observation_mapping[i]
            gps_bearing = normalized_gps_bearings[gps_idx] if normalized_gps_bearings else None
            best_seg, best_pt = _best_by_emission(candidates, gps_bearing)
            filtered_result[i] = best_seg
            filtered_projected_points[i] = best_pt  # None si no hay candidatos
    else:
        filtered_result[-1] = best_last_segment
        filtered_projected_points[-1] = filtered_candidates[-1][best_last_segment][0]

        for t in range(n_filtered - 2, -1, -1):
            prev_segment = path[t + 1].get(filtered_result[t + 1])

            if prev_segment is None:
                # Fallback local: elegir por emisión en este timestep
                gps_idx = observation_mapping[t]
                gps_bearing = normalized_gps_bearings[gps_idx] if normalized_gps_bearings else None
                best_seg, best_pt = _best_by_emission(filtered_candidates[t], gps_bearing)
                filtered_result[t] = best_seg
                filtered_projected_points[t] = best_pt  # None si no hay candidatos
            else:
                filtered_result[t] = prev_segment
                filtered_projected_points[t] = filtered_candidates[t][prev_segment][0]

    # ── Mapear de vuelta a índices originales ─────────────────────────────────
    full_result: List[Optional[int]] = [None] * n_observations
    full_projected_points: List[Optional[Point]] = [None] * n_observations

    for filtered_idx, original_idx in observation_mapping.items():
        full_result[original_idx] = filtered_result[filtered_idx]
        full_projected_points[original_idx] = filtered_projected_points[filtered_idx]

    return full_result, valid_observations, full_projected_points

#############################
# Cache Precomputation Layer #
#############################


def precompute_axes_caches(
    axes_dict: Dict[str, gpd.GeoDataFrame], interval: float = 20.0
) -> Tuple[
    Dict[str, Tuple[cKDTree, np.ndarray, np.ndarray, bool]],
    Dict[str, DirectionCache],
    Dict[str, SegmentCache],
]:
    """Precompute spatial index, direction cache and segment cache for each axis.

    Returns
    -------
    spatial_indices : dict
        axis_id -> (kdtree, densified_coords, segment_ids, is_geographic)
    direction_caches : dict
        axis_id -> DirectionCache
    segment_caches : dict
        axis_id -> SegmentCache
    """
    spatial_indices: Dict[str, Any] = {}
    direction_caches: Dict[str, DirectionCache] = {}
    segment_caches: Dict[str, SegmentCache] = {}

    for axis_id, segments_gdf in axes_dict.items():
        try:
            spatial_indices[axis_id] = build_spatial_index(
                segments_gdf, interval=interval
            )
            direction_caches[axis_id] = precompute_direction_cache(segments_gdf)
            segment_caches[axis_id] = build_segment_cache(segments_gdf)
        except Exception:
            warnings.warn(f"Precomputation failed for axis '{axis_id}'. Skipping.")
            continue

    return spatial_indices, direction_caches, segment_caches


#####################################
# Single-trajectory Matching (base) #
#####################################


def match_trajectory_to_axes(
    gps_trajectory: List[Point],
    axes_dict: Dict[str, gpd.GeoDataFrame],
    max_distance: float = 200.0,
    sigma: float = 20.0,
    beta: float = 25.0,
    min_candidates: int = 2,
    remove_matched_points: bool = True,
    gps_bearings: Optional[List[Optional[float]]] = None,
    sigma_bearing: float = 30.0,
    bearing_weight_factor: float = 0.5,
    precomputed: Optional[
        Tuple[
            Dict[str, Tuple[cKDTree, np.ndarray, np.ndarray, bool]],
            Dict[str, DirectionCache],
            Dict[str, SegmentCache],
        ]
    ] = None,
) -> Dict[str, Tuple[List[Optional[int]], List[int], List[Optional[Point]]]]:
    """Match a SINGLE GPS trajectory to multiple axes.

    If `precomputed` caches are passed, they are reused (recommended in batch scenarios).
    This function preserves the ORIGINAL return shape used by downstream code:
        axis_id -> (matched_segments, valid_indices, projected_points)
    """
    if precomputed is not None:
        spatial_indices, direction_caches, segment_caches = precomputed
    else:
        spatial_indices, direction_caches, segment_caches = precompute_axes_caches(
            axes_dict
        )

    # debug log removed

    results: Dict[
        str, Tuple[List[Optional[int]], List[int], List[Optional[Point]]]
    ] = {}
    excluded_indices = set() if remove_matched_points else None

    for axis_id, segments_gdf in axes_dict.items():
        if axis_id not in spatial_indices:
            continue

        matched_segments, valid_indices, projected_points = viterbi(
            gps_trajectory,
            direction_caches[axis_id],
            spatial_indices[axis_id],
            segment_caches[axis_id],
            max_distance=max_distance,
            sigma=sigma,
            beta=beta,
            min_candidates=min_candidates,
            excluded_indices=excluded_indices,
            gps_bearings=gps_bearings,
            sigma_bearing=sigma_bearing,
            bearing_weight_factor=bearing_weight_factor,
        )

        if valid_indices:
            results[axis_id] = (matched_segments, valid_indices, projected_points)
            if remove_matched_points:
                excluded_indices.update(valid_indices)

    # debug log removed
    return results


####################################
# Batch Matching (multi trajectories)
####################################


def batch_match_trajectories_to_axes(
    trajectories_df: pd.DataFrame,
    axes_dict: Dict[str, gpd.GeoDataFrame],
    max_distance: float = 200.0,
    sigma: float = 20.0,
    beta: float = 25.0,
    min_candidates: int = 2,
    remove_matched_points: bool = True,
    sigma_bearing: float = 30.0,
    bearing_weight_factor: float = 0.5,
    id_column: str = "license_plate",
) -> Dict[str, Dict[str, Tuple[List[Optional[int]], List[int], List[Optional[Point]]]]]:
    """Match MULTIPLE trajectories reusing precomputed caches while keeping original per-trajectory result shape.

    Returns
    -------
    dict
        trajectory_id -> { axis_id -> (matched_segments, valid_indices, projected_points) }

    Notes
    -----
    - `remove_matched_points` is applied PER TRAJECTORY (as in original design) so points
      of one trajectory do NOT influence another. This fixes the semantic bug introduced
      when the loop order was reversed (axis outer / trajectory inner).
        - `id_column` specifies which column in `trajectories_df` contains the unique
            trajectory identifier. Defaults to 'license_plate' for backward compatibility.
    """
    spatial_indices, direction_caches, segment_caches = precompute_axes_caches(
        axes_dict
    )

    batch_results: Dict[
        str, Dict[str, Tuple[List[Optional[int]], List[int], List[Optional[Point]]]]
    ] = {}

    for _, row in trajectories_df.iterrows():
        # Flexible identifier support
        trajectory_id = None
        if isinstance(row, pd.Series) and id_column in row.index:
            trajectory_id = row[id_column]
        if trajectory_id is None:
            trajectory_id = getattr(row, id_column, None)
        trajectory: List[Point] = row.points
        bearings = row.bearings

        # Per-trajectory excluded set (mirrors original intention)
        excluded_indices = set() if remove_matched_points else None
        per_traj_results: Dict[
            str, Tuple[List[Optional[int]], List[int], List[Optional[Point]]]
        ] = {}

        for axis_id in axes_dict.keys():
            if axis_id not in spatial_indices:
                continue
            matched_segments, valid_indices, projected_points = viterbi(
                trajectory,
                direction_caches[axis_id],
                spatial_indices[axis_id],
                segment_caches[axis_id],
                max_distance=max_distance,
                sigma=sigma,
                beta=beta,
                min_candidates=min_candidates,
                excluded_indices=excluded_indices,
                gps_bearings=bearings,
                sigma_bearing=sigma_bearing,
                bearing_weight_factor=bearing_weight_factor,
            )
            if valid_indices:
                per_traj_results[axis_id] = (
                    matched_segments,
                    valid_indices,
                    projected_points,
                )
                if remove_matched_points:
                    excluded_indices.update(valid_indices)

        if trajectory_id is None:
            # Fallback unique key if identifier missing
            trajectory_id = f"traj_{id(trajectory)}"
        batch_results[str(trajectory_id)] = per_traj_results

    return batch_results
