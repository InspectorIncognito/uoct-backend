from django.core.management import BaseCommand
from gtfs_rt.utils import update_gtfs_data


class Command(BaseCommand):
    help = "Update GTFS shapes and stops using the current GTFS URL."

    def handle(self, *args, **options):
        """Update GTFS shapes and stops using the current GTFS URL."""
        try:
            update_gtfs_data()
        except Exception as e:
            print(f"Error durante la actualización del GTFS: {str(e)}")
            raise
