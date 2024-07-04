from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.util.alert import TranSappSiteManager, create_alert_data
from unittest import skip


class TestAlert(BaseTestCase):
    def setUp(self):
        self.stop_codes = ["PD319"]

    @skip("Skipped")
    def test_send_alert(self):
        site_manager = TranSappSiteManager()
        alert_data = create_alert_data(self.stop_codes)
        response = site_manager.create_alert(alert_data)
