from gtfs_rt.config import TIMEZONE
import datetime
from gtfs_rt.models import GPSPulse
from velocity.vehicle import VehicleManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid


def calculate_speed(start_date: datetime.date = None, end_date: datetime = None):
    end_date_hardcode = datetime.datetime(year=2024, month=5, day=22, hour=16, minute=0, second=0)
    end_date = end_date_hardcode.astimezone(TIMEZONE)
    start_date = (end_date_hardcode - datetime.timedelta(minutes=5)).astimezone(TIMEZONE)
    queryset = GPSPulse.objects.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    print(f"Got {len(queryset)} GPS pulses.")

    print("Creating Grid Object")
    grid_obj = generate_grid()
    print("Creating Vehicle Manager")
    vm = VehicleManager(grid_obj)

    for gps in queryset:
        vm.add_data(gps)

    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
    speed_records = vm.calculate_speed(segment_criteria)
    return speed_records
