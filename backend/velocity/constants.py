from math import pi, degrees


DEG_PI = degrees(pi)
DEG_PI_HALF = degrees(pi/2)

# CSV constants
ENCODING = "utf-8"
DELIMITER = ","
QUOTECHAR = '"'

# Length in meters of each spatial segment of an axis
SEGMENT_DISTANCE_METERS = 200

# Length of each temporal segment (speed aggregation window)
TEMPORAL_SEGMENT_MINUTES = 7.5
TEMPORAL_SEGMENT_SECONDS = int(TEMPORAL_SEGMENT_MINUTES * 60)
TEMPORAL_SEGMENTS_PER_DAY = 24 * 60 * 60 // TEMPORAL_SEGMENT_SECONDS
