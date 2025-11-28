from gtfs_rt.processors.speed import calculate_speed
from gtfs_rt.utils import get_last_temporal_range
from rest_api.util.alert import TranSappSiteManager, create_alerts, update_alerts


def calculate_speed_and_check_alerts():
    start_time, end_time = get_last_temporal_range()

    calculate_speed(
        start_time,
        end_time,
    )
    site_manager = TranSappSiteManager()
    create_alerts(start_time=start_time, end_time=end_time)
    update_alerts(site_manager, start_time=start_time, end_time=end_time)
