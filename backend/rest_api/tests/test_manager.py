import datetime

from rest_api.factories import SegmentFactory, SpeedFactory, StopFactory, AlertFactory
from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.util.alert import TranSappSiteManager, create_alert_to_admin
from unittest import skip, mock
from rest_api.util.alert import update_alert_from_admin, update_alerts
from django.utils import timezone
from gtfs_rt.utils import get_temporal_segment


@skip("This class is for debugging purposes")
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

    def test_get_all_alerts(self):
        all_site_alerts = self.site_manager.get_all_alerts()
        print(all_site_alerts)
        print(len(all_site_alerts))

    @mock.patch('rest_api.util.alert.timezone')
    def test_duplicate_alert_bug(self, mock_timezone):
        dt = datetime.timedelta(minutes=15)
        timestamp_reference = timezone.localtime()
        alert_t1 = timestamp_reference - 2 * dt
        alert_t2 = timestamp_reference - dt
        alert_1_ts = get_temporal_segment(alert_t1)
        alert_2_ts = get_temporal_segment(alert_t2)

        update_alert_t1 = timestamp_reference - dt
        update_alert_t2 = timestamp_reference
        #update_alert_t3 = timestamp_reference + dt

        segment = SegmentFactory()
        speed1 = SpeedFactory(distance=500, time_secs=1)
        speed2 = SpeedFactory(distance=500, time_secs=5)

        alert1 = AlertFactory(segment=segment, detected_speed=speed1, timestamp=alert_t1, temporal_segment=alert_1_ts)
        alert2 = AlertFactory(segment=segment, detected_speed=speed2, timestamp=alert_t2, temporal_segment=alert_2_ts)

        mock_timezone.localtime.return_value = update_alert_t1
        update_alerts(self.site_manager)

        mock_timezone.localtime.return_value = update_alert_t2
        update_alerts(self.site_manager)

        #mock_timezone.localtime.return_value = update_alert_t3
        #update_alerts(self.site_manager)

