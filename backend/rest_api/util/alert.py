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
        self.DRAWTABLE = "draw=1&columns[0][data]=activated&columns[0][name]=&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=name&columns[1][name]=&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&columns[2][data]=start&columns[2][name]=&columns[2][searchable]=true&columns[2][orderable]=true&columns[2][search][value]=&columns[2][search][regex]=false&columns[3][data]=end&columns[3][name]=&columns[3][searchable]=true&columns[3][orderable]=true&columns[3][search][value]=&columns[3][search][regex]=false&columns[4][data]=start_time_day&columns[4][name]=&columns[4][searchable]=true&columns[4][orderable]=true&columns[4][search][value]=&columns[4][search][regex]=false&columns[5][data]=end_time_day&columns[5][name]=&columns[5][searchable]=true&columns[5][orderable]=true&columns[5][search][value]=&columns[5][search][regex]=false&columns[6][data]=week_days&columns[6][name]=&columns[6][searchable]=true&columns[6][orderable]=true&columns[6][search][value]=&columns[6][search][regex]=false&columns[7][data]=stop_number&columns[7][name]=&columns[7][searchable]=true&columns[7][orderable]=true&columns[7][search][value]=&columns[7][search][regex]=false&columns[8][data]=useful&columns[8][name]=&columns[8][searchable]=true&columns[8][orderable]=false&columns[8][search][value]=&columns[8][search][regex]=false&columns[9][data]=useless&columns[9][name]=&columns[9][searchable]=true&columns[9][orderable]=false&columns[9][search][value]=&columns[9][search][regex]=false&columns[10][data]=&columns[10][name]=&columns[10][searchable]=true&columns[10][orderable]=false&columns[10][search][value]=&columns[10][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start=0&length=10&search[regex]=false&_=1564452662157"
        self.session = self.get_logged_session()

    def get_update_alert_url(self, alert_id):
        return "{0}/{1}".format(self.ALERT_URL, alert_id)

    def get_delete_alert_url(self, alert_public_id):
        return f"{self.ALERT_URL}/{alert_public_id}/delete"

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
        url = f'{self.LOOKUP_URL}?{self.DRAWTABLE}&search[value]={alert_name}'
        response_raw = self.session.get(url)
        response_json = json.loads(response_raw.content.decode())
        return response_json

    def get_all_alerts(self):
        url = f'{self.LOOKUP_URL}?{self.DRAWTABLE}&search[value]=Speed Anomaly'
        response_raw = self.session.get(url)
        response_json = json.loads(response_raw.content.decode())
        return response_json

    def alert_delete(self, alert_public_id):
        alert_delete_url = self.get_delete_alert_url(alert_public_id)
        payload = {}
        res = self.session.get(self.LOGIN_URL)
        csrf_token = res.cookies['csrftoken']
        payload['csrfmiddlewaretoken'] = csrf_token

        return self.session.post(alert_delete_url, data=payload)

    def delete_all_alerts(self):
        site_alerts = self.get_all_alerts()
        for site_data in site_alerts['data']:
            name = site_data['name']
            if "Speed Anomaly" not in name:
                print("Passed alert", name)
                continue
            alert_public_id = site_data['public_id']
            print(f"Deleting {name}")
            delete_response = self.alert_delete(alert_public_id)
            print(delete_response)
            print('deleted', alert_public_id)
            exit()


def create_alert_to_admin(site_manager: TranSappSiteManager, alert_obj: Alert):
    segment = alert_obj.segment
    speed = alert_obj.detected_speed
    alert_data = create_alert_data(segment, speed)
    site_manager.create_alert(alert_data)


