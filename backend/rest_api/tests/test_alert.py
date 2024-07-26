from rest_api.factories import SegmentFactory, SpeedFactory, HistoricSpeedFactory, StopFactory
from rest_api.models import AlertThreshold, Alert
from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.util.alert import TranSappSiteManager, create_alert_data
from unittest import skip
from django.utils import timezone
from rest_api.util.alert import create_alerts
from datetime import datetime, timedelta


class TestAlert(BaseTestCase):
    def setUp(self):
        self.delta = timedelta(minutes=15)
        self.start_time = timezone.localtime() - self.delta
        self.delta_between = self.start_time + timedelta(minutes=7)
        self.temporal_segment = get_temporal_segment(self.start_time)
        self.day_type = get_day_type(self.start_time)
        self.stop_codes = ["PD319"]
        AlertThreshold.objects.create(**{"threshold": 2})

    @skip("Skipped")
    def test_send_alert(self):
        site_manager = TranSappSiteManager()
        alert_data = create_alert_data(self.stop_codes)
        response = site_manager.create_alert(alert_data)

    def test_create_alerts(self):
        speed_value = 2
        historic_speed_value = 5
        threshold = AlertThreshold.objects.first().threshold
        segment = SegmentFactory(sequence=1)
        stop = StopFactory(segment=segment)
        speed = SpeedFactory(segment=segment, speed=speed_value, timestamp=self.delta_between,
                             temporal_segment=self.temporal_segment,
                             day_type=self.day_type)
        historic_speed = HistoricSpeedFactory(segment=segment, speed=historic_speed_value, timestamp=self.delta_between,
                                              temporal_segment=self.temporal_segment, day_type=self.day_type)
        create_alerts()
        alerts = Alert.objects.all()
        self.assertEqual(len(alerts), 1)


def get_temporal_segment(datetime: datetime):
    hours_in_minutes = datetime.hour * 60
    minutes = datetime.minute
    total_minutes = hours_in_minutes + minutes
    return int(total_minutes / 15)


def get_day_type(datetime: datetime):
    weekday = datetime.weekday()
    return "L" if weekday < 5 else "S" if weekday < 7 else "D"
