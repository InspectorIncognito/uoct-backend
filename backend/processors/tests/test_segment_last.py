import geopandas as gpd
from django.test import SimpleTestCase
from haversine import Unit, haversine
from shapely.geometry import LineString

from processors.osm.process import line_length_in_meters, segment_shape_by_distance

LON = -70.65
LAT = -33.44
METERS_PER_DEG_LAT = haversine((LAT, LON), (LAT + 1, LON), unit=Unit.METERS)


def north_line(length_m: float) -> gpd.GeoDataFrame:
    end_lat = LAT + length_m / METERS_PER_DEG_LAT
    return gpd.GeoDataFrame(
        geometry=[LineString([(LON, LAT), (LON, end_lat)])], crs="EPSG:4326"
    )


def segment_lengths(length_m: float, threshold: float = 200):
    gdf = segment_shape_by_distance(
        north_line(length_m), threshold, distance_algorithm="haversine"
    )
    return [line_length_in_meters(g, "haversine") for g in gdf.geometry]


class TestLastSegmentMerge(SimpleTestCase):
    def test_short_last_segment_merges_with_previous(self):
        # 200 + 200 + 200 + 100: 100 < 0.75 * 200, so it joins the third segment.
        lengths = segment_lengths(700)
        self.assertEqual(3, len(lengths))
        for length in lengths[:-1]:
            self.assertAlmostEqual(200, length, delta=1)
        self.assertAlmostEqual(300, lengths[-1], delta=1)

    def test_long_last_segment_stays_alone(self):
        # 200 + 200 + 200 + 170: 170 >= 0.75 * 200, so it stays as its own segment.
        lengths = segment_lengths(770)
        self.assertEqual(4, len(lengths))
        self.assertAlmostEqual(170, lengths[-1], delta=1)

    def test_exact_multiple_has_no_leftover(self):
        lengths = segment_lengths(600)
        self.assertEqual(3, len(lengths))
        self.assertAlmostEqual(200, lengths[-1], delta=1)
