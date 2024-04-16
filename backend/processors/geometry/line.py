import math

from processors.geometry.point import Point


class Line:

    def __init__(self, point_a: Point, point_b: Point):
        """
        A Line is a segment between two points. Both points must be in geographical coordinates.

        :param point_a: Initial point of the line that must be a Point object
        :type point_a: Point

        :param point_b: Final point of the line that must be a Point object
        :type point_b: Point
        """
        # Private attributes
        self._point_a = None
        self._point_b = None
        self._length = None

        # Check for valid values using the setters
        self.point_a = point_a
        self.point_b = point_b

        # Calculate the length of the line
        self.length = self.point_a.distance(self.point_b)

    @property
    def point_a(self) -> Point:
        """
        Get the initial point of the line.

        :return: A Point object to get the initial point of the line.
        :rtype: Point
        """
        return self._point_a

    @point_a.setter
    def point_a(self, value: Point) -> None:
        """
        Set the initial point of the line and check for valid values.

        :param value: A Point object to set as the initial point of the line.
        :param value: Point

        :raises ValueError: If the value is not a Point object.
        """
        if not isinstance(value, Point):
            raise ValueError("Point A must be a Point object.")

        self._point_a = value

    @property
    def point_b(self) -> Point:
        """
        Get the final point of the line.

        :return: A Point object to get the final point of the line.
        :rtype: Point
        """
        return self._point_b

    @point_b.setter
    def point_b(self, value: Point) -> None:
        """
        Set the final point of the line and check for valid values.

        :param value: A Point object to set as the final point of the line.
        :type value: Point

        :raises ValueError: If the value is not a Point object.
        """
        if not isinstance(value, Point):
            raise ValueError("Point B must be a Point object.")

        self._point_b = value

    @property
    def length(self) -> float:
        """
        Get the length of the line.

        :return: A float value that corresponds to the length of the line.
        :rtype: float
        """
        return self._length

    @length.setter
    def length(self, value: float) -> None:
        """
        Set the length of the line and check for valid values.

        :param value: A non-negative float value.
        :type value: float

        :raises ValueError: If the value is not a non-negative float.
        """
        if not isinstance(value, float):
            raise ValueError("Length must be a float.")

        if value < 0:
            raise ValueError("Length must be non-negative.")

        self._length = value

    def distances(self, point: Point) -> tuple[float, float]:
        """
        Calculate the distance from a point to the line and the distance from the initial point of the line to the
        projection of the point on the line.

        :param point: A Point object that will be projected on the line.
        :type point: Point

        :return: A tuple with the distance between the point and its projection to the line and the distance from the
        initial point of the line to the aforementioned projection.
        :rtype: tuple[float, float]
        """
        # Get distances of the triangle formed by the line and the point
        distance_a = point.distance(self.point_a)
        distance_b = point.distance(self.point_b)
        segment_length = self.length

        # Sort the distances to get the smallest one
        sides = [segment_length, distance_b, distance_a]
        sides.sort()

        # Check if the triangle is obtuse using the Pythagorean theorem
        is_obtuse = (sides[0] ** 2 + sides[1] ** 2 < sides[2] ** 2)

        # Check if the segment's length is the largest side of the triangle
        is_largest = (sides[2] == segment_length)

        if not is_obtuse or is_largest:
            # The projection is inside the segment

            # Calculate the semi perimeter of the triangle
            s = (segment_length + distance_a + distance_b) / 2

            # Calculate the area of the triangle using Heron's formula
            a = math.sqrt(s * (s - distance_a) * (s - distance_b) * (s - segment_length))

            # Calculate the distance from the point to the projection using the area of the triangle
            stop_distance = (a * 2) / segment_length

            # Calculate the distance from the initial point of the line to the projection
            projection_distance = math.sqrt(abs(distance_a ** 2 - stop_distance ** 2))

            return stop_distance, projection_distance
        else:
            # The projection is outside the segment

            # Get the smallest distance
            min_distance = min(distance_a, distance_b)

            if min_distance == distance_a:
                # The point is closer to the initial point of the line
                return distance_a, 0
            else:
                # The point is closer to the final point of the line
                return distance_b, segment_length

    def __eq__(self, line: "Line") -> bool:
        """
        Return True if the points of two lines are equal, False otherwise.

        :param line: A Line object to compare with the current instance.
        :type line: Line

        :return: A boolean value that indicates if the points of two lines are equal.
        :rtype: bool
        """
        are_equal = self.point_a == line.point_a
        are_equal &= self.point_b == line.point_b

        return are_equal

    def __hash__(self) -> int:
        """
        Hash the line instance based on its points.

        :return: An integer value that corresponds to the hash of the line instance.
        :rtype: int
        """
        return hash((self.point_a, self.point_b))

    def __str__(self) -> str:
        """
        Return a string representation of the line.

        :return: A string representation of the line.
        :rtype: str
        """
        return f"Line(point_a={self.point_a}, point_b={self.point_b})"


