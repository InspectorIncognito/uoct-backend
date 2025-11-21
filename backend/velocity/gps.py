from datetime import datetime

from processors.geometry.point import Point


class GPSPulse(Point):
    def __init__(
        self,
        timestamp: datetime,
        bearing: float,
        latitude: float,
        longitude: float,
        direction: int = None,
    ):
        super(GPSPulse, self).__init__(latitude, longitude)
        self.timestamp = timestamp
        self.bearing = bearing
        self.direction = direction

    def __hash__(self) -> int:
        return hash((self.timestamp, self.latitude, self.longitude, self.bearing))

    def __str__(self) -> str:
        return f"GPS(timestamp={str(self.timestamp)} latitude={str(self.latitude)}, longitude={str(self.longitude)}, bearing={str(self.bearing)})"
