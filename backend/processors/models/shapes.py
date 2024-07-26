from rest_api.models import Shape
from geojson.feature import FeatureCollection
from django.utils import timezone
from datetime import datetime


def shapes_to_geojson(now: datetime = timezone.localtime()):
    shapes = Shape.objects.all()
    features = []
    for shape in shapes:
        features.extend(shape.to_geojson(now))
    geojson = FeatureCollection(features=features)
    return geojson
