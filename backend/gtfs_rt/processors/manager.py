import pytz

from gtfs_rt.config import PROTO_URL
import sched
import time
import datetime
import requests
from gtfs_rt.models import GPSPulse
from google.transit import gtfs_realtime_pb2
from django.utils.timezone import get_current_timezone


class GTFSRTManager:
    def __init__(self, gtfs_rt_url=PROTO_URL):
        self.url = gtfs_rt_url
        self.start_datetime = datetime.datetime.now()
        self.previous_timestamp = '0'
        self.until_datetime = datetime.datetime.now()

    def __update_until_datetime(self, hours):
        delta = datetime.timedelta(hours=hours)
        self.until_datetime = self.start_datetime + delta

    def __update_previous_timestamp(self, previous_timestamp: str):
        self.previous_timestamp = previous_timestamp

    @staticmethod
    def read_proto_raw_content(proto_raw_content) -> gtfs_realtime_pb2.FeedMessage:
        try:
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(proto_raw_content)
        except:
            print("Error parsing proto raw content")
        else:
            return feed

    @staticmethod
    def get_timestamp_from_feed(feed):
        return feed.header.timestamp

    def download_raw_gtfs_rt_data(self):
        response = requests.get(self.url)
        return response.content

    @staticmethod
    def save_gtfs_rt_to_db(feed: gtfs_realtime_pb2.FeedMessage):
        for entity in feed.entity:
            if entity.HasField('vehicle'):
                if entity.vehicle.HasField('trip') and entity.vehicle.HasField('vehicle'):
                    timestamp = entity.vehicle.timestamp
                    route_id = entity.vehicle.trip.route_id
                    direction_id = entity.vehicle.trip.direction_id
                    gps = entity.vehicle.position
                    GPSPulse.objects.create(
                        route_id=route_id,
                        direction_id=direction_id,
                        latitude=gps.latitude,
                        longitude=gps.longitude,
                        timestamp=datetime.datetime.fromtimestamp(timestamp, tz=pytz.timezone(
                            "America/Santiago")) - datetime.timedelta(hours=4)
                    )

    def run_process(self):
        raw_data = self.download_raw_gtfs_rt_data()
        feed = self.read_proto_raw_content(raw_data)
        timestamp = self.get_timestamp_from_feed(feed)
        if timestamp == self.previous_timestamp:
            print("Ignoring repeated proto file: Same timestamp.")
            return
        self.__update_previous_timestamp(timestamp)
        self.save_gtfs_rt_to_db(feed)

    def process_schedule(self, scheduler: sched.scheduler):
        actual_datetime = datetime.datetime.now()
        print(f"Donwloading file at {actual_datetime}")
        if self.until_datetime < actual_datetime:
            print("Stopping downloading GTFS RT data...")
            return
        self.run_process()
        scheduler.enter(60, 1, self.process_schedule, (scheduler,))

    def run_process_scheduler(self, hours: int = 1):
        self.__update_until_datetime(hours)
        print(f"Downloading GTFS RT data until {self.until_datetime.time()}")

        scheduler = sched.scheduler(time.time, time.sleep)
        scheduler.enter(60, 1, self.process_schedule, (scheduler,))
        scheduler.run()
