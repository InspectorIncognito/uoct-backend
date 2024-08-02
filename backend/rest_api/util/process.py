from gtfs_rt.processors.speed import calculate_speed
from rest_api.util.alert import create_alerts, send_alerts


def calculate_speed_and_check_alerts():
    calculate_speed()
    create_alerts()
    send_alerts()
