import math
from typing import Tuple

from processors.geometry.constants import EARTH_RADIUS_KM
from haversine import haversine, Unit


# Lon: x
# Lat: y
class Point:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude

        self._coordinates = (self.latitude, self.longitude)

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
        return math.sqrt((other.longitude - self.longitude) ** 2 + (other.latitude - self.latitude) ** 2)

    def haversine_distance(self, other: "Point") -> float:
        if not isinstance(other, Point):
            raise ValueError("Other point must be of type Point")
        return haversine((self.latitude, self.longitude), (other.latitude, other.longitude), unit=Unit.METERS)

    def __eq__(self, point: "Point") -> bool:
        """
        Return True if the latitude and longitude of two Point objects are equal, False otherwise.

        :param point: Another Point object to compare to
        :type point: Point
        """
        if not isinstance(point, Point):
            raise ValueError("Point must be a Point object.")

        are_equal = (self.latitude == point.latitude and
                     self.longitude == point.longitude)

        return are_equal

    def __hash__(self) -> int:
        """
        Hash the point instance based on its points and its id.

        :return: A representation of the point instance as a hash
        :rtype: int
        """
        return hash((self.latitude, self.longitude))

    def __str__(self) -> str:
        """
        Return a string representation of the point.

        :return: A string representation of the point
        :rtype: str
        """
        return f"Point(latitude={str(self.latitude)}, longitude={str(self.longitude)})"
