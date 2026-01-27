from velocity.gtfs import GTFSManager

from rest_api.models import Shape, Stop


def flush_stops_from_db():
    Stop.objects.all().delete()


def assign_stops_to_segments(shape_name=None):
    # Clear stops for specific shape if provided
    if shape_name is not None:
        shapes = Shape.objects.filter(name__startswith=f"{shape_name}_")
        for shape in shapes:
            Stop.objects.filter(segment__shape=shape).delete()
        print(f"Flushed stops for shape: {shape_name}")

    gtfs_manager = GTFSManager()
    gtfs_manager.assign_stops_to_segments(shape_name=shape_name)
