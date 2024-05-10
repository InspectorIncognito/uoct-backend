"""Module for reading GTFS files and returning them as a dictionary."""

import codecs
import csv
import zipfile
from geojson import LineString, Feature, FeatureCollection
import pandas as pd
import geopandas as gpd

import requests
import itertools
from decouple import config
from io import TextIOWrapper, BytesIO
from pathlib import Path
from typing import IO
from zipfile import ZipFile, BadZipFile, ZipExtFile
from rest_api.util.segment import SegmentManager
from rest_api.util.gtfs import flush_gtfs_shape_objects

from velocity.constants import ENCODING, DELIMITER, QUOTECHAR
from rest_api.util.gtfs import GTFSShape


class GTFSReader:

    def __init__(self, delimiter: str = DELIMITER, quotechar: str = QUOTECHAR, encoding: str = ENCODING):
        """
        Class for reading GTFS files and returning them as a dictionary.


        :param delimiter: Delimiter used in the csv file.
        :type delimiter: str

        :param quotechar: Quote character used in the csv file.
        :type quotechar: str

        :param encoding: Encoding of the csv file.
        :type encoding: str

        :raises TypeError: If the delimiter, quote character, or encoding are not strings.
        :raises ValueError: If the delimiter or quote character are not strings of length 1.
        :raises ValueError: If the encoding is not a valid encoding.

        """
        self.gtfs_url = config("GTFS_URL")

        if not isinstance(delimiter, str):
            raise TypeError("Delimiter must be a string.")

        if len(delimiter) != 1:
            raise ValueError("Delimiter must be a string of length 1.")

        if not isinstance(quotechar, str):
            raise TypeError("Quote character must be a string.")

        if len(quotechar) != 1:
            raise ValueError("Quote character must be a string of length 1.")

        if not isinstance(encoding, str):
            raise TypeError("Encoding must be a string.")

        try:
            codecs.lookup(encoding)

        except LookupError:
            raise ValueError(f"Unknown encoding: {encoding}")

        self.delimiter = delimiter
        self.quotechar = quotechar
        self.encoding = encoding

        # Open GTFS zip
        self.gtfs_zip = self.__get_gtfs_zip_from_url()

    def __is_valid_zip_file(self, gtfs_data) -> bool:
        """
        Return True if the GTFS zip file is valid, False otherwise.

        :return: True if the GTFS zip file is valid, False otherwise.
        :rtype: bool
        """
        try:
            with ZipFile(gtfs_data, 'r') as zip_file:
                _ = zip_file.namelist()
                return True

        except BadZipFile:
            return False

    def __get_gtfs_zip_from_url(self) -> ZipFile:
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

    def __get_binary_csv_from_gtfs_zip(self, csv_filename: str, gtfs_zip: ZipFile) -> IO[bytes]:

        """
        Read the content in the GTFS zip object and return a binary extracted version of the desired csv file. This is
        used to read the csv file. See https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile.open.

        :param csv_filename: Name of the file in the GTFS zip file (including the .csv extension).
        :type csv_filename: str

        :param gtfs_zip: ZipFile object representing the GTFS zip file.
        :type gtfs_zip: ZipFile

        :return: Readable binary object that contains the extracted csv file.
        :rtype: IO[bytes]

        :raises KeyError: If the file is not found in the GTFS zip file.

        """

        is_str = isinstance(csv_filename, str)
        is_zip = isinstance(gtfs_zip, ZipFile)

        if not is_str:
            raise TypeError("The csv filename must be a string.")

        if not is_zip:
            raise TypeError("The GTFS zip file must be a ZipFile object.")

        try:
            csv_binary = gtfs_zip.open(csv_filename, mode="r")
            return csv_binary

        except KeyError:
            raise KeyError(f"File {csv_filename} was not found inside the GTFS zip.")

    def __get_text_wrapper_for_binary_csv(self, csv_binary: IO[bytes]) -> TextIOWrapper:
        """
        Return a text wrapper for reading the extracted csv as text. A text wrapper is used to decode the csv file
        using the encoding specified in the constructor. See https://docs.python.org/3/library/io.html#io.TextIOWrapper.

        :param csv_binary: Readable binary object that contains the csv file.
        :type csv_binary: IO[bytes]

        :return: Text wrapper for reading the csv file as text.
        :rtype: TextIOWrapper

        """
        is_binary = isinstance(csv_binary, ZipExtFile)

        if not is_binary:
            raise TypeError("The csv binary object must be a BinaryIO object.")

        try:
            txt_wrapper = TextIOWrapper(csv_binary, encoding=self.encoding)
            return txt_wrapper

        except UnicodeDecodeError as e:
            raise UnicodeDecodeError(__encoding=self.encoding, __object=e.object, __start=e.start, __end=e.end,
                                     __reason=f"Error decoding the CSV file: {str(e)}") from e

    def __get_csv_dict_reader_from_txt_wrapper(self, csv_txt_wrapper: TextIOWrapper) -> csv.DictReader:
        """
        Return a Dictionary Reader object with the csv file data. This is used for mapping each csv row into a
        dictionary. It is assumed that the first row of the csv file contains the column names. The delimiter and quote
        characters are specified in the constructor. See https://docs.python.org/3/library/csv.html#csv.DictReader.

        :param csv_txt_wrapper: Text wrapper for reading the csv file as text.
        :type csv_txt_wrapper: TextIOWrapper

        :return: DictReader object.
        :rtype: DictReader
        """
        is_txt_wrapper = isinstance(csv_txt_wrapper, TextIOWrapper)

        if not is_txt_wrapper:
            raise TypeError("The csv text wrapper must be a TextIOWrapper object.")

        try:
            csv_dict_reader = csv.DictReader(csv_txt_wrapper, delimiter=self.delimiter, quotechar=self.quotechar)
            return csv_dict_reader

        except csv.Error as e:
            raise csv.Error(f"Error creating the DictReader object: {str(e)}") from e

    def __get_dict_from_csv_reader(self, csv_reader: csv.DictReader) -> list[dict]:
        """
        Return a list of dictionaries from the csv reader object. Each dictionary represents a row in the csv file and
        the keys are the corresponding column names. See https://docs.python.org/3/library/csv.html#csv.DictReader.

        :param csv_reader: DictReader object representing the csv data.
        :type csv_reader: DictReader

        :return: List of dictionaries representing the csv data.
        :rtype: list[dict]
        """
        is_csv_reader = isinstance(csv_reader, csv.DictReader)

        if not is_csv_reader:
            raise TypeError("The csv reader must be a DictReader object.")

        try:
            dict_list = [dict(csv_row) for csv_row in csv_reader]
            return dict_list

        except csv.Error as e:
            raise csv.Error(f"Error reading the csv data: {str(e)}") from e

    def load_csv_file_as_pd(self, csv_filename: str) -> pd.DataFrame:
        csv_binary = self.__get_binary_csv_from_gtfs_zip(csv_filename, self.gtfs_zip)
        df = pd.read_csv(csv_binary)
        return df

    def load_csv_as_dicts_list(self, csv_filename: str) -> list[dict]:
        """
        Return a list of dictionaries from the csv file in the GTFS zip file. Each dictionary represents a row in the
        csv file and the keys are the corresponding column names. See https://docs.python.org/3/library/csv.html

        :param csv_filename: Name of the file in the GTFS zip file (including the .csv extension).
        :type csv_filename: str

        :return: List of dictionaries representing the csv data.
        :rtype: list[dict]
        """
        # Open csv file in GTFS zip
        csv_binary = self.__get_binary_csv_from_gtfs_zip(csv_filename, self.gtfs_zip)

        # Create text wrapper for csv file
        csv_txt_wrapper = self.__get_text_wrapper_for_binary_csv(csv_binary)

        # Create DictReader object for csv file
        csv_dict_reader = self.__get_csv_dict_reader_from_txt_wrapper(csv_txt_wrapper)

        # Create list of dictionaries from csv file
        dict_list = self.__get_dict_from_csv_reader(csv_dict_reader)

        return dict_list


