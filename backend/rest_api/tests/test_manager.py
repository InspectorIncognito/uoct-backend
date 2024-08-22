from rest_api.factories import SegmentFactory, SpeedFactory, StopFactory, AlertFactory
from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.util.alert import TranSappSiteManager
from unittest import skip
from rest_api.util.alert import update_alert_from_admin


class TestManager(BaseTestCase):
    def setUp(self):
        self.manager = TranSappSiteManager()
        self.segment = SegmentFactory()

    @skip('Skipping')
    def test_edit(self):
        segment_obj = SegmentFactory(segment_id='82342493-ae05-4ea0-910a-80459ac52447')
        StopFactory(stop_id='PD335', segment=segment_obj)

        speed_obj = SpeedFactory(segment=segment_obj)
        alert_obj = AlertFactory(segment=segment_obj, detected_speed=speed_obj)
        segment_uuid = segment_obj.segment_id

        response = self.manager.alert_lookup(segment_uuid)
        data = response["data"]
        if len(data) > 0:
            alert_data = data[0]
            update_alert_from_admin(self.manager, alert_obj, alert_data)
