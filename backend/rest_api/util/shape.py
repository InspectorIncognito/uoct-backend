from typing import Dict, List

import geopandas as gpd
import pandas as pd
from geojson import Feature, FeatureCollection, LineString
from rest_api.models import (
    Alert,
    HistoricSpeed,
    Segment,
    Services,
    Shape,
    Speed,
    Stop,
    TrafficSignal,
)
from rest_api.util.hmm.hmm import precompute_axes_caches
from shapely.geometry import LineString as shp_LineString
from velocity.constants import DEG_PI, DEG_PI_HALF


class ShapeManager:
    def __init__(self):
        self.shapes = Shape.objects.all()
        self.spatial_indices = dict()
        self.direction_caches = dict()
        self.segment_caches = dict()

    def get_bbox(self):
        bbox_min_lat = DEG_PI_HALF
        bbox_max_lat = -DEG_PI_HALF
        bbox_min_lon = DEG_PI
        bbox_max_lon = -DEG_PI
        for shape in self.shapes:
            bbox = shape.get_bbox()
            bbox_min_lon = min(bbox_min_lon, bbox[0])
            bbox_min_lat = min(bbox_min_lat, bbox[1])
            bbox_max_lon = max(bbox_max_lon, bbox[2])
            bbox_max_lat = max(bbox_max_lat, bbox[3])
        return [bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat]

    def get_segments(self) -> Dict[int, List[Segment]]:
        return {shape.pk: list(shape.get_segments()) for shape in self.shapes}

    def get_segments_gdf(self):
        """Return a dictionary of GeoDataFrames, one per axis, concatenating both directions.

        For example, "Eje Alameda_0" and "Eje Alameda_1" are concatenated into a single
        GeoDataFrame with key "Eje Alameda", preserving all segments from both directions.
        """
        segments_dict: Dict[str, gpd.GeoDataFrame] = {}
        for shape in self.shapes:
            name = shape.name
            axis_name = name.rsplit("_", 1)[0] if "_" in name else name
            segments_gdf = shape.get_segments_gdf()

            if segments_gdf.empty:
                continue

            # Concatenate segments from both directions of the same axis
            if axis_name in segments_dict:
                segments_dict[axis_name] = gpd.GeoDataFrame(
                    pd.concat(
                        [segments_dict[axis_name], segments_gdf], ignore_index=True
                    ),
                    crs=segments_gdf.crs,
                )
            else:
                segments_dict[axis_name] = segments_gdf

        return segments_dict

    def shapes_cache(self, segments_gdfs: Dict[str, gpd.GeoDataFrame] = None):
        if segments_gdfs is None:
            segments_gdfs = self.get_segments_gdf()
        self.spatial_indices, self.direction_caches, self.segment_caches = (
            precompute_axes_caches(segments_gdfs)
        )

    def get_distances(self):
        shape_dict = {}
        for shape in self.shapes:
            shape_dict[str(shape.pk)] = shape.get_distance()
        return shape_dict

    def to_geojson(self):
        return FeatureCollection(
            features=[feature.to_geojson() for feature in self.shapes]
        )

    def get_all_services(self):
        services = set()
        for shape in self.shapes:
            segments = shape.get_segments()
            for segment in segments:
                seg_services = segment.get_services()
                if seg_services is None:
                    # Simplemente lo ignoramos
                    continue
                services.update(seg_services)
        return services

    def get_buffered_shape(self):
        segment_data = self.get_segments()
        features = []
        for shape in segment_data:
            for segment in segment_data[shape]:
                geometry = segment.geometry
                features.append(Feature(geometry=LineString(coordinates=geometry)))
        gdf = gpd.GeoDataFrame.from_features(features)
        gdf["geometry"] = gdf["geometry"].buffer(distance=0.0005, cap_style="flat")
        polygon_gdf = gdf.union_all()
        return polygon_gdf


def flush_shape_objects():
    """Safely clear all shape-related data in dependency order to avoid FK type issues.

    Deletes dependent records first (Speed, HistoricSpeed, Alert, Services, Stop),
    then Segments, and finally Shapes. TrafficSignal is NOT deleted here because
    signals are saved per-axis before segments and should persist across rebuilds.

    Use flush_traffic_signals() separately if you need to clear signals.
    """
    try:
        # Delete dependents referencing Segment first
        Speed.objects.all().delete()
        HistoricSpeed.objects.all().delete()
        Alert.objects.all().delete()
        Services.objects.all().delete()
        Stop.objects.all().delete()
        # Note: TrafficSignal is NOT deleted here - it's managed separately

        # Then delete segments and shapes
        Segment.objects.all().delete()
        Shape.objects.all().delete()
        print(
            "Flushed shapes and related objects (segments, speeds, alerts, services, stops)"
        )
    except Exception as e:
        print(f"Error flushing shape-related objects: {e}")
