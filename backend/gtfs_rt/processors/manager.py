import datetime
import sched
import time

import requests
from django.utils import timezone
from google.transit import gtfs_realtime_pb2
from rest_api.models import GTFSRTTimestamp

from gtfs_rt.config import PROTO_URL
from gtfs_rt.models import GPSPulse


class GTFSRTManager:
    def __init__(self, gtfs_rt_url=PROTO_URL):
        self.url = gtfs_rt_url
        self.start_datetime = timezone.localtime()
        self.previous_timestamp = "0"
        self.until_datetime = timezone.localtime()

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

    # TODO: Review this method to be sure that duplicated data is not stored in DB.
    # Fix the logic to compare timestamps correctly.
    # Use UTC timezone for timestamp comparison.
    def save_gtfs_rt_to_db(self, feed: gtfs_realtime_pb2.FeedMessage):
        current_timestamp = self.get_timestamp_from_feed(feed)
        if current_timestamp:
            current_timestamp = str(current_timestamp)
            manager = GTFSRTTimestamp.objects.first()
            last_timestamp = manager.last_timestamp
            if last_timestamp != "":
                if current_timestamp <= last_timestamp:
                    print("Ignoring duplicated GTFS-RT")
                    return
            else:
                manager.last_timestamp = current_timestamp
                manager.save()

        for entity in feed.entity:
            if entity.HasField("vehicle"):
                v = entity.vehicle
                if v.HasField("vehicle"):
                    timestamp = v.timestamp
                    route_id = v.trip.route_id if v.trip.HasField("route_id") else None
                    direction = (
                        v.trip.direction_id if v.trip.HasField("direction_id") else None
                    )
                    license_plate = v.vehicle.license_plate
                    gps = v.position
                    GPSPulse.objects.create(
                        route_id=route_id,
                        direction=direction,
                        latitude=gps.latitude,
                        longitude=gps.longitude,
                        bearing=gps.bearing,
                        license_plate=license_plate,
                        timestamp=datetime.datetime.fromtimestamp(timestamp).astimezone(
                            timezone.get_current_timezone()
                        ),
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
        actual_datetime = timezone.localtime()
        print(f"Donwloading file at {actual_datetime}")
        if self.until_datetime < actual_datetime:
            print("Stopping downloading GTFS RT data...")
            return
        self.run_process()
        scheduler.enter(60, 1, self.process_schedule, (scheduler,))

    def run_process_scheduler(self, hours: float = 1):
        self.__update_until_datetime(hours)
        print(f"Downloading GTFS RT data until {self.until_datetime.time()}")

        scheduler = sched.scheduler(time.time, time.sleep)
        scheduler.enter(60, 1, self.process_schedule, (scheduler,))
        scheduler.run()

    def run_process_forever(self):
        raw_data = self.download_raw_gtfs_rt_data()
        feed = self.read_proto_raw_content(raw_data)
        timestamp = self.get_timestamp_from_feed(feed)
        if timestamp == self.previous_timestamp:
            print("Ignoring repeated proto file: Same timestamp.")
            return
        self.__update_previous_timestamp(timestamp)
        self.save_gtfs_rt_to_db(feed)

    def run_process_cron(self):
        raw_data = self.download_raw_gtfs_rt_data()
        feed = self.read_proto_raw_content(raw_data)
        self.save_gtfs_rt_to_db(feed)
