from django.core.management import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--use_fixture', action='store_true')

    def handle(self, *args, **options):
        # Runs the pipeline for retrieving the map's data
        # This is, for every shape
        print("Calling initialize_map_data command...")

        # Create Shapes and Segments
        if not options['use_fixture']:
            call_command('process_shape_data')
        else:
            call_command('process_fixture_data')
        # Create GTFSShapes
        call_command('get_gtfs_shapes')
        # Assign services to segments
        call_command('assign_routes_to_segments')
        # Set alert threshold value
        call_command('set_alert_threshold')

        print("initialize_map_data finished.")
