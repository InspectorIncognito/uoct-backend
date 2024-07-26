from gtfs_rt.processors.speed import calculate_speed
from rest_api.util.alert import send_alerts, create_alerts
from django.utils import timezone


def calculate_speed_and_check_alerts():
    now = timezone.localtime()
    calculate_speed(now)
    create_alerts()
    send_alerts()
