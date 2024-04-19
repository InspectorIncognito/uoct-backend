from rest_api.models import Shape


def flush_shape_objects():
    Shape.objects.all().delete()
