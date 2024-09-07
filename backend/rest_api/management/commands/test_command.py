from django.core.management import BaseCommand

from processors.osm.process import split_geojson_by_shape, merge_shape, segment_shape_by_distance
from processors.osm.query import ALAMEDA_QUERY, overpass_query
from rest_api.util.alert import update_alerts, TranSappSiteManager, create_alerts
from rest_api.models import Speed
from django.utils import timezone
import geopandas as gpd
from geojson import FeatureCollection, Feature


class Command(BaseCommand):
    help = 'Debug command'

    def handle(self, *args, **options):
        print("Calling create_alerts command...")
        distance_threshold = 500.0
        query_data = gpd.GeoDataFrame.from_features(overpass_query(ALAMEDA_QUERY))
        features = []
        for g in query_data['geometry']:
            features.append(Feature(geometry=g))
        print(FeatureCollection(features=features))

        exit()
        print("splitting by shape..")
        splitted_geojson = split_geojson_by_shape(query_data)
        segmented_shapes = []
        print(f"Got {len(splitted_geojson)} different shapes")
        exit()
        for idx, feature in enumerate(splitted_geojson):
            merged = merge_shape(feature)
            segmented = segment_shape_by_distance(merged, distance_threshold, distance_algorithm='haversine')
            segmented_shapes.append(segmented)
