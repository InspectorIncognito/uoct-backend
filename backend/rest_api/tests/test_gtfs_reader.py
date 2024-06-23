from rest_api.tests.tests_views_base import BaseTestCase
from velocity.gtfs import GTFSManager
from unittest import skip


@skip("Skipping endpoint dependant test.")
class TestGTFSReader(BaseTestCase):
    def setUp(self):
        self.gtfs_manager = GTFSManager()

    def test_read_shapes(self):
        shapes_df = self.gtfs_manager.shapes_reader.load_csv_file_as_df()

    def test_read_stops(self):
        stops_df = self.gtfs_manager.stops_reader.load_csv_file_as_df()

    def test_read_trips(self):
        trips_df = self.gtfs_manager.trips_reader.load_csv_file_as_df()
