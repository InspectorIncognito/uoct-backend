from django.core.management.base import BaseCommand
from processors.osm.process import process_osm_queries
from rest_api.models import Segment, Shape


class Command(BaseCommand):
    help = "Process OSM queries to create Shapes and Segments"

    def add_arguments(self, parser):
        parser.add_argument(
            "--distance_threshold",
            type=float,
            default=500.0,
            help="Distance in meters to segment shapes (default: 500.0)",
        )
        parser.add_argument(
            "--use_fixtures",
            action="store_true",
            help="Use fixture data instead of downloading from OSM",
        )

    def handle(self, *args, **options):
        self.stdout.write("Processing OSM queries...")

        distance_threshold = options.get("distance_threshold", 500.0)
        use_fixtures = options.get("use_fixtures", False)

        try:
            process_osm_queries(
                distance_threshold=distance_threshold, use_fixtures=use_fixtures
            )
            self.stdout.write(self.style.SUCCESS("Successfully processed OSM queries"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error processing OSM queries: {str(e)}")
            )
