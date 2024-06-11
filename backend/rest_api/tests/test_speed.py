from rest_api.util.shape import flush_shape_objects

from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.models import Shape, Segment
from geojson.geometry import LineString, MultiLineString
from geojson.feature import Feature, FeatureCollection
from shapely.geometry import LineString as shp_LineString
from processors.models.shapes import shapes_to_geojson

from rest_api.factories import ShapeFactory, SegmentFactory, SpeedFactory


class SpeedTest(BaseTestCase):
    def setUp(self):
        self.shape = ShapeFactory()
        self.segments = [SegmentFactory(shape=self.shape) for _ in range(10)]
        self.speed_value = 1

    def test_get_avg_speed_by_month(self):
        speed_data = {
            "2024-01": 3,
            "2024-02": 3,
        }
        for segment in self.segments:
            [SpeedFactory(speed=self.speed_value) for _ in range()]
