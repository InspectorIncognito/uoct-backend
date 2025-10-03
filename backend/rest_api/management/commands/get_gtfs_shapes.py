import geopandas as gpd
from django.core.management import BaseCommand, CommandError
from rest_api.models import GTFSShape, Segment, Shape
from rest_api.util.gtfs import GTFSShapeManager
from shapely import to_geojson
from shapely.geometry import LineString as shp_LineString
from velocity.gtfs import GTFSManager


class Command(BaseCommand):
    help = "Read the GTFS file to get all the shapes and their direction"

    def handle(self, *args, **options):
        print("Calling get_gtfs_shapes command...")
        gtfs_manager = GTFSManager()
        processed_shapes = gtfs_manager.get_processed_df()
        # Save df to a csv file for debugging
        processed_shapes.to_csv("processed_shapes.csv", index=False)
        # Save to DB
        gtfs_manager.save_gtfs_shapes_to_db(processed_shapes)
