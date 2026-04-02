"""Tests to verify Rust implementation matches Python implementation."""

import time
from typing import List, Optional, Tuple

import numpy as np
import pytest

# Test data for Santiago, Chile area
SAMPLE_SEGMENTS = [
    # segment_pk, direction, geometry [(lon, lat), ...], bearing
    (1, 0, [(-70.660, -33.450), (-70.655, -33.450)], 90.0),
    (2, 0, [(-70.655, -33.450), (-70.650, -33.450)], 90.0),
    (3, 0, [(-70.650, -33.450), (-70.645, -33.450)], 90.0),
    (4, 0, [(-70.645, -33.450), (-70.640, -33.450)], 90.0),
    (5, 0, [(-70.640, -33.450), (-70.635, -33.450)], 90.0),
    # Opposite direction
    (6, 1, [(-70.635, -33.451), (-70.640, -33.451)], 270.0),
    (7, 1, [(-70.640, -33.451), (-70.645, -33.451)], 270.0),
    (8, 1, [(-70.645, -33.451), (-70.650, -33.451)], 270.0),
    (9, 1, [(-70.650, -33.451), (-70.655, -33.451)], 270.0),
    (10, 1, [(-70.655, -33.451), (-70.660, -33.451)], 270.0),
]

# GPS trajectory along the road
SAMPLE_GPS_TRAJECTORY = [
    (-70.658, -33.4501),  # Start near segment 1
    (-70.653, -33.4501),  # Near segment 2
    (-70.648, -33.4501),  # Near segment 3
    (-70.643, -33.4501),  # Near segment 4
    (-70.638, -33.4501),  # Near segment 5
]

SAMPLE_GPS_BEARINGS = [90.0, 90.0, 90.0, 90.0, 90.0]


class TestHaversineDistance:
    """Test haversine distance calculations."""

    def test_same_point(self):
        """Distance between same point should be 0."""
        try:
            from map_matching import haversine_distance

            dist = haversine_distance(-33.45, -70.65, -33.45, -70.65)
            assert dist < 1e-6
        except ImportError:
            pytest.skip("Rust map_matching not installed")

    def test_known_distance(self):
        """Test against known distance between two cities."""
        try:
            from map_matching import haversine_distance

            # Santiago to Valparaiso: ~98km
            dist = haversine_distance(-33.4489, -70.6693, -33.0472, -71.6127)
            assert 95_000 < dist < 105_000
        except ImportError:
            pytest.skip("Rust map_matching not installed")

    def test_matches_python(self):
        """Verify Rust haversine matches Python implementation."""
        try:
            from map_matching import haversine_distance as rust_haversine
        except ImportError:
            pytest.skip("Rust map_matching not installed")

        # Python implementation
        def python_haversine(lat1, lon1, lat2, lon2):
            R = 6_371_000
            lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (
                np.sin(dlat / 2) ** 2
                + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
            )
            c = 2 * np.arcsin(np.sqrt(a))
            return R * c

        # Test various points
        test_cases = [
            (-33.45, -70.65, -33.46, -70.66),
            (0.0, 0.0, 1.0, 1.0),
            (-90.0, 0.0, 90.0, 0.0),
            (45.0, 90.0, -45.0, -90.0),
        ]

        for lat1, lon1, lat2, lon2 in test_cases:
            rust_dist = rust_haversine(lat1, lon1, lat2, lon2)
            python_dist = python_haversine(lat1, lon1, lat2, lon2)
            assert abs(rust_dist - python_dist) < 1.0, (
                f"Mismatch for ({lat1}, {lon1}) -> ({lat2}, {lon2})"
            )


class TestHaversineBatch:
    """Test batch haversine distance calculations."""

    def test_batch_matches_single(self):
        """Batch results should match individual calculations."""
        try:
            from map_matching import haversine_distance, haversine_distance_batch
        except ImportError:
            pytest.skip("Rust map_matching not installed")

        n = 100
        lats1 = np.random.uniform(-90, 90, n)
        lons1 = np.random.uniform(-180, 180, n)
        lats2 = np.random.uniform(-90, 90, n)
        lons2 = np.random.uniform(-180, 180, n)

        batch_results = haversine_distance_batch(lats1, lons1, lats2, lons2)

        for i in range(n):
            single_result = haversine_distance(lats1[i], lons1[i], lats2[i], lons2[i])
            assert abs(batch_results[i] - single_result) < 0.01


class TestSpatialIndex:
    """Test spatial index functionality."""

    def test_creation(self):
        """Test spatial index creation."""
        try:
            from map_matching import SpatialIndex
        except ImportError:
            pytest.skip("Rust map_matching not installed")

        segment_pks = [s[0] for s in SAMPLE_SEGMENTS]
        geometries = [s[2] for s in SAMPLE_SEGMENTS]

        index = SpatialIndex(
            segment_pks=segment_pks,
            geometries=geometries,
            interval=20.0,
            is_geographic=True,
        )

        assert index.len() > 0

    def test_query_near_segment(self):
        """Test querying segments near a point."""
        try:
            from map_matching import SpatialIndex
        except ImportError:
            pytest.skip("Rust map_matching not installed")

        segment_pks = [s[0] for s in SAMPLE_SEGMENTS]
        geometries = [s[2] for s in SAMPLE_SEGMENTS]

        index = SpatialIndex(
            segment_pks=segment_pks,
            geometries=geometries,
            interval=20.0,
            is_geographic=True,
        )

        # Query near segment 1
        results = index.query(-70.657, -33.450, 500.0)
        assert 1 in results or 2 in results


