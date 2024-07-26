import numpy as np
from datetime import datetime
import pytz
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
    return int(day_minutes / interval)


def get_last_temporal_segment(date: datetime, interval: int = 15):
    temporal_segment = get_temporal_segment(date, interval)
    max_temporal_segment = int(1439 / 15)
    if temporal_segment == 0:
        return max_temporal_segment
    return temporal_segment - 1


def get_day_type(dt: datetime, timezone: datetime.tzinfo = pytz.UTC):
    if dt.tzinfo is None:
        raise ValueError("datetime instance must have a tzinfo")
    converted_timestamp = dt.astimezone(timezone)
    weekday = converted_timestamp.weekday()
    day_type = 'L' if weekday < 5 else 'S' if weekday == 5 else 'D'

    return day_type


def flush_gps_pulses():
    print("Calling flush_gps_pulses...")
    GPSPulse.objects.all().delete()
