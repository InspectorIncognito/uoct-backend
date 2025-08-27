import geojson
import overpass

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
    """Executes an Overpass API query and returns the results.
    To update this function to download more data in an structured way, look for the code in the following repo https://github.com/shaberle/traffic-incident-detection/blob/main/codigo/osm.py

    Parameters
    ----------
    query : str
        The Overpass API query to execute.

    Returns
    -------
    dict
        The GeoJSON response from the Overpass API.
    """
    api = overpass.API()
    response = api.get(query, verbosity="geom")
    return geojson.loads(geojson.dumps(response))
