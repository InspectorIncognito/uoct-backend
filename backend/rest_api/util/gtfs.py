from rest_api.models import GTFSShape


def flush_gtfs_shape_objects():
    GTFSShape.objects.all().delete()
