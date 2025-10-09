from django.core.management import BaseCommand
from rest_api.util.traffic_signals import assign_traffic_signals_to_segments, flush_traffic_signals_from_db


class Command(BaseCommand):
    help = 'With Shapes, Segments and GTFSSegments stored in the DB, this command assigns each traffic signal to a segment'

    def handle(self, *args, **options):
        print("Calling assign_traffic_signals_to_segments command...")
        flush_traffic_signals_from_db()
        print("DB flushed.")
        assign_traffic_signals_to_segments()
        print("Traffic signals assigned to segments")