from rest_api.models import Segment, Services
from geojson import FeatureCollection
import geopandas as gpd
import pandas as pd
from geojson import Point, LineString, Feature, FeatureCollection


class SegmentManager:
    def __init__(self):
        self.segments = Segment.objects.all()

    def segments_to_gdf(self):
        segments = []
        for segment in self.segments:
            segments.append(
                Feature(geometry=LineString(coordinates=segment.geometry), properties={"segment_pk": segment.pk})
            )
        segments = FeatureCollection(features=segments)
        return segments

    def get_services_for_each_segment(self, geojson_data: FeatureCollection):
        gdf = gpd.GeoDataFrame.from_features(geojson_data, crs='epsg:4326')
        for segment in self.segments:
            mask = gpd.GeoDataFrame.from_features([segment.to_geojson()], crs='epsg:4326')
            masked = gpd.clip(gdf, mask)
            shapes = masked['shape_id'].tolist()
            print(f'In {segment} the services are: {shapes}')

    def assign_stops_for_each_segment(self, stops_df: pd.DataFrame):
        # stop_id, lat, lon
        stops = []
        for stop in stops_df.iterrows():
            stops.append(
                Feature(geometry=Point(stop["stop_lat"], stops["stop_lon"]), properties={"stop_id": stops["stop_id"]})
            )
        stops = FeatureCollection(features=stops)
        stops_gdf = gpd.GeoDataFrame.from_features(stops)
        segments_gdf = self.segments_to_gdf()

        buffer_distance = 0.0001
        segments_gdf["buffer"] = segments_gdf.geometry.apply(lambda x: x.buffer(buffer_distance))

        for idx, line in segments_gdf.iterrows():
            buffer = line["buffer"]
            points_within_buffer = stops_gdf[stops_gdf.geometry.within(buffer)]
            for point in points_within_buffer:
                print(point)

        return


