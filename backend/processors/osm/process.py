from geojson.feature import FeatureCollection
import geopandas as gpd
from typing import List


# Separa el geojson en N linestring, con N el número de calles aisladas (alameda ida, alameda vuelta == 2)
def split_geojson_by_shape(df: gpd.GeoDataFrame) -> List[gpd.GeoDataFrame]:
    output = []
    aux_df = df.copy()

    while not aux_df.empty:
        current_df = aux_df.copy()
        current_direction = [current_df.iloc[0]]
        dir_len = len(current_direction)
        i = 0
        while i < dir_len:
            new_aux_df = []
            curr_geom = current_direction[i].geometry
            for feature in current_df.itertuples():
                comp_geom = feature.geometry
                if comp_geom in current_direction or curr_geom == comp_geom:
                    continue
                if curr_geom.touches(comp_geom):
                    current_direction.append(comp_geom)
                    dir_len += 1
                else:
                    new_aux_df.append(feature)
            current_df = gpd.GeoDataFrame.from_features(FeatureCollection(features=new_aux_df))
            i += 1
        output.append(gpd.GeoDataFrame.from_features(current_direction))
        aux_df = current_df.copy()
    return output


def segment_shapes(shapes_gdf):
    # TODO: completar la función
    return gpd.GeoDataFrame()


def save_shapes_and_segments(segmented_shapes_gdf):
    # TODO: completar la función
    return gpd.GeoDataFrame()


def process_geojson(geojson_data):
    splitted_gdf = split_geojson_by_shape(geojson_data)
    segmented_shapes = segment_shapes(splitted_gdf)