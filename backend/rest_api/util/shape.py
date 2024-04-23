from rest_api.models import Shape, Segment
from velocity.constants import DEG_PI, DEG_PI_HALF
from typing import List


class ShapeManager:
    def __init__(self):
        self.shapes = Shape.objects.all()

    def get_bbox(self):
        bbox_min_lat = DEG_PI_HALF
        bbox_max_lat = -DEG_PI_HALF
        bbox_min_lon = DEG_PI
        bbox_max_lon = -DEG_PI
        for shape in self.shapes:
            bbox = shape.get_bbox()
            bbox_min_lon = min(bbox_min_lon, bbox[0])
            bbox_min_lat = min(bbox_min_lat, bbox[1])
            bbox_max_lon = max(bbox_max_lon, bbox[2])
            bbox_max_lat = max(bbox_max_lat, bbox[3])
        return [bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat]

    def get_segments(self) -> List[Segment]:
        return [shape.get_segments() for shape in self.shapes]


def flush_shape_objects():
    Shape.objects.all().delete()