def update_alert_from_admin(site_manager: TranSappSiteManager, alert_obj: Alert, alert_data: dict, activated=True):
    segment = alert_obj.segment
    speed = alert_obj.detected_speed
    alert_public_id = alert_data['public_id']

    new_end = timezone.localtime().strftime('%Y-%m-%d')
    delta = timedelta(minutes=15)
    new_end_time_day = str((datetime.datetime.strptime(alert_data['end_time_day'], '%H:%M:%S') + delta).time())[:-3]

    alert_data = create_alert_data(segment, speed)
    new_alert_data = dict(
        name=alert_data['name'],
        start=alert_data['start'],
        end=new_end,
        start_day_time=alert_data['start_time_day'],
        end_day_time=new_end_time_day,
        activated=activated
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
    detected_speed = str(speed.get_speed())

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

    alert_data['activated'] = True
    alert_data['author'] = ALERT_AUTHOR

    return alert_data


def create_alerts():
    print("Calling create_alerts command...")
    now = timezone.localtime()
    end_time = now.replace(second=0, microsecond=0)
    delta = timedelta(minutes=15)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    start_time = end_time - delta
    day_type = get_day_type(start_time)
    temporal_segment = get_temporal_segment(start_time)
    segments = Segment.objects.all()
    alert_threshold = AlertThreshold.objects.first().threshold

    for segment in segments:
        speed = Speed.objects.filter(segment=segment, day_type=day_type, timestamp__date=today,
                                     temporal_segment=temporal_segment).first()
        if speed is None:
            continue
        historic_speed = HistoricSpeed.objects.filter(segment=segment, day_type=day_type,
                                                      temporal_segment=temporal_segment).order_by("-timestamp").first()
        if historic_speed is None:
            continue
        speed_value = speed.get_speed()
        historic_speed_value = historic_speed.speed
        alert_condition = speed_value < historic_speed_value / alert_threshold

        if alert_condition:
            alert_obj_data = {
                "segment": segment,
                "detected_speed": speed,
                "temporal_segment": temporal_segment,
            }
            Alert.objects.create(**alert_obj_data)


def search_alert_by_uuid(alert_data, segment_uuid):
    for alert in alert_data:
        alert_name = alert['name']
        alert_uuid = alert_name.split(' ')[-1]
        if alert_uuid == segment_uuid:
            return alert
    return None


def search_alert_obj(segment_uuid):
    return Alert.objects.filter(segment__segment_id=segment_uuid).first()


def update_alerts(site_manager: TranSappSiteManager):
    print("Calling update_alerts command...")
    end_time = timezone.localtime()
    start_time = end_time - timedelta(minutes=15)
    temporal_segment = get_temporal_segment(start_time)

    alerts = Alert.objects.filter(timestamp__date=start_time.date(), temporal_segment=temporal_segment)
    alert_response = site_manager.get_all_alerts()
    alert_data = alert_response['data']
    for alert in alerts:
        segment_uuid = alert.segment.segment_id
        site_alert = search_alert_by_uuid(alert_data, segment_uuid)
        if site_alert is not None:
            alert.useful = site_alert.get('useful')
            alert.useless = site_alert.get('useless')
            alert.save()
            site_alert['checked'] = True
        else:  # Send a new alert to TranSapp's Admin
            create_alert_to_admin(site_manager, alert)

    for site_alert in alert_data:
        is_checked = site_alert.get('checked', False)
        segment_uuid = site_alert.get('name').split(' ')[-1]
        alert_obj = search_alert_obj(segment_uuid)
        if alert_obj is None:
            continue
        if is_checked:
            update_alert_from_admin(site_manager, alert_obj, site_alert)
        else:
            if site_alert.get('activated', False):
                update_alert_from_admin(site_manager, alert_obj, site_alert, activated=False)


def get_active_alerts():
    end_time = timezone.localtime()
    start_time = end_time - timedelta(minutes=15)
    today = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
    temporal_segment = get_temporal_segment(start_time)
    alerts = Alert.objects.filter(timestamp__gte=today, temporal_segment=temporal_segment)
    active_alerts = []
    for alert in alerts:
        key_value = alert.get_key_value()
        useful = alert.useful
        useless = alert.useless
        mid_point = alert.segment.get_middle_point()
        data = dict(
            coords=mid_point,
            key_value=key_value,
            useful=useful,
            useless=useless,
        )
        active_alerts.append(data)
    return active_alerts
