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
            help="Distance in meters to segment shapes (default: 500.0). "
            "When --use_traffic_signals is enabled, this is used as fallback distance.",
        )
        parser.add_argument(
            "--use_fixtures",
            action="store_true",
            help="Use fixture data instead of downloading from OSM",
        )
        parser.add_argument(
            "--use_traffic_signals",
            action="store_true",
            default=True,
            help="Segment by traffic signals at relevant intersections with "
            "fallback to distance_threshold (default: True)",
        )
        parser.add_argument(
            "--no_traffic_signals",
            action="store_true",
            help="Disable traffic signal-based segmentation, use fixed distance only",
        )

    def handle(self, *args, **options):
        self.stdout.write("Processing OSM queries...")

        distance_threshold = options.get("distance_threshold", 500.0)
        use_fixtures = options.get("use_fixtures", False)

        # Handle traffic signals flag (--no_traffic_signals takes precedence)
        use_traffic_signals = not options.get("no_traffic_signals", False)

        if use_traffic_signals:
            self.stdout.write(
                f"  Segmentation mode: Traffic signals with {distance_threshold}m fallback"
            )
        else:
            self.stdout.write(
                f"  Segmentation mode: Fixed distance ({distance_threshold}m)"
            )

        try:
            process_osm_queries(
                distance_threshold=distance_threshold,
                use_fixtures=use_fixtures,
                use_traffic_signals=use_traffic_signals,
            )
            self.stdout.write(self.style.SUCCESS("Successfully processed OSM queries"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error processing OSM queries: {str(e)}")
            )
