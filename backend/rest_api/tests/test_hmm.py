import math

import geopandas as gpd
from django.test import SimpleTestCase
from rest_api.util.hmm.hmm import (
    build_segment_cache,
    build_spatial_index,
    haversine_distance,
    precompute_direction_cache,
    shortest_path_distance,
    transition_prob_log,
    viterbi,
)
from shapely.geometry import LineString, Point

LAT = -33.45
LON_A, LON_B, LON_C = -70.660, -70.656, -70.652
# Same values GridManager passes to viterbi by default
HMM_PARAMS = {"max_distance": 40, "sigma": 25, "beta": 40}


def make_gdf(rows, crs="EPSG:4326"):
    """Build a segments GeoDataFrame from (segment_pk, direction, sequence, coords)."""
    return gpd.GeoDataFrame(
        {
            "segment_pk": [row[0] for row in rows],
            "direction": [row[1] for row in rows],
            "sequence": [row[2] for row in rows],
        },
        geometry=[LineString(row[3]) for row in rows],
        crs=crs,
    )


def geodesic(p1, p2):
    return haversine_distance(p1.y, p1.x, p2.y, p2.x)


class ShortestPathDistanceTest(SimpleTestCase):
    def setUp(self):
        self.gdf = make_gdf(
            [
                (1, 0, 0, [(LON_A, LAT), (LON_B, LAT)]),
                (2, 0, 1, [(LON_B, LAT), (LON_C, LAT)]),
            ]
        )
        self.cache = precompute_direction_cache(self.gdf)
        self.p1 = Point(-70.658, LAT)
        self.p2 = Point(-70.654, LAT)

    def assert_close_to_geodesic(self, distance, p1, p2):
        expected = geodesic(p1, p2)
        self.assertAlmostEqual(distance, expected, delta=expected * 0.005)

    def test_cross_segment_distance_is_in_meters(self):
        distance = shortest_path_distance(self.p1, self.p2, 1, 2, self.cache)
        self.assert_close_to_geodesic(distance, self.p1, self.p2)

    def test_cross_segment_matches_same_segment_distance(self):
        cross = shortest_path_distance(self.p1, self.p2, 1, 2, self.cache)
        same = shortest_path_distance(self.p1, self.p2, 1, 1, self.cache)
        self.assertAlmostEqual(cross, same, delta=same * 0.005)

    def test_north_south_axis_is_in_meters(self):
        cache = precompute_direction_cache(
            make_gdf(
                [
                    (1, 0, 0, [(LON_A, -33.450), (LON_A, -33.446)]),
                    (2, 0, 1, [(LON_A, -33.446), (LON_A, -33.442)]),
                ]
            )
        )
        p1, p2 = Point(LON_A, -33.448), Point(LON_A, -33.444)
        distance = shortest_path_distance(p1, p2, 1, 2, cache)
        self.assert_close_to_geodesic(distance, p1, p2)

    def test_distance_is_symmetric(self):
        forward = shortest_path_distance(self.p1, self.p2, 1, 2, self.cache)
        backward = shortest_path_distance(self.p2, self.p1, 2, 1, self.cache)
        self.assertAlmostEqual(forward, backward)

    def test_distance_follows_the_route_not_the_straight_line(self):
        # L-shaped route: each leg ~371 m east and ~445 m north
        corner = (LON_B, LAT)
        cache = precompute_direction_cache(
            make_gdf(
                [
                    (1, 0, 0, [(LON_A, LAT), corner]),
                    (2, 0, 1, [corner, (LON_B, LAT + 0.004)]),
                ]
            )
        )
        start = Point(LON_A, LAT)
        end = Point(LON_B, LAT + 0.004)
        legs = geodesic(start, Point(corner)) + geodesic(Point(corner), end)
        distance = shortest_path_distance(start, end, 1, 2, cache)
        self.assertAlmostEqual(distance, legs, delta=legs * 0.005)
        self.assertGreater(distance, geodesic(start, end) * 1.2)

    def test_segments_are_chained_by_sequence_not_frame_order(self):
        lon_d = -70.648
        cache = precompute_direction_cache(
            make_gdf(
                [
                    (3, 0, 2, [(LON_C, LAT), (lon_d, LAT)]),
                    (1, 0, 0, [(LON_A, LAT), (LON_B, LAT)]),
                    (2, 0, 1, [(LON_B, LAT), (LON_C, LAT)]),
                ]
            )
        )
        p1, p3 = Point(-70.658, LAT), Point(-70.650, LAT)
        distance = shortest_path_distance(p1, p3, 1, 3, cache)
        self.assert_close_to_geodesic(distance, p1, p3)

    def test_retraced_street_counts_both_passes(self):
        # Route goes east and returns along the same street
        cache = precompute_direction_cache(
            make_gdf(
                [
                    (1, 0, 0, [(LON_A, LAT), (LON_B, LAT)]),
                    (2, 0, 1, [(LON_B, LAT), (LON_A, LAT)]),
                ]
            )
        )
        p1, p2 = Point(-70.659, LAT), Point(-70.657, LAT)
        leg = geodesic(Point(LON_A, LAT), Point(LON_B, LAT))
        distance = shortest_path_distance(p1, p2, 1, 2, cache)
        self.assertAlmostEqual(distance, leg, delta=leg * 0.005)

    def test_projected_crs_keeps_its_units(self):
        cache = precompute_direction_cache(
            make_gdf(
                [
                    (1, 0, 0, [(0, 0), (100, 0)]),
                    (2, 0, 1, [(100, 0), (200, 0)]),
                ],
                crs="EPSG:32719",
            )
        )
        distance = shortest_path_distance(Point(50, 0), Point(150, 0), 1, 2, cache)
        self.assertAlmostEqual(distance, 100.0)

    def test_missing_direction_column_infers_groups(self):
        gdf = self.gdf.drop(columns=["direction"])
        with self.assertWarns(UserWarning):
            cache = precompute_direction_cache(gdf)
        distance = shortest_path_distance(self.p1, self.p2, 1, 2, cache)
        self.assert_close_to_geodesic(distance, self.p1, self.p2)

    def test_opposite_directions_fall_back_to_geodesic(self):
        cache = precompute_direction_cache(
            make_gdf(
                [
                    (1, 0, 0, [(LON_A, LAT), (LON_B, LAT)]),
                    (2, 1, 0, [(LON_C, LAT), (LON_B, LAT)]),
                ]
            )
        )
        distance = shortest_path_distance(self.p1, self.p2, 1, 2, cache)
        self.assertAlmostEqual(distance, geodesic(self.p1, self.p2))

    def test_unknown_segment_falls_back_to_geodesic(self):
        distance = shortest_path_distance(self.p1, self.p2, 1, 99, self.cache)
        self.assertAlmostEqual(distance, geodesic(self.p1, self.p2))


