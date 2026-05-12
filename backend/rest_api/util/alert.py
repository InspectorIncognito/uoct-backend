import datetime
import json
import logging
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import requests
from decouple import config
from django.utils import timezone
from gtfs_rt.utils import (get_day_type, get_last_temporal_range,
                           get_temporal_segment)
from rest_api.models import (Alert, AlertThreshold, HistoricSpeed, Segment,
                             Speed)

logger = logging.getLogger()
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ALERT_AUTHOR = config("ALERT_AUTHOR")
SANTIAGO_TZ = ZoneInfo("America/Santiago")


def get_santiago_time():
    """Return the actual time in Santiago de Chile (GMT-3)."""
    return timezone.now().astimezone(SANTIAGO_TZ)


# TODO: Review how to handle alerts creation and updates to TranSapp's Admin site
class TranSappSiteManager:
    def __init__(self):
        self.server_name = "https://{0}".format(config("TRANSAPP_HOST"))
        self.server_username = config("TRANSAPP_SITE_USERNAME")

        self.LOGIN_URL = "{0}/login/?next=/".format(self.server_name)
        self.ALERT_URL = "{0}/adminapp/alert".format(self.server_name)
        self.LOOKUP_URL = "{0}/adminapp/alert/data".format(self.server_name)
        self.CREATE_ALERT_URL = "{0}/add".format(self.ALERT_URL)

        self.session = self.get_logged_session()

    def get_update_alert_url(self, alert_id):
        return f"{self.ALERT_URL}/{alert_id}"

    def get_delete_alert_url(self, alert_public_id):
        return f"{self.ALERT_URL}/{alert_public_id}/delete"

    @staticmethod
    def get_drawtable(start: int = 0, length: int = 10):
        return f"draw=1&columns[0][data]=activated&columns[0][name]=&columns[0][searchable]=true&columns[0][orderable]=true&columns[0][search][value]=&columns[0][search][regex]=false&columns[1][data]=name&columns[1][name]=&columns[1][searchable]=true&columns[1][orderable]=true&columns[1][search][value]=&columns[1][search][regex]=false&columns[2][data]=start&columns[2][name]=&columns[2][searchable]=true&columns[2][orderable]=true&columns[2][search][value]=&columns[2][search][regex]=false&columns[3][data]=end&columns[3][name]=&columns[3][searchable]=true&columns[3][orderable]=true&columns[3][search][value]=&columns[3][search][regex]=false&columns[4][data]=start_time_day&columns[4][name]=&columns[4][searchable]=true&columns[4][orderable]=true&columns[4][search][value]=&columns[4][search][regex]=false&columns[5][data]=end_time_day&columns[5][name]=&columns[5][searchable]=true&columns[5][orderable]=true&columns[5][search][value]=&columns[5][search][regex]=false&columns[6][data]=week_days&columns[6][name]=&columns[6][searchable]=true&columns[6][orderable]=true&columns[6][search][value]=&columns[6][search][regex]=false&columns[7][data]=stop_number&columns[7][name]=&columns[7][searchable]=true&columns[7][orderable]=true&columns[7][search][value]=&columns[7][search][regex]=false&columns[8][data]=useful&columns[8][name]=&columns[8][searchable]=true&columns[8][orderable]=false&columns[8][search][value]=&columns[8][search][regex]=false&columns[9][data]=useless&columns[9][name]=&columns[9][searchable]=true&columns[9][orderable]=false&columns[9][search][value]=&columns[9][search][regex]=false&columns[10][data]=&columns[10][name]=&columns[10][searchable]=true&columns[10][orderable]=false&columns[10][search][value]=&columns[10][search][regex]=false&order[0][column]=0&order[0][dir]=asc&start={start}&length={length}&search[regex]=false&_=1564452662157"

    def get_logged_session(self):
        payload = {
            "username": self.server_username,
            "password": config("TRANSAPP_SITE_PASSWORD"),
            "next": "/adminapp/",
        }

        req_session = requests.Session()
        res = req_session.get(self.LOGIN_URL)
        csrf_token = res.cookies["csrftoken"]
        payload["csrfmiddlewaretoken"] = csrf_token

        req_session.headers.update({"referer": self.LOGIN_URL})
        response = req_session.post(self.LOGIN_URL, data=payload, cookies=res.cookies)

        logger.info(
            'se intenta iniciar sesión en "{0}" con usuario "{1}". Resultado: {2}'.format(
                self.server_name, self.server_username, response.status_code
            )
        )

        return req_session

    def create_alert(self, alert_data: dict):
        payload = alert_data

        res = self.session.get(self.CREATE_ALERT_URL)
        if res.status_code != 200:
            print(
                f"Failed to GET create form. Status: {res.status_code}, Response: {res.text}"
            )
            logger.error(
                f"Failed to GET create form. Status: {res.status_code}, Response: {res.text}"
            )
            return None
        csrf_token = res.cookies["csrftoken"]
        if not csrf_token:
            print("No CSRF token found in cookies")
            logger.error("No CSRF token found in cookies")
            return None
        payload["csrfmiddlewaretoken"] = csrf_token

        return self.session.post(
            self.CREATE_ALERT_URL, data=payload, cookies=res.cookies
        )

    def update_alert(self, alert_data: dict, alert_id):
        payload = alert_data
        update_alert_url = self.get_update_alert_url(alert_id)

        res = self.session.get(update_alert_url)
        csrf_token = res.cookies["csrftoken"]
        payload["csrfmiddlewaretoken"] = csrf_token

        return self.session.post(update_alert_url, data=payload, cookies=res.cookies)

    def alert_lookup(self, alert_name: str):
        url = f"{self.LOOKUP_URL}?{self.get_drawtable()}&search[value]={alert_name}"
        response_raw = self.session.get(url)
        response_json = json.loads(response_raw.content.decode())
        return response_json

    def get_all_alerts(self) -> list:
        query = "search[value]=Speed Anomaly"
        url = f"{self.LOOKUP_URL}?{self.get_drawtable()}&{query}"
        response_raw = self.session.get(url)
        response_json = json.loads(response_raw.content.decode())
        records_total = response_json["recordsTotal"]
        site_alerts = response_json["data"]
        if records_total > len(site_alerts):
            start = len(site_alerts)
            length = records_total - start
            url = f"{self.LOOKUP_URL}?{self.get_drawtable(start=start, length=length)}&{query}"
            response_rest_site_alerts_raw = self.session.get(url)
            rest_site_alerts_json = json.loads(
                response_rest_site_alerts_raw.content.decode()
            )
            rest_site_alerts = rest_site_alerts_json["data"]
            site_alerts = site_alerts + rest_site_alerts
        return site_alerts

    def alert_delete(self, alert_public_id):
        alert_delete_url = self.get_delete_alert_url(alert_public_id)
        payload = {}
        res = self.session.get(self.LOGIN_URL)
        csrf_token = res.cookies["csrftoken"]
        payload["csrfmiddlewaretoken"] = csrf_token

        return self.session.post(alert_delete_url, data=payload)

    def delete_all_alerts(self):
        site_alerts = self.get_all_alerts()
        for site_data in site_alerts:
            name = site_data["name"]
            if "Speed Anomaly" not in name:
                print("Passed alert", name)
                continue
            alert_public_id = site_data["public_id"]
            delete_response = self.alert_delete(alert_public_id)


