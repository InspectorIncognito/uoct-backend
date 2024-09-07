from rest_api.factories import SegmentFactory, SpeedFactory, StopFactory, AlertFactory
from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.util.alert import TranSappSiteManager, create_alert_to_admin
from unittest import skip
from rest_api.util.alert import update_alert_from_admin


# @skip("This class is for debugging purposes")
class TestManager(BaseTestCase):
    def setUp(self):
        self.site_manager = TranSappSiteManager()
        self.segment_id = "72e85d02-6cec-4f41-88f3-94294c3081db"
        self.segment = SegmentFactory(segment_id=self.segment_id)
        self.stop = StopFactory(stop_id='PD335')
        self.speed = SpeedFactory(segment=self.segment)
        self.alert = AlertFactory(segment=self.segment, detected_speed=self.speed)

    def test_create_alert(self):
        create_response = create_alert_to_admin(self.site_manager, self.alert)
        print(create_response)

    def test_alert_lookup(self):
        site_alert = self.site_manager.alert_lookup(self.segment_id)
        print(site_alert)

    def test_update_alert(self):
        lookup_response = self.site_manager.alert_lookup(self.segment_id)
        alert_data = lookup_response["data"][0]

        update_response = update_alert_from_admin(self.site_manager, self.alert, alert_data)
        print(update_response)

    def test_disable_alert(self):
        lookup_response = self.site_manager.alert_lookup(self.segment_id)
        alert_data = lookup_response["data"][0]

        update_response = update_alert_from_admin(self.site_manager, self.alert, alert_data, activated=False)
        print(update_response)

    def test_delete_alert(self):
        lookup_response = self.site_manager.alert_lookup(self.segment_id)
        alert_data = lookup_response["data"][0]
        alert_public_id = alert_data["public_id"]
        delete_response = self.site_manager.alert_delete(alert_public_id)
        print(delete_response)

    def test_create_bulk(self):
        alert_objs = AlertFactory.create_batch(11)
        for alert in alert_objs:
            create_response = create_alert_to_admin(self.site_manager, alert)
            print(create_response)

    def test_delete_all_alerts(self):
        self.site_manager.delete_all_alerts()

    def test_alert_pagination(self):
        alert_objs = AlertFactory.create_batch(11)
        for alert in alert_objs:
            create_response = create_alert_to_admin(self.site_manager, alert)
            print(create_response)

        lookup_response = self.site_manager.get_all_alerts()
        alerts = lookup_response["data"]
        print(lookup_response)
