from shapely.geometry import LineString, Point
import math
from haversine import haversine, inverse_haversine, Unit


def get_azimuth(p1, p2):
    x1, y1 = p1
    x2, y2 = p2

    return math.atan2(y2 - y1, x2 - x1)


def interpolate_points_by_distance(p1: Point, p2: Point, distance_in_meters: float = 500.0):
    points = [p1, p2]
    line = LineString(points)
    p1, p2 = map(lambda x: list(x.coords[0]), points)
    p1.reverse()
    p2.reverse()
    azimuth = get_azimuth(p1, p2)

    interpolated_point = inverse_haversine(p1, distance_in_meters, azimuth, unit=Unit.METERS)

    p1_obj = Point(p1)
    p_interpolated = Point(interpolated_point)
    latlon_distance = p1_obj.distance(p_interpolated)
    collinear_interpolated_point = line.interpolate(latlon_distance)
    collinear_point_coords = list(collinear_interpolated_point.coords[0])

    return collinear_point_coords


def linestring_distance(line: LineString):
    previous_coords = None
    total_distance = 0
    for coords in line.coords:
        current_coords = list(coords)
        current_coords.reverse()
        if previous_coords is None:
            previous_coords = current_coords
            continue
        total_distance += haversine(previous_coords, current_coords, unit=Unit.METERS)
        previous_coords = current_coords
    return total_distance