def create_alert_to_admin(site_manager: TranSappSiteManager, alert_obj: Alert):
    segment = alert_obj.segment
    speed = alert_obj.detected_speed
    alert_data = create_alert_data(segment, speed)
    print("Creating alert with data:", alert_data)
    res = site_manager.create_alert(alert_data)
    if res.status_code != 200:
        return None
    print("Alert created successfully.")
    return res


def update_alert_from_admin(
    site_manager: TranSappSiteManager,
    alert_obj: Alert,
    alert_data: dict,
    activated=True,
):
    print("Updating alert with data:", alert_data)
    segment = alert_obj.segment
    speed = alert_obj.detected_speed
    alert_public_id = alert_data["public_id"]

    # Create fresh alert data based on current time for time-related fields
    fresh_alert_data = create_alert_data(segment, speed)

    # Prepare update payload starting with existing site alert data
    update_payload = {
        "name": fresh_alert_data["name"],
        "message": fresh_alert_data["message"],
        "stops": fresh_alert_data["stops"],
        "author": fresh_alert_data["author"],
        # Update time-related fields with fresh values
        "start": fresh_alert_data["start"],
        "end": fresh_alert_data["end"],
        "start_time_day": fresh_alert_data["start_time_day"],
        "end_time_day": fresh_alert_data["end_time_day"],
        # Preserve day selection from fresh data
        **{day: fresh_alert_data.get(day, "") for day in DAYS},
        # Control activation
        "activated": "on" if activated else "",
    }

    res = site_manager.update_alert(update_payload, alert_id=alert_public_id)
    if res.status_code != 200:
        print("Failed to update alert.")
        print(f"Status: {res.status_code}, Response: {res.text}")
        print("=" * 30)
        return None
    print("Alert updated successfully.")
    return res


