from django.core.management import BaseCommand

from rest_api.util.cameras import assign_cameras_to_segments, flush_cameras_from_db


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--shape_name",
            type=str,
            default=None,
            help='Process only segments for this specific shape (e.g., "Eje Alameda")',
        )

    def handle(self, *args, **options):
        shape_name = options.get("shape_name")
        print(
            "Calling assign_cameras_to_segments command..."
            + (f" for shape: {shape_name}" if shape_name else "")
        )
        if shape_name is None:
            flush_cameras_from_db()
        assign_cameras_to_segments(shape_name=shape_name)
