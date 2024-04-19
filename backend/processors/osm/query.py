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
