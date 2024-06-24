from rest_api.models import Speed, HistoricSpeed, Segment
from datetime import datetime, timedelta
from django.db.models import Avg
from django.utils import timezone


def get_last_month_avg_speed():
    now = timezone.now()
    yesterday = now - timedelta(days=1)
    last_month = yesterday.month
    last_year = yesterday.year

    last_month_speeds = Speed.objects.filter(timestamp__year=last_year, timestamp__month=last_month)
    avg_speeds = last_month_speeds.values("segment", "day_type", "temporal_segment").annotate(
        average_segment_speed=Avg("speed")).order_by("segment", "day_type", "temporal_segment")
    for historic_speed in avg_speeds:
        historic_speed_data = {
            "segment": Segment.objects.get(pk=historic_speed["segment"]),
            "speed": historic_speed["average_segment_speed"],
            "day_type": historic_speed["day_type"],
            "temporal_segment": historic_speed["temporal_segment"]
        }
        HistoricSpeed.objects.create(**historic_speed_data)


def get_avg_speed_by_month(year, month):
    start_date = datetime(year, month, 1, 0, 0, 0, 0)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, 0, 0, 0)
    else:
        end_date = datetime(year, month + 1, 1, 0, 0, 0)

    start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
    end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

    speeds_in_month = Speed.objects.filter(
        timestamp__gte=start_date,
        timestamp__lt=end_date,
    )

    avg_speeds = (speeds_in_month.
                  values("segment", "day_type")
                  .annotate(avg_speed=Avg("speed"))
                  .order_by("segment", "day_type")
                  )
    return avg_speeds


def save_historic_avg_speed(avg_speeds, custom_datetime=None):
    for avg_speed in avg_speeds:
        historic_speed_data = {"segment": Segment.objects.get(pk=avg_speed["segment"]),
                               "day_type": avg_speed["day_type"],
                               "speed": avg_speed["avg_speed"],
                               'timestamp': custom_datetime if custom_datetime is not None else None}
        HistoricSpeed.objects.create(**historic_speed_data)
