import math
from processors.geometry.constants import EARTH_RADIUS_KM


class Point:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude

    def haversine_distance(self, other: "Point") -> float:
        if not isinstance(other, Point):
            raise ValueError("Other point must be of type Point")

        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)

        lon_dist, lat_dist = lon2 - lon1, lat2 - lat1

        # Apply the Haversine formula to calculate the distance between two points on the surface of the earth
        a = math.sin(lat_dist / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(lon_dist / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        # Calculate the distance in meters
        distance = EARTH_RADIUS_KM * c * 1000

        return distance

    def distance(self, other: "Point") -> float:
        return self.haversine_distance(other)

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
