from rest_api.factories import SegmentFactory, SpeedFactory, StopFactory, AlertFactory
from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.util.alert import TranSappSiteManager, create_alert_to_admin
from unittest import skip
from rest_api.util.alert import update_alert_from_admin


#@skip("Debug purposes")
class TestManager(BaseTestCase):
    def setUp(self):
        self.site_manager = TranSappSiteManager()
        self.segment = SegmentFactory(segment_id="72e85d02-6cec-4f41-88f3-94294c3081db")
        self.stop = StopFactory(stop_id='PD335')
        self.speed = SpeedFactory()
        self.alert = AlertFactory(segment=self.segment, detected_speed=self.speed)

    def test_edit(self):
        segment_obj = SegmentFactory(segment_id='9dcdd5fb-13e1-4f1e-8862-c7c59084fd40')
        StopFactory(stop_id='PD335', segment=segment_obj)

        speed_obj = SpeedFactory(segment=segment_obj)
        alert_obj = AlertFactory(segment=segment_obj, detected_speed=speed_obj)
        segment_uuid = segment_obj.segment_id

        response = self.site_manager.alert_lookup(segment_uuid)
        data = response["data"]
        if len(data) > 0:
            alert_data = data[0]
            update_alert_from_admin(self.site_manager, alert_obj, alert_data)

    def test_create_alert(self):
        create_response = create_alert_to_admin(self.site_manager, self.alert)
        print(create_response)

    def test_alert_lookup(self):
        pass

    def test_update_alert(self):
        pass

    def test_delete_alert(self):
        pass
