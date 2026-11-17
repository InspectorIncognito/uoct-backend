from decouple import config
from gtfs_rt.processors.speed import calculate_speed
from gtfs_rt.utils import get_last_temporal_range
from rest_api.util.alert import TranSappSiteManager, create_alerts, update_alerts


def calculate_speed_and_check_alerts():
    start_time, end_time = get_last_temporal_range()

    calculate_speed(
        start_time,
        end_time,
    )
    create_alerts(start_time=start_time, end_time=end_time)
    # TRANSAPP_SYNC_ENABLED=False keeps alerts local (no login or changes on TranSapp admin).
    if config("TRANSAPP_SYNC_ENABLED", default=True, cast=bool):
        site_manager = TranSappSiteManager()
        update_alerts(site_manager, start_time=start_time, end_time=end_time)
    else:
        print("TRANSAPP_SYNC_ENABLED=False: alerts not sent to TranSapp.")
