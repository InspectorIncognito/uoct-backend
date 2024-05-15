from django.core.management import BaseCommand
from rest_api.util.services import assign_routes_to_segments, flush_services_from_db


class Command(BaseCommand):
    help = 'With Shapes, Segments and GTFSSegments stored in the DB, this command assigns each route to a segment'

    def handle(self, *args, **options):
        flush_services_from_db()
        print("DB flushed.")
        assign_routes_to_segments()
        print("Routes assigned to segments")
