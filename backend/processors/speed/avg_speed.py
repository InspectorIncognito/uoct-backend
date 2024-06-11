from rest_api.models import Speed, HistoricSpeed
from datetime import datetime
from django.db.models import Avg


def get_avg_speed_by_month(year, month):
    start_date = datetime(year, month, 1, 0, 0, 0, 0)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, 0, 0, 0)
    else:
        end_date = datetime(year, month + 1, 1, 0, 0, 0)

    speeds_in_month = Speed.objects.filter(
        timestamp__gte=start_date,
        timestamp_lt=end_date,
    )

    avg_speeds = (speeds_in_month.
                  values("segment", "day_type")
                  .annotate(avg_speed=Avg("speed"))
                  .order_by("segment", "day_type")
                  )
    return avg_speeds


def save_historic_avg_speed(avg_speeds):
    for avg_speed in avg_speeds:
        historic_speed_data = {
            "segment": avg_speed["segment"],
            "day_type": avg_speed["day_type"],
            "speed": avg_speed["avg_speed"]
        }
        HistoricSpeed.objects.create(**historic_speed_data)
