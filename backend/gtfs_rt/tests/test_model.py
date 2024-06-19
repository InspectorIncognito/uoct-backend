from rest_api.tests.tests_views_base import BaseTestCase
from gtfs_rt.models import GPSPulse
from gtfs_rt.factories import GPSPulseFactory
from django.utils import timezone


class GPSPulsesTest(BaseTestCase):
    def setUp(self):
        self.instances = 500
        self.gps_pulse_data = {
            "route_id": "route_id",
            "direction_id": 0,
            "license_plate": "ABCD12",
            "latitude": 0.0,
            "longitude": 0.0,
            "timestamp": timezone.localtime()
        }

    def create_gps_instances(self):
        for _ in range(self.instances):
            GPSPulseFactory(**self.gps_pulse_data)

    def test_create_duplicates(self):
        self.create_gps_instances()
        all_pulses = GPSPulse.objects.all()
        self.assertEqual(all_pulses.count(), self.instances)

    def test_filter_duplicates(self):
        self.create_gps_instances()

        distinct_pulses = GPSPulse.objects.values(
            "route_id", "direction_id",
            "license_plate",
            "latitude",
            "longitude",
            "timestamp",
        ).distinct()

        self.assertEqual(distinct_pulses.count(), 1)
