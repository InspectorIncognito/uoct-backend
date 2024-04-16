from processors.geometry.point import Point
from datetime import datetime


class GPSPulse(Point):
    def __init__(self, timestamp: datetime, latitude: float, longitude:float):
        super().__init__(latitude, longitude)
        self.timestamp = timestamp

    def __hash__(self) -> int:
        return hash((self.timestamp, self.latitude, self.longitude))

    def __str__(self) -> str:
        return f"GPS(timestamp={str(self.timestamp)}latitude={str(self.latitude)}, longitude={str(self.longitude)})"