class ShapesReader(GTFSReader):

    def __init__(self):
        super().__init__()
        self.filename = 'shapes.txt'
        self.segment_manager = SegmentManager()

    def __process_row(self, row: dict) -> dict:
        """
        :param row: Row from the shapes.txt file.
        :type row: dict

        :return: dict object.
        :rtype: dict
        """
        keys_to_extract = ['shape_pt_lat', 'shape_pt_lon', 'shape_pt_sequence', 'shape_id']
        cast_funcs = [float, float, float, str]
        subset_dict = {key: cast_func(row[key]) for cast_func, key in zip(cast_funcs, keys_to_extract)}

        return subset_dict

    def load_csv_as_pd(self) -> pd.DataFrame:
        df = self.load_csv_file_as_pd(self.filename)
        return df

    @staticmethod
    def concat_points(group):
        return [(lon, lat) for lat, lon in zip(group['shape_pt_lat'], group['shape_pt_lon'])]

    def process_df(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.groupby('shape_id')[['shape_pt_lat', 'shape_pt_lon']].apply(self.concat_points).reset_index(
            name='coordinates')

    @staticmethod
    def processed_df_to_geojson(df: pd.DataFrame):
        output_geojson = FeatureCollection(
            features=[
                Feature(geometry=LineString(coordinates=row['coordinates']),
                        properties={
                            "shape_id": str(row['shape_id'])
                        }
                        )
                for _, row in df.iterrows()]
        )
        return output_geojson

    def get_services_for_each_segment(self, geojson_data: FeatureCollection):
        self.segment_manager.get_services_for_each_segment(geojson_data)

    def save_gtfs_shapes_to_db(self, processed_df: pd.DataFrame):
        self._save_gtfs_shapes_to_db(processed_df)


class TripsReader(GTFSReader):

    def __init__(self):
        super().__init__()
        self.filename = 'trips.txt'

    def __process_row(self, row: dict) -> dict:
        """
        Process a row from the trips.txt file and return a StopPoint object with information about the stop.

        :param row: Row from the trips.txt file.
        :type row: dict

        :return: tuple object.
        :rtype: dict
        """
        keys_to_extract = ['route_id', 'service_id', 'trip_id', 'direction_id', 'shape_id']
        subset_dict = {key: row[key] for key in keys_to_extract}

        return subset_dict

    def load_csv_as_list(self) -> list[dict]:
        """
        Custom method to load CSV as a list of dictionaries with some changes in the process.

        :return: List of dictionaries representing the custom processed csv data.
        :rtype: list[dict]
        """
        # Load the csv file as a list of dictionaries with the original processing logic
        dict_list = super().load_csv_as_dicts_list(self.filename)

        # Apply the custom processing logic to each row
        dict_list = [self.__process_row(row) for row in dict_list]

        return dict_list

    def load_csv_as_dict(self) -> dict:
        """
        Custom method to load CSV as a dict of dictionaries with some changes in the process.

        :return: List of dictionaries representing the custom processed csv data.
        :rtype: list[dict]
        """
        dict_list = self.load_csv_as_dicts_list(self.filename)

        trip_dict = dict()
        for row in dict_list:
            row = self.__process_row(row)
            trip_dict[row['trip_id']] = row

        return trip_dict

    def load_csv_as_pd(self) -> pd.DataFrame:
        df = self.load_csv_file_as_pd(self.filename)
        return df

    def get_route_direction(self, shape_id: str):
        df = self.load_csv_file_as_pd(self.filename)
        col = df[df['shape_id'] == shape_id]
        if col.empty:
            return None
        return col.iloc[0]['direction_id']


class GTFSManager:
    def __init__(self):
        self.shape_reader = ShapesReader()
        self.trips_reader = TripsReader()

    def get_shape_id_dict(self):
        return self.shape_reader.load_csv_as_pd()

    def get_processed_df(self):
        df = self.get_shape_id_dict()
        return self.shape_reader.process_df(df)

    def get_shape_geojson(self):
        df = self.get_shape_id_dict()
        df = self.shape_reader.process_df(df)
        geojson = self.shape_reader.processed_df_to_geojson(df)
        return geojson

    def get_services_for_each_segment(self, geojson_data: FeatureCollection):
        self.shape_reader.get_services_for_each_segment(geojson_data)

    def save_gtfs_shapes_to_db(self, processed_df: pd.DataFrame):
        flush_gtfs_shape_objects()
        for _, row in processed_df.iterrows():
            shape_id = row['shape_id']
            geometry = row['coordinates']
            direction = self.trips_reader.get_route_direction(shape_id)
            if direction is None:
                print(f"Shape {shape_id} has no direction.")
                return
            GTFSShape.objects.create(shape_id=shape_id, geometry=geometry, direction=direction)

