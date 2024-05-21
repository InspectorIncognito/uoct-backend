from rest_api.models import Services, Segment, Shape
from shapely.geometry import LineString as shp_LineString
from rest_api.util.gtfs import GTFSShapeManager
import geopandas as gpd


def flush_services_from_db():
    Services.objects.all().delete()


def create_services(segment, services):
    Services.objects.create(segment=segment, services=services)


def assign_routes_to_segments():
    gtfs_shape_manager = GTFSShapeManager()
    shapes = Shape.objects.all()
    i = 0
    for shape in shapes:
        segments = shape.get_segments()
        gtfs_shape_manager.filter_by_direction(i)
        gtfs_routes = gtfs_shape_manager.to_geojson()
        gdf_routes = gpd.GeoDataFrame.from_features(gtfs_routes, crs='epsg:4326')
        for segment in segments:
            segment_linestring = shp_LineString(coordinates=segment.geometry)
            buffered = segment_linestring.buffer(0.0001, cap_style='flat', join_style='bevel')
            gdf_buffered = gpd.GeoDataFrame(index=[0], crs='epsg:4326', geometry=[buffered])
            clipped = gpd.clip(gdf_routes, gdf_buffered)
            services = clipped['shape_id'].tolist()
            create_services(segment, services)
        i += 1


def get_all_services():
    shape_data = {}
    for service in Services.objects.all():
        shape_id = service.segment.shape.pk
        set_services = shape_data.get(shape_id) or set()
        set_services.update(service.services)
        shape_data[shape_id] = set_services
    return shape_data


def get_shape_by_route_id(shape_data, route_id):
    for shape_id in shape_data:
        if route_id in shape_data[shape_id]:
            return shape_id
    return None
