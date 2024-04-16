import os
import geopandas as gpd
from config.paths import TEST_PATH
from geojson import Feature, FeatureCollection, MultiLineString
from processors.geometry.point import Point as Pointt
from shapely.geometry import Point, LineString
from shapely.ops import linemerge, split
import warnings

shapes = ["shape_0.geojson", "shape_1.geojson"]
SHAPES_PATH = os.path.join(TEST_PATH, "input_shapes")
OUTPUT_PATH = os.path.join(TEST_PATH, "output_shapes")


def clean_linestring(linestring):
    previous_coords = None
    coords = []
    for point in linestring.coords:
        if previous_coords is None:
            previous_coords = point
        if previous_coords == point:
            print("Repeated point:", point)
            continue
        coords.append([float(point[0]), float(point[1])])
        previous_coords = point
    linestring = LineString(coordinates=coords)
    print(linestring)
    return linestring


def merge_shapes(shapes_file_paths, output_filename="merged_shapes.geojson"):
    linestrings = []
    for path in shapes_file_paths:
        shape_path = os.path.join(SHAPES_PATH, path)
        gdf = gpd.read_file(shape_path)
        merged = linemerge(gdf["geometry"].unary_union).simplify(tolerance=0)
        linestrings.append(merged)

    feature_col = FeatureCollection(features=[Feature(geometry=f) for f in linestrings])
    output_gdf = gpd.GeoDataFrame.from_features(feature_col)
    output_path = os.path.join(OUTPUT_PATH, output_filename)
    output_gdf.to_file(output_path, driver="GeoJSON")


def segment_shapes_by_distance(shapes_file_name: str = "merged_shapes.geojson", distance_in_meters: int = 500,
                               output_filename="segmented_shapes.geojson"):
    shapes_path = os.path.join(TEST_PATH, shapes_file_name)
    output_path = os.path.join(TEST_PATH, output_filename)

    gdf = gpd.read_file(shapes_path)
    features = []
    total_distance = 0
    for shape in gdf.itertuples():
        points = []
        linestrings = []
        geometry = shape.geometry
        previous_point = None
        previous_distance = 0
        for point in geometry.coords:
            p_obj = Pointt(point[1], point[0])
            if previous_point is None:
                previous_point = p_obj
                continue
            previous_distance += p_obj.distance(previous_point)
            total_distance += p_obj.distance(previous_point)
            if previous_distance >= distance_in_meters:
                points.append(Point(point[0], point[1]))
                previous_distance = 0
            previous_point = p_obj
        previous_geometry = geometry
        for idx, point in enumerate(points):
            splitted = split(previous_geometry, point)
            previous_geometry = splitted.geoms[1]
            linestrings.append(splitted.geoms[0])

        mls_coords = [tuple(line.coords) for line in linestrings]
        features.append(Feature(geometry=MultiLineString(coordinates=mls_coords)))
    output = gpd.GeoDataFrame.from_features(FeatureCollection(features, crs={'init': 'epsg:4326'}))
    output.to_file(output_path, driver='GeoJSON')


def main():
    # merge_shapes(shapes)
    segment_shapes_by_distance()


if __name__ == "__main__":
    main()
