from rest_api.models import Speed, HistoricSpeed, Segment
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum, ExpressionWrapper, FloatField
from django.db.models.functions import Round


def flush_historic_speeds():
    HistoricSpeed.objects.all().delete()


def get_month_commercial_speed(year: int, month: int):
    print("Calling get_month_commercial_speed command...")
    creation_date = timezone.localtime().replace(year=year, month=month, day=1, hour=0, minute=0, second=0,
                                                 microsecond=0)
    last_month_speeds = Speed.objects.filter(timestamp__year=year, timestamp__month=month)
    avg_speeds = (
        last_month_speeds
        .values('segment', 'day_type', 'temporal_segment')
        .annotate(
            total_distance=Sum('distance'),
            total_time=Sum('time_secs'),
            avg_speed=ExpressionWrapper(
                Round(3.6 * Sum('distance') / Sum('time_secs'), 2),
                output_field=FloatField()
            )
        )
    )
    for avg_speed in avg_speeds:
        historic_speed_data = dict(
            segment=Segment.objects.get(pk=avg_speed['segment']),
            speed=avg_speed['avg_speed'],
            day_type=avg_speed['day_type'],
            temporal_segment=avg_speed['temporal_segment'],
            timestamp=creation_date
        )
        HistoricSpeed.objects.create(**historic_speed_data)


def save_historic_avg_speed(avg_speeds, custom_datetime=None):
    for avg_speed in avg_speeds:
        historic_speed_data = {"segment": Segment.objects.get(pk=avg_speed["segment"]),
                               "day_type": avg_speed["day_type"],
                               "speed": avg_speed["avg_speed"],
                               'timestamp': custom_datetime if custom_datetime is not None else None}


def get_last_month_avg_speed():
    print("Calling get_last_month_avg_speed command...")
    today = timezone.localtime() - timedelta(days=1)
    this_year = today.year
    this_month = today.month
    get_month_commercial_speed(year=this_year, month=this_month)