class TestViterbi:
    """Test Viterbi map matching algorithm."""

    def test_simple_trajectory(self):
        """Test matching a simple trajectory."""
        try:
            from map_matching import (
                SpatialIndex,
                DirectionCache,
                SegmentCache,
                viterbi,
            )
        except ImportError:
            pytest.skip("Rust map_matching not installed")

        segment_pks = [s[0] for s in SAMPLE_SEGMENTS]
        directions = [s[1] for s in SAMPLE_SEGMENTS]
        geometries = [s[2] for s in SAMPLE_SEGMENTS]
        bearings = [s[3] for s in SAMPLE_SEGMENTS]

        spatial_index = SpatialIndex(
            segment_pks=segment_pks,
            geometries=geometries,
            interval=20.0,
            is_geographic=True,
        )

        direction_cache = DirectionCache(
            segment_pks=segment_pks,
            directions=directions,
            geometries=geometries,
        )

        segment_cache = SegmentCache(
            segment_pks=segment_pks,
            geometries=geometries,
            bearings=[b if b is not None else None for b in bearings],
        )

        gps_lons = [p[0] for p in SAMPLE_GPS_TRAJECTORY]
        gps_lats = [p[1] for p in SAMPLE_GPS_TRAJECTORY]

        matched_segments, valid_indices, projected_points = viterbi(
            gps_lons=gps_lons,
            gps_lats=gps_lats,
            spatial_index=spatial_index,
            direction_cache=direction_cache,
            segment_cache=segment_cache,
            max_distance=200.0,
            sigma=25.0,
            beta=40.0,
            min_candidates=1,
        )

        # Should have some matches
        assert len(valid_indices) > 0

        # Matched segments should be in order (1-5)
        matched = [s for s in matched_segments if s is not None]
        assert len(matched) > 0

        # All matched should be direction 0 (segments 1-5)
        for seg in matched:
            assert seg in [1, 2, 3, 4, 5], f"Unexpected segment {seg}"


class TestPerformance:
    """Performance benchmarks."""

    def test_haversine_performance(self):
        """Benchmark haversine distance calculations."""
        try:
            from map_matching import haversine_distance, haversine_distance_batch
        except ImportError:
            pytest.skip("Rust map_matching not installed")

        # Single point benchmark
        n_iterations = 10_000
        start = time.perf_counter()
        for _ in range(n_iterations):
            haversine_distance(-33.45, -70.65, -33.46, -70.66)
        single_time = time.perf_counter() - start
        print(f"\nSingle haversine: {single_time / n_iterations * 1e6:.2f} μs/call")

        # Batch benchmark
        n_points = 10_000
        lats1 = np.random.uniform(-90, 90, n_points)
        lons1 = np.random.uniform(-180, 180, n_points)
        lats2 = np.random.uniform(-90, 90, n_points)
        lons2 = np.random.uniform(-180, 180, n_points)

        start = time.perf_counter()
        haversine_distance_batch(lats1, lons1, lats2, lons2)
        batch_time = time.perf_counter() - start
        print(f"Batch haversine ({n_points} points): {batch_time * 1000:.2f} ms")

    def test_viterbi_performance(self):
        """Benchmark Viterbi algorithm."""
        try:
            from map_matching import (
                SpatialIndex,
                DirectionCache,
                SegmentCache,
                viterbi,
            )
        except ImportError:
            pytest.skip("Rust map_matching not installed")

        # Create larger test data
        n_segments = 100
        segment_pks = list(range(n_segments))
        directions = [i % 2 for i in range(n_segments)]
        geometries = [
            [(-70.7 + i * 0.001, -33.45), (-70.7 + i * 0.001 + 0.0009, -33.45)]
            for i in range(n_segments)
        ]
        bearings = [90.0 if d == 0 else 270.0 for d in directions]

        spatial_index = SpatialIndex(
            segment_pks=segment_pks,
            geometries=geometries,
            interval=20.0,
            is_geographic=True,
        )

        direction_cache = DirectionCache(
            segment_pks=segment_pks,
            directions=directions,
            geometries=geometries,
        )

        segment_cache = SegmentCache(
            segment_pks=segment_pks,
            geometries=geometries,
            bearings=bearings,
        )

        # Generate trajectory
        n_gps_points = 100
        gps_lons = [-70.698 + i * 0.001 for i in range(n_gps_points)]
        gps_lats = [-33.4501] * n_gps_points

        # Warmup
        viterbi(
            gps_lons=gps_lons,
            gps_lats=gps_lats,
            spatial_index=spatial_index,
            direction_cache=direction_cache,
            segment_cache=segment_cache,
            max_distance=200.0,
            sigma=25.0,
            beta=40.0,
            min_candidates=1,
        )

        # Benchmark
        n_iterations = 100
        start = time.perf_counter()
        for _ in range(n_iterations):
            viterbi(
                gps_lons=gps_lons,
                gps_lats=gps_lats,
                spatial_index=spatial_index,
                direction_cache=direction_cache,
                segment_cache=segment_cache,
                max_distance=200.0,
                sigma=25.0,
                beta=40.0,
                min_candidates=1,
            )
        elapsed = time.perf_counter() - start

        print(f"\nViterbi ({n_gps_points} GPS points, {n_segments} segments):")
        print(f"  Total: {elapsed * 1000:.2f} ms for {n_iterations} iterations")
        print(f"  Per call: {elapsed / n_iterations * 1000:.2f} ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
