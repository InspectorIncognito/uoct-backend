from rest_api.models import Shape
from geojson.feature import FeatureCollection


def shapes_to_geojson():
    shapes = Shape.objects.all()
    features = []
    for shape in shapes:
        features.extend(shape.to_geojson())
    geojson = FeatureCollection(
        features=features,
    )
    return geojson
