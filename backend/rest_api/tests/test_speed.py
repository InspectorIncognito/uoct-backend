from rest_api.util.shape import flush_shape_objects

from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.models import Shape, Segment
from geojson.geometry import LineString, MultiLineString
from geojson.feature import Feature, FeatureCollection
from shapely.geometry import LineString as shp_LineString
from processors.models.shapes import shapes_to_geojson

from rest_api.factories import ShapeFactory, SegmentFactory, SpeedFactory, create_speed_dataset
from datetime import datetime
from processors.speed.avg_speed import get_avg_speed_by_month
from django.utils import timezone


class SpeedTest(BaseTestCase):
    def setUp(self):
        self.shape = ShapeFactory()
        self.segment = SegmentFactory(shape=self.shape, sequence=0)
        self.speed_value = 1

    def test_get_avg_speed_by_month(self):
        speed_data = {
            "2024-01": [1.0, 4.0],
            "2024-02": [1.0, 2.0],
        }
        for year_month in speed_data:
            for speed in speed_data[year_month]:
                date = datetime.strptime(year_month, "%Y-%m")
                date = timezone.make_aware(date, timezone.get_current_timezone())
                SpeedFactory(segment=self.segment, timestamp=date, speed=speed)
        january_speed = get_avg_speed_by_month(2024, 1)
        february_speed = get_avg_speed_by_month(2024, 2)

        self.assertEqual(january_speed[0]['avg_speed'], 2.5)
        self.assertEqual(february_speed[0]['avg_speed'], 1.5)
        self.assertEqual(january_speed[0]['segment'], self.segment.pk)

    def test_store_historic_speeds(self):
        dataset = create_speed_dataset()
        print(dataset)
        for shape_id in dataset:
            for segments_id in dataset[shape_id]:
                pass

