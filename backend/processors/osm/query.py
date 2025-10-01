import time
from typing import Dict, List

import geojson
import overpass
import requests
from jinja2 import Template

# Overpass API template for querying OSM data
OVERPASS_TEMPLATE = Template(
    """rel({{ relation_id }});
map_to_area->.target_area;
way(area.target_area)
  [highway~"^(primary|secondary)$"]
  [name~"^({% for street in streets %}{{ street }}{% if not loop.last %}|{% endif %}{% endfor %})$"];
"""
)

# Santiago's main traffic axes configuration
EJES_PRINCIPALES = {
    "Eje Alameda": {
        "city": "Provincia de Santiago",
        "streets": [
            "Avenida Libertador Bernardo O'Higgins",
            "Avenida Providencia",
            "Avenida Nueva Providencia",
            "Avenida Apoquindo",
        ],
    },
    "Eje Vicuña Mackenna": {
        "city": "Provincia de Santiago",
        "streets": [
            "Avenida Vicuña Mackenna",
            "Avenida Vicuña Mackenna Poniente",
            "Avenida Vicuña Mackenna Oriente",
        ],
    },
    "Eje Gran Avenida": {
        "city": "Provincia de Santiago",
        "streets": ["Gran Avenida José Miguel Carrera", "San Diego", "Nataniel Cox"],
    },
    "Eje independencia": {
        "city": "Provincia de Santiago",
        "streets": ["Avenida Independencia"],
    },
    "Eje Santa Rosa": {
        "city": "Provincia de Santiago",
        "streets": ["Avenida Santa Rosa", "San Francisco"],
    },
    "Eje Irarrázaval": {
        "city": "Provincia de Santiago",
        "streets": [
            "Avenida Irarrázaval",
            "Avenida Larraín",
            "Avenida Alcalde Fernando Castillo Velasco",
        ],
    },
    "Eje La Florida - Los Leones": {
        "city": "Provincia de Santiago",
        "streets": [
            "Avenida La Florida",
            "Avenida Macul",
            "Avenida José Pedro Alessandri",
            "Avenida Chile España",
            "General José Artigas",
            "Avenida Los Leones",
        ],
    },
    "Eje 5 de Abril - Matta": {
        "city": "Provincia de Santiago",
        "streets": [
            "Avenida 5 de Abril",
            "Avenida Simón Bolívar",
            "Arica",
            "Avenida Almirante Blanco Encalada",
            "Avenida Tupper",
            "Plaza Ercilla",
            "Avenida Manuel Antonio Matta",
            "Avenida Grecia",
        ],
    },
}


def get_axis_config(axis_name: str) -> dict:
    """Get configuration for a specific axis.

    Parameters
    ----------
    axis_name : str
        Name of the axis

    Returns
    -------
    dict
        Configuration dictionary for the axis

    Raises
    ------
    KeyError
        If axis is not found
    """
    if axis_name not in EJES_PRINCIPALES:
        raise KeyError(f"Axis '{axis_name}' not found in configuration")
    return EJES_PRINCIPALES[axis_name]


class OSMDownloader:
    """Handles downloading and processing of OSM data."""

    def __init__(self, user_agent: str = "santiago-axes-downloader"):
        """Initialize the OSM downloader.

        Parameters
        ----------
        user_agent : str
            User agent string for API requests
        """
        self.user_agent = user_agent

    def get_relation_id(self, place_name: str, country: str = "Chile") -> int:
        """Get the OSM relation ID for a given place.

        Parameters
        ----------
        place_name : str
            The name of the place to search for.
        country : str, optional
            The country to restrict the search to, by default "Chile".

        Returns
        -------
        int
            The OSM relation ID if found.

        Raises
        ------
        Exception
            If the place is not found or has no relation ID.
        """
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": f"{place_name}, {country}",
            "format": "json",
            "polygon": 0,
            "addressdetails": 0,
        }

        try:
            r = requests.get(
                url, params=params, headers={"User-Agent": self.user_agent}
            )
            r.raise_for_status()
            results = r.json()

            for res in results:
                if res["osm_type"] == "relation":
                    return int(res["osm_id"])

            raise Exception(f"Place '{place_name}' not found or has no relation ID.")

        except requests.RequestException as e:
            raise Exception(f"Error connecting to Nominatim API: {e}")

    def build_overpass_query(self, place: str, streets: List[str]) -> str:
        """Build an Overpass API query for a specific city, highway type, and list of streets.

        Parameters
        ----------
        place : str
            The name of the place to search in.
        streets : List[str]
            The names of the streets to include in the query.

        Returns
        -------
        str
            The Overpass API query as a string.

        Raises
        ------
        Exception
            If unable to build the query.
        """
        print(f"Building Overpass query ...")

        try:
            relation_id = self.get_relation_id(place)

            return OVERPASS_TEMPLATE.render(relation_id=relation_id, streets=streets)

        except Exception as e:
            print(f"Error building query: {e}")
            raise

    def execute_query(self, query: str, retries: int = 3) -> Dict:
        """Execute an Overpass API query and return the results.

        Parameters
        ----------
        query : str
            The Overpass API query to execute.
        retries : int, optional
            Number of retry attempts if the query fails, by default 3.

        Returns
        -------
        Dict
            The GeoJSON response from the Overpass API.

        Raises
        ------
        Exception
            If all retry attempts fail.
        """
        for attempt in range(retries):
            try:
                api = overpass.API(timeout=180 * (attempt + 1))
                # api.get adds [out:json]; at the beginning and "out geom;" at the end
                response = api.get(query, verbosity="geom")
                return geojson.loads(geojson.dumps(response))

            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print("All retry attempts failed.")
                    raise
