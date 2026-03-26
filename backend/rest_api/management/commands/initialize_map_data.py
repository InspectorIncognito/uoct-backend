from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--use_fixture", action="store_true")

    def handle(self, *args, **options):
        # Runs the pipeline for retrieving the map's data
        # This is, for every shape
        print("Calling initialize_map_data command...")

        # Create Shapes and Segments
        if not options["use_fixture"]:
            # Problema con la función split_geojson_by_shape en osm/process.py. No esta captando bien las direcciones.
            call_command("create_axles_db")
            call_command("process_osm_queries")
        else:
            call_command("process_fixture_data")
        # Create GTFSShapes
        call_command("get_gtfs_shapes")
        # Assign services to all segments
        call_command("assign_routes_to_segments")
        # Assign stops to all segments
        call_command("assign_stops_to_segments")
        # Assign cameras to all segments
        call_command("assign_cameras_to_segments")
        # Set alert threshold value
        call_command("set_alert_threshold")
        # Set gtfs rt timestamp manager
        call_command("set_gtfs_rt_timestamp_manager")

        print("initialize_map_data command finished.")
