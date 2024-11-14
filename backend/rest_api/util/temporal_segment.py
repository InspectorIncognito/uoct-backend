from datetime import timedelta

from django.utils import timezone

from gtfs_rt.utils import get_temporal_segment, get_temporal_range


def get_last_temporal_segment_data():
    delta_time = timedelta(minutes=15)
    now = timezone.localtime()
    previous_15_minutes = now - delta_time
    previous_temporal_segment = get_temporal_segment(previous_15_minutes)
    start_date, _ = get_temporal_range(previous_temporal_segment)
    weekday = start_date.weekday()
    day_type = 'L' if weekday < 5 else 'S' if weekday == 5 else 'D'
    date = start_date.date()
    return date, day_type, previous_temporal_segment


def get_last_temporal_segment_dates():
    delta_time = timedelta(minutes=15)
    now = timezone.localtime()
    previous_15_minutes = now - delta_time
    previous_temporal_segment = get_temporal_segment(previous_15_minutes)
    start_date, end_date = get_temporal_range(previous_temporal_segment)
    return start_date, end_date
