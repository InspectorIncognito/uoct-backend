from django.core.management.base import BaseCommand
from processors.osm.process import process_single_axis

from rest_api.models import Axles


class Command(BaseCommand):
    help = "Add a single axis without deleting existing data"

    def add_arguments(self, parser):
        parser.add_argument(
            "axis_name",
            type=str,
            help="Name of the axis to add (must exist in Axles table or EJES_PRINCIPALES)",
        )
        parser.add_argument(
            "--distance_threshold",
            type=float,
            default=500.0,
            help="Distance in meters to segment shapes (default: 500.0). "
            "When --use_traffic_signals is enabled, this is used as fallback distance.",
        )
        parser.add_argument(
            "--no_traffic_signals",
            action="store_true",
            help="Disable traffic signal-based segmentation, use fixed distance only",
        )

    def handle(self, *args, **options):
        axis_name = options["axis_name"]
        distance_threshold = options.get("distance_threshold", 500.0)
        use_traffic_signals = not options.get("no_traffic_signals", False)

        self.stdout.write(f"Adding axis: {axis_name}")
        if use_traffic_signals:
            self.stdout.write(
                f"  Segmentation mode: Traffic signals with {distance_threshold}m fallback"
            )
        else:
            self.stdout.write(
                f"  Segmentation mode: Fixed distance ({distance_threshold}m)"
            )

        # First check if axis exists in Axles table
        try:
            axle = Axles.objects.get(name=axis_name)
            self.stdout.write(
                self.style.SUCCESS(f"Found axis in database: {axis_name}")
            )
        except Axles.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"Axis '{axis_name}' not found in database. "
                    f"Run 'python manage.py create_axles_db' first to populate Axles table."
                )
            )
            return

        try:
            # Process just this axis
            process_single_axis(
                axis_name=axis_name,
                distance_threshold=distance_threshold,
                use_traffic_signals=use_traffic_signals,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Successfully added axis: {axis_name}")
            )

            # Execute map matching for the new axis
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("Starting map matching for new axis...")
            self.stdout.write("=" * 50 + "\n")

            # Assign routes to segments
            self.stdout.write("Assigning routes to segments...")
            from rest_api.util.services import assign_routes_to_segments

            assign_routes_to_segments(shape_name=axis_name)
            self.stdout.write(self.style.SUCCESS("Routes assigned successfully"))

            # Assign stops to segments
            self.stdout.write("Assigning stops to segments...")
            from rest_api.util.stops import assign_stops_to_segments

            assign_stops_to_segments(shape_name=axis_name)
            self.stdout.write(self.style.SUCCESS("Stops assigned successfully"))

            # Assign cameras to segments
            self.stdout.write("Assigning cameras to segments...")
            from rest_api.util.cameras import assign_cameras_to_segments

            assign_cameras_to_segments(shape_name=axis_name)
            self.stdout.write(self.style.SUCCESS("Cameras assigned successfully"))

            self.stdout.write("\n" + "=" * 50)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Axis '{axis_name}' fully processed with all map matching complete!"
                )
            )
            self.stdout.write("=" * 50 + "\n")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error adding axis '{axis_name}': {str(e)}")
            )
            raise
