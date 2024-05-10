from rest_api.models import GTFSShape


def flush_gtfs_shape_objects():
    try:
        GTFSShape.objects.all().delete()
    except:
        pass
