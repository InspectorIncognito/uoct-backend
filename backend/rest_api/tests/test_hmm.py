import geopandas as gpd
from django.test import SimpleTestCase
from rest_api.util.hmm.hmm import (
    build_segment_cache,
    build_spatial_index,
    haversine_distance,
    precompute_direction_cache,
    shortest_path_distance,
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
