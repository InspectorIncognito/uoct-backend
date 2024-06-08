from rest_api.models import GTFSShape
from rest_api.util.shape import ShapeManager


class GTFSShapeManager(ShapeManager):
    def __init__(self):
        super(GTFSShapeManager, self).__init__()
        self.shapes = GTFSShape.objects.all()

    def clear_filter(self):
        self.shapes = GTFSShape.objects.all()

    def filter_by_direction(self, direction: int):
        self.clear_filter()
        self.shapes = self.shapes.filter(direction=direction)


def flush_gtfs_shape_objects():
    try:
        GTFSShape.objects.all().delete()
    except:
        pass
