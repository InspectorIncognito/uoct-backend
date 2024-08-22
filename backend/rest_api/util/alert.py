import datetime
import json

import requests
import logging
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
        self.LOOKUP_URL = '{0}/adminapp/alert/data'.format(self.server_name)
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

        res = self.session.get(update_alert_url)
        csrf_token = res.cookies['csrftoken']
        payload['csrfmiddlewaretoken'] = csrf_token

        return self.session.post(update_alert_url, data=payload, cookies=res.cookies)

    def alert_lookup(self, alert_name: str):
        url = '{0}{1}{2}'.format(self.LOOKUP_URL,
                                 '?draw=1&columns%5B0%5D%5Bdata%5D=activated&columns%5B0%5D%5Bname%5D=&columns%5B0%5D%5Bsearchable%5D=true&columns%5B0%5D%5Borderable%5D=true&columns%5B0%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B0%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B1%5D%5Bdata%5D=name&columns%5B1%5D%5Bname%5D=&columns%5B1%5D%5Bsearchable%5D=true&columns%5B1%5D%5Borderable%5D=true&columns%5B1%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B1%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B2%5D%5Bdata%5D=start&columns%5B2%5D%5Bname%5D=&columns%5B2%5D%5Bsearchable%5D=true&columns%5B2%5D%5Borderable%5D=true&columns%5B2%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B2%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B3%5D%5Bdata%5D=end&columns%5B3%5D%5Bname%5D=&columns%5B3%5D%5Bsearchable%5D=true&columns%5B3%5D%5Borderable%5D=true&columns%5B3%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B3%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B4%5D%5Bdata%5D=start_time_day&columns%5B4%5D%5Bname%5D=&columns%5B4%5D%5Bsearchable%5D=true&columns%5B4%5D%5Borderable%5D=true&columns%5B4%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B4%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B5%5D%5Bdata%5D=end_time_day&columns%5B5%5D%5Bname%5D=&columns%5B5%5D%5Bsearchable%5D=true&columns%5B5%5D%5Borderable%5D=true&columns%5B5%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B5%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B6%5D%5Bdata%5D=week_days&columns%5B6%5D%5Bname%5D=&columns%5B6%5D%5Bsearchable%5D=true&columns%5B6%5D%5Borderable%5D=true&columns%5B6%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B6%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B7%5D%5Bdata%5D=stop_number&columns%5B7%5D%5Bname%5D=&columns%5B7%5D%5Bsearchable%5D=true&columns%5B7%5D%5Borderable%5D=true&columns%5B7%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B7%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B8%5D%5Bdata%5D=useful&columns%5B8%5D%5Bname%5D=&columns%5B8%5D%5Bsearchable%5D=true&columns%5B8%5D%5Borderable%5D=false&columns%5B8%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B8%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B9%5D%5Bdata%5D=useless&columns%5B9%5D%5Bname%5D=&columns%5B9%5D%5Bsearchable%5D=true&columns%5B9%5D%5Borderable%5D=false&columns%5B9%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B9%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B10%5D%5Bdata%5D=&columns%5B10%5D%5Bname%5D=&columns%5B10%5D%5Bsearchable%5D=true&columns%5B10%5D%5Borderable%5D=false&columns%5B10%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B10%5D%5Bsearch%5D%5Bregex%5D=false&order%5B0%5D%5Bcolumn%5D=0&order%5B0%5D%5Bdir%5D=asc&start=0&length=10&search%5Bvalue%5D=&search%5Bregex%5D=false&_=1564452662157',
                                 f'search[value]={alert_name}'
                                 )
        response_raw = self.session.get(url)
        response_json = json.loads(response_raw.content.decode())
        return response_json


def create_alert_to_admin(site_manager: TranSappSiteManager, alert_obj: Alert):
    segment = alert_obj.segment
    speed = alert_obj.detected_speed
    alert_data = create_alert_data(segment, speed)
    site_manager.create_alert(alert_data)


def update_alert_from_admin(site_manager: TranSappSiteManager, alert_obj: Alert, alert_data: dict):
    segment = alert_obj.segment
    speed = alert_obj.detected_speed
    alert_public_id = alert_data['public_id']

    new_end = timezone.now().strftime('%Y-%m-%d')
    delta = timedelta(minutes=15)
    new_end_time_day = str((datetime.datetime.strptime(alert_data['end_time_day'], '%H:%M:%S') + delta).time())[:-3]

    alert_data = create_alert_data(segment, speed)
    new_alert_data = dict(
        name=alert_data['name'],
        start=alert_data['start'],
        end=new_end,
        start_day_time=alert_data['start_time_day'],
        end_day_time=new_end_time_day,
    )
    alert_data.update(new_alert_data)

    site_manager.update_alert(alert_data, alert_public_id)


def create_alert_data(segment: Segment, speed: Speed):
    alert_data = dict()
    stops = segment.get_stops()

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

    segment_uuid = str(segment.segment_id)
    segment_id = str(segment.pk)
    shape_id = str(segment.shape.pk)
    temporal_segment = str(speed.temporal_segment)
    day_type = str(speed.day_type)
    detected_speed = str(speed.speed)

    alert_data['name'] = "Speed Anomaly {}".format(segment_uuid)

    # prefill data = shape_id|segment_id|temporal_segment|day_type|detected_speed
    prefill_data = '|'.join([shape_id, segment_id, temporal_segment, day_type, detected_speed])
    alert_prefill_data = '&entry.1001130690={}'.format(prefill_data)

    alert_url = 'https://docs.google.com/forms/d/e/1FAIpQLSfPOqOT45GnlP_gBol0613yl2X-ObMC6ApWfTLnSSrcpGdRKg/viewform?usp=pp_url{}'.format(
        alert_prefill_data)

    alert_data['message'] = """
        Hemos detectado <strong>congestión</strong>, ayúdanos a resolverla respondiendo esta breve encuesta🚌<br><a target="_blank" href="{}">Presiona aquí👈</a>
        """.format(alert_url)
    alert_data['stops'] = [json.dumps(dict(label="Affected Stops", value='|'.join(stops)))]

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
        alert_condition = speed_value < historic_speed_value / alert_threshold

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
        segment_uuid = segment.segment_id
        alert_search_response = site_manager.alert_lookup(segment_uuid)
        data = alert_search_response['data']
        if len(data) > 0:  # Check if the alert already exists in TranSapp's admin
            alert_data = data[0]
            update_alert_from_admin(site_manager, alert, alert_data)

        else:  # The alert doesn't exist, create it instead
            create_alert_to_admin(site_manager, alert)
