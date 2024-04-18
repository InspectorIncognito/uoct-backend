from rest_api.tests.tests_views_base import BaseTestCase
import geopandas as gpd
from geojson.feature import Feature, FeatureCollection
from geojson.geometry import LineString
from processors.osm.process import split_geojson_by_shape
import pandas as pd


class TestProcess(BaseTestCase):
    def setUp(self):
        super(TestProcess, self).setUp()
        self.gdf_data_no_touches = gpd.GeoDataFrame([
            Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)])),
            Feature(geometry=LineString(coordinates=[(1, 0), (1, 1), (1, 2)])),
        ])
        self.gdf_data_touches = gpd.GeoDataFrame([
            Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)])),
            Feature(geometry=LineString(coordinates=[(0, 2), (0, 3), (0, 4)])),
        ])
        self.gdf_data_mixed = gpd.GeoDataFrame([
            Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)])),
            Feature(geometry=LineString(coordinates=[(0, 2), (0, 3), (0, 4)])),
            Feature(geometry=LineString(coordinates=[(0, 5), (0, 6), (0, 7)]))
        ])

    def test_split_geojson_by_shape_no_touches(self):
        actual = split_geojson_by_shape(self.gdf_data_no_touches)
        expected = [
            gpd.GeoDataFrame.from_features(
                features=[Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)]))]),
            gpd.GeoDataFrame.from_features(
                features=[Feature(geometry=LineString(coordinates=[(1, 0), (1, 1), (1, 2)]))])
        ]
        actual = gpd.GeoDataFrame(pd.concat(actual, ignore_index=True))
        expected = gpd.GeoDataFrame(pd.concat(expected, ignore_index=True))
        self.assertTrue(actual.equals(expected))

    def test_split_geojson_by_shape_touches(self):
        actual = split_geojson_by_shape(self.gdf_data_touches)
        expected = [
            gpd.GeoDataFrame.from_features(
                features=[
                    Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)])),
                    Feature(geometry=LineString(coordinates=[(0, 2), (0, 3), (0, 4)])),
                ]
            )
        ]
        actual = gpd.GeoDataFrame(pd.concat(actual, ignore_index=True))
        expected = gpd.GeoDataFrame(pd.concat(expected, ignore_index=True))
        self.assertTrue(actual.equals(expected))

    def test_split_geojson_by_shape_mixed(self):
        actual = split_geojson_by_shape(self.gdf_data_mixed)
        expected = [
            gpd.GeoDataFrame.from_features(
                features=[
                    Feature(geometry=LineString(coordinates=[(0, 0), (0, 1), (0, 2)])),
                    Feature(geometry=LineString(coordinates=[(0, 2), (0, 3), (0, 4)]))
                ]
            ),
            gpd.GeoDataFrame.from_features(
                features=[
                    Feature(geometry=LineString(coordinates=[(0, 5), (0, 6), (0, 7)]))
                ]
            )
        ]
        actual = gpd.GeoDataFrame(pd.concat(actual, ignore_index=True))
        expected = gpd.GeoDataFrame(pd.concat(expected, ignore_index=True))
        self.assertTrue(actual.equals(expected))
