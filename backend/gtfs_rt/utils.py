from typing import List

import numpy as np
from datetime import datetime, timedelta
from django.utils import timezone
from gtfs_rt.models import GPSPulse

MAD_CONST = 1.4826


def median_absolute_deviation(x):
    median = np.median(x)
    abs_deviations = np.abs(x - median)
    return np.median(abs_deviations) * MAD_CONST


def speed_threshold(x):
    median = np.median(x)
    abs_deviations = np.abs(x - median)
    MAD = np.median(abs_deviations) * MAD_CONST
    return (x - median) / MAD


def get_temporal_segment(date: datetime, interval: int = 15):
    day_minutes = date.hour * 60 + date.minute
    return day_minutes // interval


def get_temporal_range(temporal_segment):
    start_time_minutes = temporal_segment * 15
    hours = start_time_minutes // 60
    minutes = start_time_minutes % 60

    start_time = timezone.localtime().replace(hour=hours, minute=minutes, second=0, microsecond=0)
    end_time = start_time + timedelta(minutes=15)
    return start_time, end_time


def get_day_type(dt: datetime):
    if dt.tzinfo is None:
        raise ValueError("datetime instance must have a tzinfo")
    converted_timestamp = timezone.localtime(dt)
    weekday = converted_timestamp.weekday()
    day_type = 'L' if weekday < 5 else 'S' if weekday == 5 else 'D'

    return day_type


def flush_gps_pulses():
    print("Calling flush_gps_pulses command...")
    GPSPulse.objects.all().delete()
