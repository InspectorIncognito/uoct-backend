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

    @staticmethod
    def is_new_feed(feed_timestamp: int) -> bool:
        """Return True (and remember it) only if the feed is newer than the last one stored.

        The feed is republished with the same header timestamp, and the same file can be
        downloaded more than once, so older or equal feeds are skipped.
        """
        if not feed_timestamp:
            return True
        manager = GTFSRTTimestamp.objects.first()
        if manager is None:
            manager = GTFSRTTimestamp.objects.create(last_timestamp="")
        last_timestamp = int(manager.last_timestamp) if manager.last_timestamp else 0
        if feed_timestamp <= last_timestamp:
            return False
        manager.last_timestamp = str(feed_timestamp)
        manager.save()
        return True

    @staticmethod
    def build_new_pulses(feed: gtfs_realtime_pb2.FeedMessage) -> list:
        """GPSPulse objects for the vehicle positions not stored yet.

        A vehicle that did not report again keeps its old position (same plate and
        timestamp) in the next feed, so (license_plate, timestamp) already in the DB,
        or repeated inside the feed, are skipped.
        """
        pulses = {}
        for entity in feed.entity:
            if not entity.HasField("vehicle"):
                continue
            v = entity.vehicle
            if not v.HasField("vehicle"):
                continue
            timestamp = datetime.datetime.fromtimestamp(
                v.timestamp, tz=datetime.timezone.utc
            )
            key = (v.vehicle.license_plate, timestamp)
            if key in pulses:
                continue
            gps = v.position
            pulses[key] = GPSPulse(
                route_id=v.trip.route_id if v.trip.HasField("route_id") else None,
                direction=v.trip.direction_id if v.trip.HasField("direction_id") else None,
                latitude=gps.latitude,
                longitude=gps.longitude,
                bearing=gps.bearing,
                license_plate=v.vehicle.license_plate,
                timestamp=timestamp,
            )
        if not pulses:
            return []

        timestamps = [ts for _, ts in pulses]
        existing = set(
            GPSPulse.objects.filter(
                timestamp__gte=min(timestamps), timestamp__lte=max(timestamps)
            ).values_list("license_plate", "timestamp")
        )
        return [pulse for key, pulse in pulses.items() if key not in existing]

    def save_gtfs_rt_to_db(self, feed: gtfs_realtime_pb2.FeedMessage):
        if not self.is_new_feed(self.get_timestamp_from_feed(feed)):
            print("Ignoring duplicated GTFS-RT")
            return

        new_pulses = self.build_new_pulses(feed)
        GPSPulse.objects.bulk_create(new_pulses, batch_size=2000)
        print(f"Saved {len(new_pulses)} new GPS pulses of {len(feed.entity)} entities.")

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
