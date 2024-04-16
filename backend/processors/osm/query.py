import overpass
import geojson
import geopandas as gpd

ALAMEDA_QUERY = """
    rel(1674530);
    map_to_area->.santiago;
    (
      way(area.santiago)[highway="primary"][name="Avenida Providencia"];
      way(area.santiago)[highway="primary"][name="Avenida Nueva Providencia"];
      way(176118014);
      way(area.santiago)[highway="primary"][name="Avenida Libertador Bernardo O'Higgins"];
      way(area.santiago)[highway="primary"][name="Avenida Apoquindo"];
    );
"""


def overpass_query(query):
    api = overpass.API()
    response = api.get(query, verbosity='geom')
    return geojson.loads(geojson.dumps(response))


# Separa el geojson en N linestring, con N el número de calles aisladas (alameda ida, alameda vuelta == 2)
def split_geojson_by_shape(geojson_data):
    # TODO: completar la función
    return gpd.GeoDataFrame()


def segment_shapes(shapes_gdf):
    # TODO: completar la función
    return gpd.GeoDataFrame()


def save_shapes_and_segments(segmented_shapes_gdf):
    # TODO: completar la función
    return gpd.GeoDataFrame()


def process_geojson(geojson_data):
    splitted_gdf = split_geojson_by_shape(geojson_data)
    segmented_shapes = segment_shapes(splitted_gdf)


data = overpass_query(ALAMEDA_QUERY)
process_geojson(data)
