import geopandas as gpd
from typing import List
from geojson.feature import Feature, FeatureCollection
from processors.geometry.point import Point as p
from shapely.geometry import Point
from shapely.ops import linemerge, split
from shapely.geometry import LineString as shp_LineString
from rest_api.util.shape import flush_shape_objects
from rest_api.models import Shape, Segment
from processors.osm.query import overpass_query, ALAMEDA_QUERY


# Separa el geojson en N linestring, con N el número de calles aisladas (alameda ida, alameda vuelta == 2)
def split_geojson_by_shape(df: gpd.GeoDataFrame) -> List[gpd.GeoDataFrame]:
    output = []
    aux_df = df.copy()

    while not aux_df.empty:
        current_df = aux_df.copy()
        current_direction = [current_df.iloc[0]]
        aux_geom = [current_direction[0].geometry]
        dir_len = len(current_direction)
        i = 0
        while i < dir_len:
            new_aux_df = []
            curr_geom = aux_geom[i]
            for feature in current_df.itertuples():
                comp_geom = feature.geometry
                if comp_geom in aux_geom or curr_geom == comp_geom:
                    continue
                if curr_geom.touches(comp_geom):
                    current_direction.append(feature)
                    aux_geom.append(comp_geom)
                    dir_len += 1
                else:
                    new_aux_df.append(feature)
            features = FeatureCollection(features=[Feature(geometry=f.geometry) for f in new_aux_df])
            current_df = gpd.GeoDataFrame.from_features(features)
            i += 1
        output.append(gpd.GeoDataFrame.from_features(
            FeatureCollection(features=[Feature(geometry=f.geometry) for f in current_direction])))
        aux_df = current_df.copy()
    return output


def merge_shape(gdf: gpd.GeoDataFrame) -> shp_LineString:
    merged = linemerge(gdf["geometry"].unary_union)
    return merged


def segment_shape_by_distance(shape: shp_LineString, distance_threshold: float = 500,
                              distance_algorithm: str = 'euclidean'):
    if distance_threshold <= 0:
        raise ValueError("distance_threshold must be greater than 0.")
    output_linestrings = []
    geom = shape
    counter = 0
    geom_len = len(geom.coords)
    while counter < geom_len:
        previous_point = None
        distance_accum = 0
        counter = 0
        for point in geom.coords:
            point_obj = Point(point[0], point[1])
            if previous_point is None:
                previous_point = point_obj
                counter += 1
                continue
            previous_p_aux = p(previous_point.x, previous_point.y)
            actual_p_aux = p(point[0], point[1])
            distance_accum += actual_p_aux.distance(previous_p_aux, algorithm=distance_algorithm)
            if distance_accum >= distance_threshold:
                splitted = split(geom, point_obj).geoms
                output_linestrings.append(splitted[0])
                if len(splitted) == 2:
                    geom = splitted[1]
                    geom_len = len(geom.coords)
                else:
                    geom_len = 0
                    geom = None
                break
            else:
                counter += 1
                previous_point = point_obj
    if geom is not None:
        output_linestrings.append(geom)
    return output_linestrings


def save_segmented_shape_to_db(segmented_shape: List[shp_LineString], shape_name: str):
    shape = Shape.objects.create(**{"name": shape_name})
    print("Created shape", shape)
    for sequence, segment in enumerate(segmented_shape):
        shape.add_segment(sequence=sequence, geometry=segment)
        print("Created segment", segment)


def save_all_segmented_shapes_to_db(segmented_shapes: List[List[shp_LineString]]):
    flush_shape_objects()
    for idx, segmented_shape in enumerate(segmented_shapes):
        save_segmented_shape_to_db(segmented_shape, shape_name=f"shape_{idx}")


# Crea la consulta, separa los distintos shapes, los mergea y divide en segmentos de 'distance_threshold' metros."
# Almacena toda la información en la db
def process_shape_data(distance_threshold: float = 500):
    query_data = gpd.GeoDataFrame.from_features(overpass_query(ALAMEDA_QUERY))
    splitted_geojson = split_geojson_by_shape(query_data)
    segmented_shapes = []
    for idx, feature in enumerate(splitted_geojson):
        merged = merge_shape(feature)
        segmented = segment_shape_by_distance(merged, distance_threshold, distance_algorithm='haversine')
        segmented_shapes.append(segmented)
    save_all_segmented_shapes_to_db(segmented_shapes)
