import geopandas as gpd
from django.test import SimpleTestCase
from shapely.geometry import LineString

from processors.osm.process import flatten_osm_tags, split_axis_by_direction


def feature(coords, tags):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {"type": "way", "id": 1, "tags": tags},
    }


def to_gdf(features):
    return gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": features}, crs="EPSG:4326"
    )


class TestFlattenOsmTags(SimpleTestCase):
    def test_tags_become_columns(self):
        gdf = flatten_osm_tags(
            to_gdf([feature([(0, 0), (0, 0.001)], {"oneway": "yes", "name": "X"})])
        )
        self.assertNotIn("tags", gdf.columns)
        self.assertEqual("yes", gdf["oneway"].iloc[0])
        self.assertEqual("X", gdf["name"].iloc[0])

    def test_existing_columns_are_kept(self):
        gdf = flatten_osm_tags(
            to_gdf([feature([(0, 0), (0, 0.001)], {"type": "other"})])
        )
        self.assertEqual("way", gdf["type"].iloc[0])


class TestSplitAxisOneway(SimpleTestCase):
    def expanded(self, tags):
        gdf = flatten_osm_tags(to_gdf([feature([(-70.65, -33.44), (-70.65, -33.43)], tags)]))
        groups = split_axis_by_direction(gdf)
        return [row for g in groups for _, row in g.iterrows()]

    def test_oneway_yes_is_not_duplicated(self):
        rows = self.expanded({"oneway": "yes"})
        self.assertEqual(1, len(rows))
        self.assertFalse(rows[0]["reversed"])

    def test_missing_oneway_is_two_way(self):
        rows = self.expanded({"name": "X"})
        self.assertEqual(2, len(rows))
        self.assertEqual({False, True}, {bool(r["reversed"]) for r in rows})

    def test_oneway_minus_one_is_reversed(self):
        rows = self.expanded({"oneway": "-1"})
        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]["reversed"])
        self.assertEqual(
            LineString([(-70.65, -33.43), (-70.65, -33.44)]).coords[:],
            rows[0].geometry.coords[:],
        )
