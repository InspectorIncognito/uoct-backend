from django.core.management import BaseCommand, CommandError
from rest_api.models import Shape, Segment, GTFSShape
from shapely.geometry import LineString as shp_LineString
from rest_api.util.gtfs import GTFSShapeManager
from shapely import to_geojson
import geopandas as gpd
from velocity.gtfs import GTFSManager


class Command(BaseCommand):
    help = 'Read the GTFS file to get all the shapes and their direction'

    def handle(self, *args, **options):
        print("Calling get_gtfs_shapes...")
        gtfs_manager = GTFSManager()
        print("GTFS LOADED")
        processed_shapes = gtfs_manager.get_processed_df()
        print("PROCESSED DF:", processed_shapes)
        print('GOT SHAPES')
        gtfs_manager.save_gtfs_shapes_to_db(processed_shapes)
