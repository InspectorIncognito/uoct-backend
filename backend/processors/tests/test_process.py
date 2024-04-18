from rest_api.tests.tests_views_base import BaseTestCase
import geopandas as gpd
from geojson.feature import Feature, FeatureCollection
from geojson.geometry import LineString
from processors.osm.process import split_geojson_by_shape


class TestProcess(BaseTestCase):
    def setUp(self):
        super(TestProcess, self).setUp()
        self.gdf_data = gpd.GeoDataFrame.from_features(
            features=[
                Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)])),
                Feature(geometry=LineString(coordinates=[(1, 0), (1, 1), (1, 2)])),
            ]
        )

    def test_split_geojson_by_shape(self):
        actual = split_geojson_by_shape(self.gdf_data)
        expected = [
            gpd.GeoDataFrame.from_features(
                features=[
                    Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)]))
                ]
            ),
            gpd.GeoDataFrame.from_features(
                features=[
                    Feature(geometry=LineString(coordinates=[(1, 0), (1, 1), (1, 2)]))
                ]
            )
        ]
        self.assertEqual(actual, expected)
