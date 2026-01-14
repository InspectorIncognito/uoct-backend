"""Module for reading GTFS files and returning them as a dictionary."""

from io import BytesIO
from typing import IO
from zipfile import BadZipFile, ZipFile

import pandas as pd
import requests
from decouple import config
from rest_api.util.gtfs import GTFSShape, flush_gtfs_shape_objects
from rest_api.util.segment import SegmentManager


class GTFSFileReader:
    def __init__(self, filename: str, gtfs_zip: ZipFile):
        self.filename = filename
        self.gtfs_zip = gtfs_zip

    def __get_binary_csv_from_gtfs_zip(self, gtfs_zip: ZipFile) -> IO[bytes]:
        """
        Read the content in the GTFS zip object and return a binary extracted version of the desired csv file. This is
        used to read the csv file. See https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile.open.

        :param gtfs_zip: ZipFile object representing the GTFS zip file.
        :type gtfs_zip: ZipFile

        :return: Readable binary object that contains the extracted csv file.
        :rtype: IO[bytes]

        :raises KeyError: If the file is not found in the GTFS zip file.

        """

        is_zip = isinstance(gtfs_zip, ZipFile)

        if not is_zip:
            raise TypeError("The GTFS zip file must be a ZipFile object.")

        try:
            csv_binary = gtfs_zip.open(self.filename, mode="r")
            return csv_binary

        except KeyError:
            raise KeyError(f"File {self.filename} was not found inside the GTFS zip.")

    def load_csv_file_as_df(self) -> pd.DataFrame:
        csv_binary = self.__get_binary_csv_from_gtfs_zip(self.gtfs_zip)
        df = pd.read_csv(csv_binary)
        return df


class ShapesReader(GTFSFileReader):
    def __init__(self, gtfs_zip):
        super().__init__(filename="shapes.txt", gtfs_zip=gtfs_zip)

    @staticmethod
    def concat_points(group):
        return [
            (lon, lat) for lat, lon in zip(group["shape_pt_lat"], group["shape_pt_lon"])
        ]

    def process_df(self, df: pd.DataFrame) -> pd.DataFrame:
        return (
            df.groupby("shape_id")[["shape_pt_lat", "shape_pt_lon"]]
            .apply(self.concat_points)
            .reset_index(name="coordinates")
        )

    def filter_df(self, df: pd.DataFrame) -> pd.DataFrame:
        str_filter = "L|-"
        return df[~df.shape_id.str.contains(str_filter, case=False)]


class StopsReader(GTFSFileReader):
    def __init__(self, gtfs_zip):
        super().__init__(filename="stops.txt", gtfs_zip=gtfs_zip)


class TripsReader(GTFSFileReader):
    def __init__(self, gtfs_zip):
        super().__init__(filename="trips.txt", gtfs_zip=gtfs_zip)

    def get_route_direction(self, shape_id: str):
        df = self.load_csv_file_as_df()
        col = df[df["shape_id"] == shape_id]
        if col.empty:
            return None
        return col.iloc[0]["direction_id"]


