from django.test import TestCase
from google.transit import gtfs_realtime_pb2

from gtfs_rt.models import GPSPulse
from gtfs_rt.processors.manager import GTFSRTManager
from rest_api.models import GTFSRTTimestamp


def make_feed(header_ts, vehicles):
    """vehicles: list of (license_plate, vehicle_timestamp)."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = header_ts
    for i, (plate, ts) in enumerate(vehicles):
        entity = feed.entity.add()
        entity.id = str(i)
        entity.vehicle.vehicle.license_plate = plate
        entity.vehicle.timestamp = ts
        entity.vehicle.trip.route_id = "T101"
        entity.vehicle.trip.direction_id = 0
        entity.vehicle.position.latitude = -33.44
        entity.vehicle.position.longitude = -70.65
        entity.vehicle.position.bearing = 90
    return feed


class TestGTFSRTDedup(TestCase):
    def setUp(self):
        GTFSRTTimestamp.objects.create(last_timestamp="")
        self.manager = GTFSRTManager(gtfs_rt_url="http://unused")

    def test_same_feed_twice_is_stored_once(self):
        feed = make_feed(1000, [("AAAA11", 990), ("BBBB22", 995)])
        self.manager.save_gtfs_rt_to_db(feed)
        self.manager.save_gtfs_rt_to_db(feed)
        self.assertEqual(2, GPSPulse.objects.count())

    def test_older_feed_is_ignored(self):
        self.manager.save_gtfs_rt_to_db(make_feed(1000, [("AAAA11", 990)]))
        self.manager.save_gtfs_rt_to_db(make_feed(940, [("AAAA11", 930)]))
        self.assertEqual(1, GPSPulse.objects.count())
        self.assertEqual("1000", GTFSRTTimestamp.objects.first().last_timestamp)

    def test_vehicle_without_new_report_is_not_repeated(self):
        self.manager.save_gtfs_rt_to_db(make_feed(1000, [("AAAA11", 990), ("BBBB22", 995)]))
        # Next feed: AAAA11 reported again, BBBB22 kept its old position
        self.manager.save_gtfs_rt_to_db(make_feed(1060, [("AAAA11", 1050), ("BBBB22", 995)]))
        self.assertEqual(3, GPSPulse.objects.count())
        self.assertEqual(1, GPSPulse.objects.filter(license_plate="BBBB22").count())

    def test_repeated_vehicle_inside_feed(self):
        self.manager.save_gtfs_rt_to_db(make_feed(1000, [("AAAA11", 990), ("AAAA11", 990)]))
        self.assertEqual(1, GPSPulse.objects.count())
