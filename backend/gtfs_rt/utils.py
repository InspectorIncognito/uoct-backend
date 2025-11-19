from datetime import datetime, timedelta

import numpy as np
from django.utils import timezone
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
    return day_minutes // interval


def get_temporal_range(temporal_segment, reference_datetime=None):
    # Base: ahora en UTC
    if reference_datetime is None:
        reference_datetime = timezone.now()

    start_minutes = temporal_segment * 15
    start_hour = start_minutes // 60
    start_minute = start_minutes % 60

    # Construir un datetime en UTC, conservando la fecha actual
    start_time = reference_datetime.replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )

    end_time = start_time + timedelta(minutes=15)
    return start_time, end_time


def get_last_temporal_range():
    delta = timedelta(minutes=15)
    now = timezone.now()
    last_15_minutes = now - delta
    last_temporal_segment = get_temporal_segment(last_15_minutes)
    print(
        f"DEBUG: now={now}, last_15_minutes={last_15_minutes}, segment={last_temporal_segment}"
    )
    return get_temporal_range(last_temporal_segment, reference_datetime=last_15_minutes)


def get_last_temporal_segment():
    delta = timedelta(minutes=15)
    now = timezone.now()
    last_15_minutes = now - delta
    last_temporal_segment = get_temporal_segment(last_15_minutes)
    return last_15_minutes.date(), last_temporal_segment


def get_day_type(dt: datetime):
    if dt.tzinfo is None:
        raise ValueError("datetime instance must have a tzinfo")
    # Convertir a Santiago solo para determinar día de semana
    santiago_tz = pytz.timezone('America/Santiago')
    converted_timestamp = dt.astimezone(santiago_tz)
    weekday = converted_timestamp.weekday()
    day_type = "L" if weekday < 5 else "S" if weekday == 5 else "D"

    return day_type


def get_previous_month():
    current_datetime = timezone.now()
    current_date = current_datetime.replace(day=1)
    current_date = current_date - timedelta(days=1)
    return current_date.month


def flush_gps_pulses():
    print("Calling flush_gps_pulses command...")
    GPSPulse.objects.all().delete()
