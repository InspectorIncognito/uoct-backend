from gtfs_rt.processors.speed import calculate_speed
from rest_api.util.alert import create_alerts, update_alerts, TranSappSiteManager


def calculate_speed_and_check_alerts():
    calculate_speed()
    site_manager = TranSappSiteManager()
    create_alerts()
    update_alerts(site_manager)