class RoutesReader(GTFSFileReader):
    def __init__(self, gtfs_zip):
        super().__init__(filename="routes.txt", gtfs_zip=gtfs_zip)

    def filter_bus_routes(self, df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Filter routes to include only buses (route_type == 3).

        Args:
            df: Optional DataFrame to use. If None, loads from CSV

        Returns:
            DataFrame with only bus routes
        """
        if df is None:
            df = self.load_csv_file_as_df()

        return df[df["route_type"] == 3].reset_index(drop=True)


class GTFSManager:
    def __init__(self, gtfs_url: str = None):
        """
        Initialize GTFSManager.

        Args:
            gtfs_url: Optional GTFS URL to download from. If None, uses GTFS_URL from config.
        """
        self.gtfs_url = gtfs_url if gtfs_url else config("GTFS_URL")
        self.gtfs_zip = self.__download_gtfs_data()

        self.shapes_reader = ShapesReader(self.gtfs_zip)
        self.stops_reader = StopsReader(self.gtfs_zip)
        self.trips_reader = TripsReader(self.gtfs_zip)
        self.routes_reader = RoutesReader(self.gtfs_zip)

        self.segment_manager = SegmentManager()

    @staticmethod
    def __is_valid_zip_file(gtfs_zip) -> bool:
        """
        Return True if the GTFS zip file is valid, False otherwise.

        :return: True if the GTFS zip file is valid, False otherwise.
        :rtype: bool
        """
        try:
            with ZipFile(gtfs_zip, "r") as zip_file:
                _ = zip_file.namelist()
                return True

        except BadZipFile:
            return False

    def __download_gtfs_data(self) -> ZipFile:
        """
        Return a ZipFile object representing the GTFS zip file. This object is used to read the csv files inside the
        GTFS zip file. See https://docs.python.org/3/library/zipfile.html#zipfile-objects.

        :raises FileNotFoundError: If the GTFS zip file is not found in the input directory.
        :raises BadZipFile: If the GTFS zip file is not a valid zip file.
        """
        is_str = isinstance(self.gtfs_url, str)
        gtfs_data = requests.get(self.gtfs_url, stream=True)
        gtfs_data = BytesIO(gtfs_data.content)
        valid_type = self.__is_valid_zip_file(gtfs_data)

        if not is_str:
            raise TypeError("The path to the GTFS zip file must be a string.")

        if not valid_type:
            raise BadZipFile(f"File {self.gtfs_url} is not a valid zip file.")

        gtfs_zip = ZipFile(gtfs_data)
        return gtfs_zip

    def get_processed_df(self):
        df = self.shapes_reader.load_csv_file_as_df()
        df = self.shapes_reader.process_df(df)
        df = self.shapes_reader.filter_df(df)
        return df

    def merge_gtfs_data(self):
        """
        Merge trips, routes, and shapes DataFrames exactly as done in join_gtfs_info.py

        Returns:
            Merged DataFrame with trips, routes, and shapes data
        """
        # Load dataframes
        shapes_df = self.shapes_reader.load_csv_file_as_df()
        trips_df = self.trips_reader.load_csv_file_as_df()
        routes_df = self.routes_reader.load_csv_file_as_df()

        # Drop columns exactly as in join_gtfs_info.py
        drop_columns_shapes = []
        drop_columns_trips = [
            "trip_id",
            "service_id",
            "trip_headsign",
            "wheelchair_accessible",
            "bikes_allowed",
        ]
        drop_columns_routes = [
            "agency_id",
            "route_short_name",
            "route_long_name",
            "route_desc",
            "route_url",
            "route_color",
            "route_text_color",
        ]

        shapes_df.drop(columns=drop_columns_shapes, inplace=True)
        trips_df.drop(columns=drop_columns_trips, inplace=True)
        routes_df.drop(columns=drop_columns_routes, inplace=True)

        # Process shapes
        shapes_df = self.shapes_reader.process_df(shapes_df)
        # Remove duplicates from trips
        trips_df = trips_df.drop_duplicates(
            subset=["shape_id", "route_id", "direction_id"]
        )
        # Merge DataFrames
        merged_df = trips_df.merge(routes_df, on="route_id").merge(
            shapes_df, on="shape_id"
        )

        return merged_df

    def get_processed_shapes(self):
        """
        Create the final DataFrames for shapes (only bus routes) from the merged GTFS data.
        """
        merged_df = self.merge_gtfs_data()

        # Filter only bus routes (route_type == 3)
        shapes_df = (
            merged_df[merged_df["route_type"] == 3]
            .drop(columns=["route_type"])
            .reset_index(drop=True)
        )

        return shapes_df

    def save_gtfs_shapes_to_db(self, processed_df: pd.DataFrame):
        flush_gtfs_shape_objects()
        for _, row in processed_df.iterrows():
            shape_id = row["shape_id"]
            route_id = row.get("route_id", None)
            geometry = row["coordinates"]
            direction = row.get("direction_id", None)
            if direction is None:
                print(f"Shape {shape_id} has no direction.")
                continue
            GTFSShape.objects.create(
                shape_id=shape_id,
                route_id=route_id,
                geometry=geometry,
                direction=direction,
            )

    # Stops
    def assign_stops_to_segments(self):
        stops_df = self.stops_reader.load_csv_file_as_df()
        stops_df = stops_df.drop(columns=["stop_code", "location_type"])

        # Save df to a csv file for debugging
        stops_df.to_csv("stops.csv", index=False)
        stops_df = stops_df[["stop_id", "stop_lat", "stop_lon"]]
        self.segment_manager.assign_stops_for_each_segment(stops_df)
