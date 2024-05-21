import datetime
from gtfs_rt.models import GPSPulse


def calculate_speed(start_date: datetime.datetime | None, end_date: datetime.datetime | None):
    if start_date and end_date:
        gtfs_rt_query = GPSPulse.objects.filter()