def create_alert_data(segment: Segment, speed: Speed, interval: int = 15):
    alert_data = dict()
    stops = segment.get_stops()

    now = get_santiago_time()
    now = now.replace(microsecond=0)

    # Derivar los límites reales del temporal segment
    ts = int(speed.temporal_segment)
    ts_start_minutes = ts * interval
    ts_end_minutes = (ts + 1) * interval

    speed_date_utc = speed.timestamp.date()

    ts_utc_start = datetime.datetime(
        speed_date_utc.year, speed_date_utc.month, speed_date_utc.day,
        ts_start_minutes // 60, ts_start_minutes % 60,
        tzinfo=ZoneInfo("UTC"),
    )
    ts_utc_end = ts_utc_start + timedelta(minutes=interval)
    # Convertir a Santiago para los campos del formulario
    ts_santiago_start = ts_utc_start.astimezone(SANTIAGO_TZ)
    ts_santiago_end = ts_utc_end.astimezone(SANTIAGO_TZ)

    weekday = now.weekday()
    for idx, day in enumerate(DAYS):
        if idx == weekday:
            alert_data[day] = "on"

    alert_data["start"] = (ts_santiago_start - timedelta(days=1)).strftime("%m/%d/%Y")
    alert_data["end"] = (ts_santiago_start + timedelta(days=1)).strftime("%m/%d/%Y")
    alert_data["start_time_day"] = f"{ts_santiago_start.hour:02}:{ts_santiago_start.minute:02}:00"
    alert_data["end_time_day"] = f"{ts_santiago_end.hour:02}:{ts_santiago_end.minute:02}:00"

    segment_uuid = str(segment.segment_id)
    segment_id = str(segment.pk)
    shape_id = str(segment.shape.pk)
    temporal_segment = str(speed.temporal_segment)
    day_type = str(speed.day_type)
    detected_speed = str(speed.get_speed())

    alert_data["name"] = "Speed Anomaly {}".format(segment_uuid)

    # prefill data = shape_id|segment_id|temporal_segment|day_type|detected_speed
    prefill_data = "|".join(
        [shape_id, segment_id, temporal_segment, day_type, detected_speed]
    )
    alert_prefill_data = "&entry.1084383620={}".format(prefill_data)

    alert_url = "https://docs.google.com/forms/d/e/1FAIpQLSdA1rZ1PwADaPQ8Hhf8zlgOVpGfXmRZmDOC0aXJTkSSQAlMpQ/viewform?usp=pp_url{}".format(
        alert_prefill_data
    )

    alert_data["message"] = """
        Ayúdanos y participa por $30.000 para tu Bip!</strong> 💳<br>
        <a target="_blank" href="{}">👉 Presiona aquí para participar</a>
        """.format(alert_url)
    alert_data["stops"] = [
        json.dumps(dict(label="Affected Stops", value="|".join(stops)))
    ]

    alert_data["activated"] = "on"
    alert_data["author"] = ALERT_AUTHOR

    return alert_data


