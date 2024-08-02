import json
import uuid

import requests
import logging
from typing import List
from decouple import config
from datetime import timedelta
from django.utils import timezone

from rest_api.models import Segment, Speed, HistoricSpeed, Alert, AlertThreshold
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
        self.ALERT_URL = '{0}/adminapp/alert'.format(self.server_name)
        self.CREATE_ALERT_URL = "{0}/add".format(self.ALERT_URL)
        self.session = self.get_logged_session()

    def get_update_alert_url(self, alert_id):
        return "{0}/{1}".format(self.ALERT_URL, alert_id)

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

    def update_alert(self, alert_data: dict, alert_id):
        payload = alert_data
        update_alert_url = self.get_update_alert_url(alert_id)
        res = self.session.put(update_alert_url)
        csrf_token = res.cookies['csrftoken']
        payload['csrfmiddlewaretoken'] = csrf_token

        return self.session.put(update_alert_url, data=payload, cookies=res.cookies)


def create_alert_data(stops: List[str], segment_id: uuid.uuid4):
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


def create_alerts():
    print("Calling create_alerts...")
    now = timezone.localtime()
    end_time = now.replace(second=0, microsecond=0)
    delta = timedelta(minutes=15)

    start_time = end_time - delta
    day_type = get_day_type(start_time)
    temporal_segment = get_temporal_segment(start_time)
    segments = Segment.objects.all()
    alert_threshold = AlertThreshold.objects.first().threshold

    for segment in segments:
        speed = Speed.objects.filter(segment=segment, day_type=day_type, temporal_segment=temporal_segment,
                                     timestamp__gte=start_time, timestamp__lte=end_time).first()
        if speed is None:
            continue
        historic_speed = HistoricSpeed.objects.filter(segment=segment, day_type=day_type,
                                                      temporal_segment=temporal_segment).order_by("-timestamp").first()
        if historic_speed is None:
            continue
        speed_value = speed.speed
        historic_speed_value = historic_speed.speed
        alert_condition = alert_threshold * speed_value < historic_speed_value

        if alert_condition:
            alert_obj_data = {
                "segment": segment,
                "detected_speed": speed,
                "temporal_segment": temporal_segment
            }
            Alert.objects.create(**alert_obj_data)


def send_alerts():
    print("Calling send_alerts...")
    end_time = timezone.localtime()
    delta = timedelta(minutes=15)
    start_time = end_time - delta
    site_manager = TranSappSiteManager()

    alerts = Alert.objects.filter(timestamp__gte=start_time, timestamp__lte=end_time)
    for alert in alerts:
        segment = alert.segment
        stops = segment.get_stops()
        segment_id = segment.segment_id
        alert_data = create_alert_data(stops, segment_id)
        site_manager.create_alert(alert_data)
