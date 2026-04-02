"""Rust-accelerated HMM map matching integration.

This module provides a drop-in replacement for the pure Python HMM implementation
when the Rust `map_matching` extension is available.

Usage:
    The existing hmm.py will automatically use this when available via:

    try:
        from rest_api.util.hmm.rust_bridge import (
            USE_RUST,
            viterbi_rust,
            precompute_caches_rust,
        )
    except ImportError:
        USE_RUST = False
"""

from typing import Any, Dict, List, Optional, Set, Tuple

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

# Try to import Rust extension
try:
    import map_matching as mm

    USE_RUST = True
    print(f"Rust map_matching loaded (version {mm.__version__})")
except ImportError:
    USE_RUST = False
    mm = None
    print("Rust map_matching not available, using pure Python")


class RustSpatialIndex:
    """Wrapper around Rust SpatialIndex for compatibility with Python code."""

    def __init__(
        self,
        segments_gdf: gpd.GeoDataFrame,
        interval: float = 20.0,
    ):
        if not USE_RUST:
            raise RuntimeError("Rust map_matching not available")

        # Extract data from GeoDataFrame
        segment_pks = segments_gdf["segment_pk"].tolist()

        # Convert geometries to list of coordinate tuples
        geometries = []
        for geom in segments_gdf.geometry:
            if geom is None:
                geometries.append([])
            else:
                coords = [(x, y) for x, y in geom.coords]
                geometries.append(coords)

        # Determine if geographic
        is_geographic = True
        if segments_gdf.crs is not None:
            is_geographic = segments_gdf.crs.is_geographic

        self._inner = mm.SpatialIndex(
            segment_pks=segment_pks,
            geometries=geometries,
            interval=interval,
            is_geographic=is_geographic,
        )
        self.is_geographic = is_geographic

    def query(self, lon: float, lat: float, max_distance: float) -> List[int]:
        """Query segments within radius."""
        return self._inner.query(lon, lat, max_distance)


class RustDirectionCache:
    """Wrapper around Rust DirectionCache."""

    def __init__(
        self, segments_gdf: gpd.GeoDataFrame, use_attribute: str = "direction"
    ):
        if not USE_RUST:
            raise RuntimeError("Rust map_matching not available")

        segment_pks = segments_gdf["segment_pk"].tolist()

        # Extract directions
        if use_attribute in segments_gdf.columns:
            directions = [
                int(d) if d is not None and not np.isnan(d) else 0
                for d in segments_gdf[use_attribute]
            ]
        else:
            # Infer from geometry orientation
            directions = []
            for geom in segments_gdf.geometry:
                if geom is not None and len(geom.coords) >= 2:
                    dx = geom.coords[-1][0] - geom.coords[0][0]
                    directions.append(0 if dx >= 0 else 1)
                else:
                    directions.append(0)

        # Convert geometries
        geometries = []
        for geom in segments_gdf.geometry:
            if geom is None:
                geometries.append([])
            else:
                coords = [(x, y) for x, y in geom.coords]
                geometries.append(coords)

        self._inner = mm.DirectionCache(
            segment_pks=segment_pks,
            directions=directions,
            geometries=geometries,
        )
        self._segment_to_direction = dict(zip(segment_pks, directions))

    def get_direction(self, segment_pk: int) -> Optional[int]:
        """Get direction for a segment."""
        return self._segment_to_direction.get(segment_pk)


class RustSegmentCache:
    """Wrapper around Rust SegmentCache."""

    def __init__(self, segments_gdf: gpd.GeoDataFrame):
        if not USE_RUST:
            raise RuntimeError("Rust map_matching not available")

        segment_pks = segments_gdf["segment_pk"].tolist()

        # Convert geometries
        geometries = []
        for geom in segments_gdf.geometry:
            if geom is None:
                geometries.append([])
            else:
                coords = [(x, y) for x, y in geom.coords]
                geometries.append(coords)

        # Extract bearings
        has_bearing = "bearing" in segments_gdf.columns
        bearings = []
        for _, row in segments_gdf.iterrows():
            if has_bearing:
                b = row.get("bearing")
                if b is not None and not np.isnan(b):
                    bearings.append(float(b) % 360.0)
                else:
                    bearings.append(None)
            else:
                bearings.append(None)

        self._inner = mm.SegmentCache(
            segment_pks=segment_pks,
            geometries=geometries,
            bearings=bearings,
        )
        self._geometries = dict(zip(segment_pks, geometries))
        self._bearings = dict(zip(segment_pks, bearings))

    def get_bearing(self, segment_pk: int) -> Optional[float]:
        """Get bearing for a segment."""
        return self._bearings.get(segment_pk)