def create_alerts(start_time: datetime = None, end_time: datetime = None):
    if start_time is None or end_time is None:
        start_time, end_time = get_last_temporal_range()

    temporal_segment = get_temporal_segment(start_time)
    day_type = get_day_type(start_time)

    segments = Segment.objects.all()
    alert_threshold = AlertThreshold.objects.first().threshold

    for segment in segments:
        speed_obj = Speed.objects.filter(
            segment=segment,
            timestamp__date=start_time.date(),
            temporal_segment=temporal_segment,
        ).first()
        historic_speed = (
            HistoricSpeed.objects.filter(
                segment=segment, day_type=day_type, temporal_segment=temporal_segment
            )
            .order_by("-timestamp")
            .first()
        )
        if speed_obj is None or historic_speed is None:
            logger.info(
                f"Skipping alert check for segment {segment.segment_id} due to missing speed data."
            )
            continue
        speed_value = speed_obj.get_speed()
        historic_speed_value = historic_speed.speed
        alert_condition = speed_value < historic_speed_value / alert_threshold

        if alert_condition:
            alert_obj_data = {
                "segment": segment,
                "detected_speed": speed_obj,
                "temporal_segment": temporal_segment,
            }
            Alert.objects.create(**alert_obj_data)


def search_alert_by_uuid(alert_data: dict, segment_uuid: uuid.UUID) -> dict or None:
    for alert in alert_data:
        alert_name = alert["name"]
        segment_id = uuid.UUID(alert_name.split(" ")[-1])
        if segment_id == segment_uuid:
            return alert
    return None


def search_alert_obj(segment_uuid):
    return Alert.objects.filter(segment__segment_id=segment_uuid).first()


def update_alerts(
    site_manager: TranSappSiteManager,
    start_time: datetime = None,
    end_time: datetime = None,
):
    print("Calling update_alerts command...")
    if not start_time or not end_time:
        start_time, end_time = get_last_temporal_range()

    temporal_segment = get_temporal_segment(start_time)
    alert_date = start_time.date()
    alerts = Alert.objects.filter(
        temporal_segment = temporal_segment,
        detected_speed__timestamp__date=alert_date,
    )
    alert_data = site_manager.get_all_alerts()

    if alerts.count() == 0:
        print("No alerts to update.")
    for alert in alerts:
        segment_uuid = alert.segment.segment_id
        site_alert = search_alert_by_uuid(alert_data, segment_uuid)
        if site_alert is not None:
            print(f"Updating alert for segment {segment_uuid}...")
            alert.useful = site_alert.get("useful")
            alert.useless = site_alert.get("useless")
            alert.save()
            site_alert["checked"] = True
        else:  # Send a new alert to TranSapp's Admin
            print(f"Creating alert for segment {segment_uuid}...")
            create_alert_to_admin(site_manager, alert)

    for site_alert in alert_data:
        is_checked = site_alert.get("checked", False)
        segment_uuid = site_alert.get("name").split(" ")[-1]
        alert_obj = Alert.objects.filter(
            segment__segment_id=segment_uuid,
            temporal_segment=temporal_segment,
            detected_speed__timestamp__date=alert_date,
        ).first()
        if alert_obj is None:
            continue
        if is_checked:
            update_alert_from_admin(
                site_manager, alert_obj=alert_obj, alert_data=site_alert
            )
        else:
            if site_alert.get("activated", False):
                update_alert_from_admin(
                    site_manager, alert_obj, site_alert, activated=False
                )


def get_active_alerts():
    # Use UTC time for database queries since Alert.timestamp is stored in UTC
    end_time = timezone.now()
    start_time = end_time - timedelta(minutes=15)
    # Use select_related to prefetch segment and shape in a single query
    alerts = Alert.objects.select_related("segment", "segment__shape").filter(
        timestamp__gte=start_time,
        timestamp__lte=end_time,
    )
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
