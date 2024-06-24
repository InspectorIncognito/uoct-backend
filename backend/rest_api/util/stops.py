from rest_api.models import Stop
from velocity.gtfs import GTFSManager


def flush_stops_from_db():
    Stop.objects.all().delete()


def assign_stops_to_segments():
    gtfs_manager = GTFSManager()
    gtfs_manager.assign_stops_to_segments()
