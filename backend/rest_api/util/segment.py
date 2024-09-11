from rest_api.models import Segment, Services, Stop
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
        for _, stop in stops_df.iterrows():
            stop_lat = stop['stop_lat']
            stop_lon = stop['stop_lon']
            stop_id = stop['stop_id']
            stops.append(
                Feature(geometry=Point(coordinates=[stop_lon, stop_lat]), properties={"stop_id": stop_id})
            )
        stops = FeatureCollection(features=stops)
        segments = self.segments_to_gdf()
        stops_gdf = gpd.GeoDataFrame.from_features(stops, crs='epsg:4326')
        segments_gdf = gpd.GeoDataFrame.from_features(segments, crs='epsg:4326')

        buffer_distance = 0.0001
        segments_gdf["buffer"] = segments_gdf.geometry.apply(
            lambda x: x.buffer(buffer_distance, cap_style='flat', join_style="bevel"))

        for idx, line in segments_gdf.iterrows():
            buffer = line["buffer"]
            stops_inside_buffer = stops_gdf[stops_gdf.geometry.within(buffer)]
            for _, stop in stops_inside_buffer.iterrows():
                stop_data = {
                    "segment": Segment.objects.get(pk=line["segment_pk"]),
                    "stop_id": stop['stop_id'],
                    "latitude": stop['geometry'].coords[0][1],
                    "longitude": stop['geometry'].coords[0][0]
                }
                Stop.objects.create(**stop_data)
