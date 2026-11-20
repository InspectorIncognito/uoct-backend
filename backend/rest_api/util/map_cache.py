from datetime import datetime

from django.core.cache import cache

from velocity.constants import TEMPORAL_SEGMENT_SECONDS

# Map payload TTL once the window's speeds are stored (alert votes can change sooner).
READY_TTL_SECONDS = 60
# While the speed job is still running for the window, keep the payload only briefly
# so the map picks up the speeds as soon as they are stored.
PENDING_TTL_SECONDS = 5


def map_data_key(window_start: datetime) -> str:
    return f"rest_api:map_data:{window_start.isoformat()}"


def speeds_ready_key(window_start: datetime) -> str:
    return f"rest_api:speeds_ready:{window_start.isoformat()}"


def speeds_ready(window_start: datetime) -> bool:
    return bool(cache.get(speeds_ready_key(window_start)))


def mark_speeds_ready(window_start: datetime) -> None:
    """Called by the speed job once speeds and alerts of the window are stored.

    Drops any map payload built while the job was running, otherwise it would be
    served without speeds until it expired.
    """
    cache.set(speeds_ready_key(window_start), True, 2 * TEMPORAL_SEGMENT_SECONDS)
    cache.delete(map_data_key(window_start))