class TransitionProbabilityTest(SimpleTestCase):
    def test_next_segment_is_as_likely_as_same_segment(self):
        cache = precompute_direction_cache(
            make_gdf(
                [
                    (1, 0, 0, [(LON_A, LAT), (LON_B, LAT)]),
                    (2, 0, 1, [(LON_B, LAT), (LON_C, LAT)]),
                ]
            )
        )
        p1, p2 = Point(-70.658, LAT), Point(-70.654, LAT)
        beta = HMM_PARAMS["beta"]
        cross = transition_prob_log(p1, p2, 1, 2, p1, p2, beta, cache)
        self.assertAlmostEqual(cross, -math.log(beta), delta=0.1)


class ViterbiAcrossSegmentsTest(SimpleTestCase):
    def setUp(self):
        # Opposite carriageway ~17 m north, so it is also a candidate for every pulse
        north = LAT + 0.00015
        gdf = make_gdf(
            [
                (1, 0, 0, [(LON_A, LAT), (LON_B, LAT)]),
                (2, 0, 1, [(LON_B, LAT), (LON_C, LAT)]),
                (3, 1, 0, [(LON_C, north), (LON_B, north)]),
                (4, 1, 1, [(LON_B, north), (LON_A, north)]),
            ]
        )
        self.caches = (
            precompute_direction_cache(gdf),
            build_spatial_index(gdf),
            build_segment_cache(gdf),
        )

    def test_stays_on_carriageway_when_crossing_segments(self):
        trajectory = [Point(-70.6585, LAT + 1e-5), Point(-70.6545, LAT + 1e-5)]
        matched, valid, _ = viterbi(trajectory, *self.caches, **HMM_PARAMS)
        self.assertEqual(valid, [0, 1])
        self.assertEqual([int(seg) for seg in matched], [1, 2])
