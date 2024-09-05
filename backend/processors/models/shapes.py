from rest_api.models import Shape
from geojson.feature import FeatureCollection
from rest_api.util.alert import get_active_alerts


def shapes_to_geojson():
    shapes = Shape.objects.all()
    features = []
    for shape in shapes:
        features.extend(shape.to_geojson())
    geojson = FeatureCollection(features=features)
    active_alerts = get_active_alerts()
    output_data = dict(
        geojson=geojson,
        alerts=active_alerts
    )
    return output_data
