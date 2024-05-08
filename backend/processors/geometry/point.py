import math
from typing import Tuple

from processors.geometry.constants import EARTH_RADIUS_KM
from haversine import haversine, Unit


# Lon: x
# Lat: y
class Point:
    def __init__(self, latitude: float, longitude: float):
        self.x = latitude
        self.y = longitude

        self._coordinates = (self.y, self.x)

    @property
    def coordinates(self) -> Tuple[float, float]:
        """
        Get the length of the line.

        :return: A float value that corresponds to the length of the line.
        :rtype: float
        """
        return self._coordinates

    def distance(self, other: "Point", algorithm: str = 'euclidean') -> float:
        if algorithm == 'euclidean':
            return self.euclidean_distance(other)
        elif algorithm == 'haversine':
            return self.haversine_distance(other)

    def euclidean_distance(self, other: "Point") -> float:
        return math.sqrt((other.x - self.x) ** 2 + (other.y - self.y) ** 2)

    def haversine_distance(self, other: "Point") -> float:
        if not isinstance(other, Point):
            raise ValueError("Other point must be of type Point")
        return haversine((self.y, self.x), (other.y, other.x), unit=Unit.METERS)

    def __eq__(self, point: "Point") -> bool:
        """
        Return True if the latitude and longitude of two Point objects are equal, False otherwise.

        :param point: Another Point object to compare to
        :type point: Point
        """
        if not isinstance(point, Point):
            raise ValueError("Point must be a Point object.")

        are_equal = (self.y == point.y and
                     self.x == point.x)

        return are_equal

    def __hash__(self) -> int:
        """
        Hash the point instance based on its points and its id.

        :return: A representation of the point instance as a hash
        :rtype: int
        """
        return hash((self.y, self.x))

    def __str__(self) -> str:
        """
        Return a string representation of the point.

        :return: A string representation of the point
        :rtype: str
        """
        return f"Point(latitude={str(self.y)}, longitude={str(self.x)})"
