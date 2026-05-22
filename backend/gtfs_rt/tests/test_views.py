import json
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIRequestFactory

from gtfs_rt.models import GPSPulse
from gtfs_rt.views import GTFSRTViewSet
from rest_api.tests.tests_views_base import BaseTestCase


class GTFSRTViewSetTest(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

    def _create_pulse(self, timestamp, route_id="route-test"):
        return GPSPulse.objects.create(
            route_id=route_id,
            direction=0,
            license_plate="ABCD12",
            latitude=-33.45,
            longitude=-70.66,
            timestamp=timestamp,
        )

    def _call_to_geojson(self, query_string=""):
        request = self.factory.get(f"/gtfs_rt/pulses/to_geojson/{query_string}")
        return GTFSRTViewSet.as_view({"get": "to_geojson"})(request)

    def test_to_geojson_includes_new_fields(self):
        now = timezone.now()
        self._create_pulse(now)

        response = self._call_to_geojson()
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        properties = payload["features"][0]["properties"]
        self.assertIn("direction", properties)
        self.assertIn("license_plate", properties)
        self.assertIn("timestamp", properties)

    def test_to_geojson_last_minute_filters_latest_pulses(self):
        now = timezone.now()
        self._create_pulse(now - timedelta(seconds=30))
        self._create_pulse(now - timedelta(seconds=50))
        self._create_pulse(now - timedelta(minutes=2))

        response = self._call_to_geojson("?last_minute=true")
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["features"]), 2)
