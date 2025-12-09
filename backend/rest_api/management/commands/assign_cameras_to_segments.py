from django.core.management import BaseCommand
from rest_api.util.cameras import assign_cameras_to_segments, flush_cameras_from_db


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Calling assign_cameras_to_segments command...")
        flush_cameras_from_db()
        assign_cameras_to_segments()
