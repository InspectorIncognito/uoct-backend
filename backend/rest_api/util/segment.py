from rest_api.models import Segment, Services
from geojson import FeatureCollection
import geopandas as gpd


class SegmentManager:
    def __init__(self):
        self.segments = Segment.objects.all()

    def get_services_for_each_segment(self, geojson_data: FeatureCollection):
        gdf = gpd.GeoDataFrame.from_features(geojson_data, crs='epsg:4326')
        for segment in self.segments:
            mask = gpd.GeoDataFrame.from_features([segment.to_geojson()], crs='epsg:4326')
            masked = gpd.clip(gdf, mask)
            shapes = masked['shape_id'].tolist()
            print(f'In {segment} the services are: {shapes}')