def viterbi_rust(
    gps_trajectory: List[Point],
    direction_cache: RustDirectionCache,
    spatial_index: RustSpatialIndex,
    segment_cache: RustSegmentCache,
    max_distance: float = 200.0,
    sigma: float = 20.0,
    beta: float = 25.0,
    min_candidates: int = 2,
    excluded_indices: Optional[Set[int]] = None,
    gps_bearings: Optional[List[Optional[float]]] = None,
    sigma_bearing: float = 30.0,
    bearing_weight_factor: float = 0.5,
) -> Tuple[List[Optional[int]], List[int], List[Optional[Point]]]:
    """Run Viterbi HMM map matching using Rust implementation.

    This function has the same signature as the Python viterbi() for drop-in replacement.

    Returns
    -------
    matched_segments : List[Optional[int]]
        List of segment PKs for matched points, None for unmatched.
    valid_indices : List[int]
        List of original GPS trajectory indices that have matches.
    projected_points : List[Optional[Point]]
        List of projected points (shapely Points), None for unmatched.
    """
    if not USE_RUST:
        raise RuntimeError("Rust map_matching not available")

    # Extract coordinates from shapely Points
    gps_lons = [p.x for p in gps_trajectory]
    gps_lats = [p.y for p in gps_trajectory]

    # Convert excluded indices to list
    excluded_list = list(excluded_indices) if excluded_indices else None

    # Call Rust implementation
    matched_segments, valid_indices, projected_tuples = mm.viterbi(
        gps_lons=gps_lons,
        gps_lats=gps_lats,
        spatial_index=spatial_index._inner,
        direction_cache=direction_cache._inner,
        segment_cache=segment_cache._inner,
        max_distance=max_distance,
        sigma=sigma,
        beta=beta,
        min_candidates=min_candidates,
        gps_bearings=gps_bearings,
        sigma_bearing=sigma_bearing,
        bearing_weight_factor=bearing_weight_factor,
        excluded_indices=excluded_list,
    )

    # Convert projected points back to shapely Points
    projected_points = []
    for pt in projected_tuples:
        if pt is not None:
            projected_points.append(Point(pt[0], pt[1]))
        else:
            projected_points.append(None)

    return matched_segments, valid_indices, projected_points


def precompute_caches_rust(
    axes_dict: Dict[str, gpd.GeoDataFrame],
    interval: float = 20.0,
) -> Tuple[
    Dict[str, RustSpatialIndex],
    Dict[str, RustDirectionCache],
    Dict[str, RustSegmentCache],
]:
    """Precompute caches for all axes using Rust implementations.

    Returns
    -------
    spatial_indices : dict
        axis_id -> RustSpatialIndex
    direction_caches : dict
        axis_id -> RustDirectionCache
    segment_caches : dict
        axis_id -> RustSegmentCache
    """
    if not USE_RUST:
        raise RuntimeError("Rust map_matching not available")

    spatial_indices = {}
    direction_caches = {}
    segment_caches = {}

    for axis_id, segments_gdf in axes_dict.items():
        try:
            spatial_indices[axis_id] = RustSpatialIndex(segments_gdf, interval)
            direction_caches[axis_id] = RustDirectionCache(segments_gdf)
            segment_caches[axis_id] = RustSegmentCache(segments_gdf)
        except Exception as e:
            print(f"Warning: Failed to create Rust caches for axis '{axis_id}': {e}")
            continue

    return spatial_indices, direction_caches, segment_caches


def haversine_distance_rust(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate haversine distance using Rust implementation."""
    if not USE_RUST:
        raise RuntimeError("Rust map_matching not available")
    return mm.haversine_distance(lat1, lon1, lat2, lon2)


def haversine_distance_batch_rust(
    lats1: np.ndarray,
    lons1: np.ndarray,
    lats2: np.ndarray,
    lons2: np.ndarray,
) -> np.ndarray:
    """Calculate batch haversine distances using Rust implementation."""
    if not USE_RUST:
        raise RuntimeError("Rust map_matching not available")
    return mm.haversine_distance_batch(lats1, lons1, lats2, lons2)