class PolylineSegment(Line):

    def __init__(self, point_a: Point, point_b: Point, prev_distance: float | int, sequence: int):
        """
        A Segment is a line with a previous distance and a sequence number.

        :param point_a: Initial point of the segment that must be a Point object
        :type point_a: Point

        :param point_b: Final point of the segment that must be a Point object
        :type point_b: Point

        :param prev_distance: Distance from the initial point of the Polyline to the previous point
        :type prev_distance: float or int

        :param sequence: Sequence number of the segment that conforms the polyline
        :type sequence: int
        """
        # Initialize the parent class
        super(PolylineSegment, self).__init__(point_a, point_b)

        # Private attributes
        self._prev_distance = None
        self._sequence = None

        # Check for valid values using the setters
        self.prev_distance = prev_distance
        self.sequence = sequence

    @property
    def prev_distance(self) -> float | int:
        """
        Get the previous distance of the segment.

        :return: A non-negative numeric value that corresponds to the previous distance of the segment.
        :rtype: float or int
        """
        return self._prev_distance

    @prev_distance.setter
    def prev_distance(self, value: float | int) -> None:
        """
        Set the previous distance of the segment and check for valid values.

        :param value: A non-negative numeric value that corresponds to the previous distance of the segment.
        :type value: float or int

        :raises ValueError: If the value is not a non-negative numeric value.
        """
        if not isinstance(value, (float, int)):
            raise ValueError("Previous distance must be a numeric value.")

        if value < 0:
            raise ValueError("Previous distance must be a non-negative value.")

        self._prev_distance = value

    @property
    def sequence(self) -> int:
        """
        Get the sequence number of the segment.

        :return: A non-negative integer value that corresponds to the sequence number of the segment.
        :rtype: int
        """
        return self._sequence

    @sequence.setter
    def sequence(self, value: int) -> None:
        """
        Set the sequence number of the segment and check for valid values.

        :param value: A non-negative integer value.
        :raises ValueError: If the value is not a non-negative integer value.
        """
        if not isinstance(value, int):
            raise ValueError("Sequence must be an integer.")

        if value < 0:
            raise ValueError("Sequence must be non-negative.")

        self._sequence = value

    def on_route_distances(self, point: Point) -> tuple[float, float]:
        """
        Calculate the distance from a point to the segment of the polyline and the distance from the initial point of
        the polyline to the projection of the point on the segment.

        :param point: A Point object that will be projected on the segment.
        :type point: Point

        :return: A tuple with the distance between the point and the line, and its projection to the segment.
        :rtype: tuple[float, float]
        """
        # Calculate the distance from the point to the segment
        distance, projection = self.distances(point)

        # Accumulate the previous on route distance to the projection
        projection += self.prev_distance

        return distance, projection

    def __eq__(self, polyline_segment: "PolylineSegment") -> bool:
        """
        Return True if the points of two polyline segments are equal and the previous distance
        and sequence are equal, False otherwise.

        :param polyline_segment: A PolylineSegment object to compare with the current instance.
        :type polyline_segment: PolylineSegment

        :return: A boolean value that indicates if the points of two polyline segments are equal.
        :rtype: bool
        """
        are_equal = super(PolylineSegment, self).__eq__(polyline_segment)
        are_equal &= self.prev_distance == polyline_segment.prev_distance
        are_equal &= self.sequence == polyline_segment.sequence

        return are_equal

    def __hash__(self) -> int:
        """
        Hash the polyline segment instance based on its points, previous distance, and sequence.

        :return: An integer value that corresponds to the hash of the polyline segment instance.
        :rtype: int
        """
        return hash((self.point_a, self.point_b, self.prev_distance, self.sequence))

    def __str__(self) -> str:
        """
        Return a string representation of the polyline's segment.

        :return: A string representation of the polyline's segment.
        :rtype: str
        """
        return (f"PolylineSegment(point_a={self.point_a}, point_b={self.point_b},"
                f"prev_distance={self.prev_distance}, sequence={self.sequence})")
