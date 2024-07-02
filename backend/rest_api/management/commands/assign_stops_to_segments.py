from django.core.management import BaseCommand
from rest_api.util.stops import assign_stops_to_segments, flush_stops_from_db


class Command(BaseCommand):
    def handle(self, *args, **options):
        flush_stops_from_db()
        assign_stops_to_segments()
