from rest_api.models import Speed, HistoricSpeed, Segment
from rest_api.util.alert import TranSappSiteManager, AlertForm
from django.utils import timezone
from datetime import timedelta


def check_speed_with_historic_speed(speed_obj: Speed, historic_speed_obj: HistoricSpeed, segment: Segment) -> None:
    speed = speed_obj.speed
    historic_speed = historic_speed_obj.speed
    if 2 * speed < historic_speed:
        start = timezone.now()
        end = (start + timedelta(days=1, minutes=30))

        time_start = start.time()
        time_end = end.time()

        start_date = start.date()
        end_date = end.date()

        transapp_manager = TranSappSiteManager()
        alert_form = AlertForm(
            name="UOCT Speed Anomaly Alert",
            activated=False,
            message="UOCT Speed Anomaly",
            stops=segment.get_stops(),
            start=start_date,
            end=end_date,
            start_time_day=time_start,
            end_time_day=time_end,
            monday=True,
            tuesday=True,
            wednesday=True,
            thursday=True,
            friday=True,
            saturday=True,
            sunday=True
        )
        transapp_manager.create_alert(alert_form.get_alert())
