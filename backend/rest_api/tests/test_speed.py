from rest_api.models import HistoricSpeed
from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.factories import ShapeFactory, SegmentFactory, SpeedFactory, create_speed_dataset
from datetime import datetime
from processors.speed.avg_speed import get_avg_speed_by_month, save_historic_avg_speed
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
        this_year = timezone.now().year
        dataset = create_speed_dataset()
        for month in range(1, 13):
            creation_datetime = datetime(this_year, month, 1)
            creation_datetime = timezone.make_aware(creation_datetime, timezone.get_current_timezone())
            avg_speeds = get_avg_speed_by_month(this_year, month)
            save_historic_avg_speed(avg_speeds, creation_datetime)

        for segment_id in dataset["segments"]:
            for month_data in dataset["segments"][segment_id]:
                month = month_data["date"]
                expected_speed = month_data["expected_speed"]
                creation_datetime = datetime(this_year, month, 1)
                creation_datetime = timezone.make_aware(creation_datetime, timezone.get_current_timezone())
                historic_speed = HistoricSpeed.objects.get(segment__pk=segment_id, timestamp=creation_datetime)
                self.assertEqual(historic_speed.speed, expected_speed)

