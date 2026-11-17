from datetime import datetime, timezone as dt_timezone

from django.test import SimpleTestCase
from gtfs_rt.utils import get_day_bounds, get_month_bounds

UTC = dt_timezone.utc


class BoundsTest(SimpleTestCase):
    def test_day_bounds(self):
        start, end = get_day_bounds(datetime(2026, 11, 17, 23, 59, 59, tzinfo=UTC))
        self.assertEqual(start, datetime(2026, 11, 17, tzinfo=UTC))
        self.assertEqual(end, datetime(2026, 11, 18, tzinfo=UTC))

    def test_month_bounds_roll_over_the_year(self):
        self.assertEqual(
            get_month_bounds(2026, 12),
            (datetime(2026, 12, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)),
        )
