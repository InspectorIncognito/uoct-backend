from gtfs_rt.processors.speed import calculate_speed
from rest_api.util.alert import send_alerts


def calculate_speed_and_check_alerts():
    calculate_speed()
    send_alerts()
