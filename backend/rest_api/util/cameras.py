from rest_api.models import Camera
from rest_api.util.shape import ShapeManager

def flush_cameras_from_db():
    Camera.objects.all().delete()

def assign_cameras_to_segments():
    pass