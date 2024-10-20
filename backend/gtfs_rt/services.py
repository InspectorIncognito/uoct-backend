from django.utils import timezone
from datetime import datetime, timedelta

from gtfs_rt.models import GPSPulse
from gtfs_rt.utils import get_temporal_segment, get_temporal_range


def get_gps_data_from_last_15_minutes():
    delta_time = timedelta(minutes=15)
    now = timezone.localtime()
    previous_15_minutes = now - delta_time
    previous_temporal_segment = get_temporal_segment(previous_15_minutes)
    start_date, end_date = get_temporal_range(previous_temporal_segment)
    queryset = GPSPulse.objects.filter(timestamp__gte=start_date, timestamp__lte=end_date).values(
        "route_id",
        "direction_id",
        "license_plate",
        "latitude",
        "longitude",
        "timestamp",
    ).distinct()
    print("START TIME:", start_date)
    print("END TIME:", end_date)
    print("TOTAL GPS:", len(queryset))
    return queryset
