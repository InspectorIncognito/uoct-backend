import datetime

from config.paths import FIXTURE_PATH
from processors.osm.process import segment_shape_by_distance, save_all_segmented_shapes_to_db
from rest_api.factories import SegmentFactory, SpeedFactory, StopFactory, AlertFactory
from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.util.alert import TranSappSiteManager, create_alert_to_admin
from unittest import skip, mock
from rest_api.util.alert import update_alert_from_admin, update_alerts
from django.utils import timezone
from gtfs_rt.utils import get_temporal_segment
from rest_api.util.shape import ShapeManager
from velocity.grid import GridManager
import geopandas as gpd


class TestShapeManager(BaseTestCase):
    def setUp(self):
        distance_threshold = 500.0
        gdf = gpd.read_file(FIXTURE_PATH)
        segmented_shapes = []
        for idx, feature in gdf.iterrows():
            merged = feature.geometry
            segmented = segment_shape_by_distance(merged, distance_threshold, distance_algorithm='haversine')
            segmented_shapes.append(segmented)
        save_all_segmented_shapes_to_db(segmented_shapes)

    def test_get_buffered_shape(self):
        sm = ShapeManager()
        gdf = sm.get_buffered_shape()
        print(gdf)