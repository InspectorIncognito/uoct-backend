import random

from django.db.models import Sum
from django.utils import timezone
from processors.speed.avg_speed import get_month_commercial_speed
from rest_api.factories import SpeedFactory, SegmentFactory
from rest_api.models import HistoricSpeed, Speed
from rest_api.tests.tests_views_base import BaseTestCase


class HistoricSpeedTest(BaseTestCase):
    def setUp(self):
        day_minutes = 1440
        temporal_segment_duration = 15
        self.segments = [SegmentFactory(), SegmentFactory()]
        self.day_types = ['L', 'S', 'D']
        self.temporal_segments = int(day_minutes / temporal_segment_duration)

    def test_calculate_monthly_speed(self):
        for segment in self.segments:
            for day_type in self.day_types:
                for temporal_segment in range(self.temporal_segments):
                    for day in range(4):
                        distance = random.randint(10, 100)
                        time_secs = random.randint(1, 5)
                        SpeedFactory(segment=segment, temporal_segment=temporal_segment, day_type=day_type,
                                     distance=distance, time_secs=time_secs)

        today = timezone.localtime()
        this_month = today.month
        this_year = today.year
        get_month_commercial_speed(year=this_year, month=this_month)

        historic_speeds = HistoricSpeed.objects.filter(timestamp__year=this_year, timestamp__month=this_month)
        expected_historic_speed_records = len(self.segments) * len(self.day_types) * self.temporal_segments
        self.assertEqual(historic_speeds.count(), expected_historic_speed_records)

        for avg_speed in historic_speeds:
            segment = avg_speed.segment
            temporal_segment = avg_speed.temporal_segment
            day_type = avg_speed.day_type
            expected_speed = avg_speed.speed
            speeds = Speed.objects.filter(timestamp__year=this_year, timestamp__month=this_month,
                                          segment=segment, temporal_segment=temporal_segment, day_type=day_type)
            total_distance = speeds.aggregate(Sum('distance'))['distance__sum']
            total_time = speeds.aggregate(Sum('time_secs'))['time_secs__sum']
            actual_speed = round(3.6 * total_distance / total_time, 2)
            self.assertAlmostEqual(actual_speed, expected_speed, 1)
