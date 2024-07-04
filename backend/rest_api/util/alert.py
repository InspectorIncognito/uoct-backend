import json
import requests
import logging
from typing import List
from decouple import config
from datetime import timedelta
from django.utils import timezone

from rest_api.models import Segment, Speed, HistoricSpeed, Alert
from gtfs_rt.utils import get_temporal_segment, get_day_type

logger = logging.getLogger(__name__)
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ALERT_AUTHOR = config("ALERT_AUTHOR")


class TranSappSiteManager:

    def __init__(self):
        self.server_name = 'https://{0}'.format(config('TRANSAPP_HOST'))
        self.server_username = config('TRANSAPP_SITE_USERNAME')
        # urls
        self.LOGIN_URL = '{0}/login/?next=/'.format(self.server_name)
        self.CREATE_ALERT_URL = '{0}/adminapp/alert/add'.format(self.server_name)

        self.session = self.get_logged_session()

    def get_logged_session(self):
        payload = {
            'username': self.server_username,
            'password': config('TRANSAPP_SITE_PASSWORD'),
            'next': '/adminapp/'
        }

        req_session = requests.Session()
        res = req_session.get(self.LOGIN_URL)
        csrf_token = res.cookies['csrftoken']
        payload['csrfmiddlewaretoken'] = csrf_token

        req_session.headers.update({'referer': self.LOGIN_URL})
        response = req_session.post(self.LOGIN_URL, data=payload, cookies=res.cookies)

        logger.info('se intenta iniciar sesión en "{0}" con usuario "{1}". Resultado: {2}'.format(
            self.server_name, self.server_username, response.status_code))

        return req_session

    def create_alert(self, alert_data: dict):
        payload = alert_data

        res = self.session.get(self.CREATE_ALERT_URL)
        csrf_token = res.cookies['csrftoken']
        payload['csrfmiddlewaretoken'] = csrf_token

        return self.session.post(self.CREATE_ALERT_URL, data=payload, cookies=res.cookies)


def create_alert_data(stops: List[str]):
    alert_data = {}

    now = timezone.localtime()
    now = now.replace(microsecond=0)
    weekday = now.weekday()
    for idx, day in enumerate(DAYS):
        alert_data[day] = idx == weekday
    alert_data['start'] = str(now.date())
    alert_data['end'] = str(now.date())

    start_time_day = now.time()
    end_time_day = (now + timedelta(minutes=30)).time()
    alert_data['start_time_day'] = f"{start_time_day.hour:02}:{start_time_day.minute:02}"
    alert_data['end_time_day'] = f"{end_time_day.hour:02}:{end_time_day.minute:02}"

    alert_data['name'] = "Speed Anomaly Test"
    alert_data['message'] = "Speed Anomaly detected"
    alert_data['stops'] = [json.dumps(dict(label="Test stops", value='|'.join(stops)))]

    alert_data['activated'] = False
    alert_data['author'] = ALERT_AUTHOR

    return alert_data


def send_alerts():
    print("Calling send_alerts...")
    now = timezone.localtime()
    now = now.replace(second=0, microsecond=0)
    delta = timedelta(minutes=15)
    site_manager = TranSappSiteManager()

    start_time = now - delta
    day_type = get_day_type(start_time)
    temporal_segment = get_temporal_segment(start_time)

    segments = Segment.objects.all()
    for segment in segments:
        speed = Speed.objects.filter(segment=segment, temporal_segment=temporal_segment,
                                     day_type=day_type).order_by("-timestamp").first()
        if speed is None:
            continue
        historic_speed = HistoricSpeed.objects.filter(segment=segment, temporal_segment=temporal_segment,
                                                      day_type=day_type).order_by("-timestamp").first()
        if historic_speed is None:
            continue

        alert_condition = 2 * speed < historic_speed
        if alert_condition:
            stops = segment.get_stops()
            alert_data = create_alert_data(stops)
            site_manager.create_alert(alert_data)

            alert_obj_data = {
                "segment": segment,
                "detected_speed": speed,
                "temporal_segment": temporal_segment
            }
            alert = Alert.objects.create(**alert_obj_data)
            print(f"Alert object created: {alert}")
