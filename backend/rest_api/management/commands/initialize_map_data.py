from django.core.management import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Runs the pipeline for retrieving the map's data
        # This is, for every shape
        print("Calling initialize_map_data...")

        # Create Shapes and Segments
        call_command('process_shape_data')
        # Create GTFSShapes
        call_command('get_gtfs_shapes')
        # Assign services to segments
        call_command('assign_routes_to_segments')
        # Set alert threshold value
        call_command('set_alert_threshold')

        print("initialize_map_data finished.")
