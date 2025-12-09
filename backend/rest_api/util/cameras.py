from pathlib import Path

import geopandas as gpd
import pandas as pd
from rest_api.models import Camera, Segment
from rest_api.util.segment import SegmentManager


def flush_cameras_from_db():
    Camera.objects.all().delete()


def assign_cameras_to_segments():
    """
    Assigns cameras to all segments within a 10-meter radius.
    Reads camera data from processed_cameras.csv and creates Camera objects
    for each camera-segment pair within the radius.
    """
    # Load cameras from CSV
    fixtures_path = Path(__file__).parent.parent.parent / "fixtures"
    cameras_csv_path = fixtures_path / "processed_cameras.csv"

    if not cameras_csv_path.exists():
        print(f"Error: Camera file not found at {cameras_csv_path}")
        return

    cameras_df = pd.read_csv(cameras_csv_path)
    cameras_df = cameras_df[["ID", "Latitud", "Longitud"]]
    cameras_df = cameras_df.dropna(subset=["Latitud", "Longitud"])

    # Convert cameras to GeoDataFrame
    cameras_gdf = gpd.GeoDataFrame(
        cameras_df,
        geometry=gpd.points_from_xy(cameras_df["Longitud"], cameras_df["Latitud"]),
        crs="epsg:4326",
    )

    # Get segments as GeoDataFrame
    segment_manager = SegmentManager()
    segments = segment_manager.segments_to_gdf()
    segments_gdf = gpd.GeoDataFrame.from_features(segments, crs="epsg:4326")

    # Validate and clean geometries
    cameras_gdf = cameras_gdf[
        (cameras_gdf.geometry.notna())
        & (cameras_gdf.geometry.is_valid)
        & (~cameras_gdf.geometry.is_empty)
    ]

    segments_gdf = segments_gdf[
        (segments_gdf.geometry.notna()) & (~segments_gdf.geometry.is_empty)
    ]
    segments_gdf["geometry"] = segments_gdf.geometry.apply(
        lambda geom: geom if geom.is_valid else geom.buffer(0)
    )

    if len(cameras_gdf) == 0 or len(segments_gdf) == 0:
        print("No valid geometries to process")
        return

    # Project to metric CRS for accurate distance calculations
    utm_crs = "epsg:32719"  # UTM Zone 19S for Santiago, Chile

    try:
        cameras_projected = cameras_gdf.to_crs(utm_crs)
        segments_projected = segments_gdf.to_crs(utm_crs)
    except Exception as e:
        print(f"Projection error: {e}")
        cameras_projected = cameras_gdf
        segments_projected = segments_gdf

    # For each camera, find all segments within 10 meters
    cameras_created = 0
    cameras_skipped = 0
    radius_meters = 15

    for idx, camera in cameras_projected.iterrows():
        try:
            # Calculate distance to all segments
            distances = segments_projected.geometry.distance(camera.geometry)

            # Check for valid distances
            if distances.isna().all():
                cameras_skipped += 1
                continue

            # Find all segments within the 10-meter radius
            segments_within_radius = distances[distances <= radius_meters]

            if len(segments_within_radius) == 0:
                cameras_skipped += 1
                print(
                    f"No segments within {radius_meters}m for camera {cameras_df.loc[idx, 'ID']}"
                )
                continue

            # Get original coordinates (in WGS84)
            original_camera = cameras_gdf.loc[idx]

            # Create a Camera object for each segment within the radius
            for segment_idx in segments_within_radius.index:
                segment = segments_gdf.loc[segment_idx]
                camera_data = {
                    "camera_id": str(int(cameras_df.loc[idx, "ID"])),
                    "segment_id": Segment.objects.get(pk=segment["segment_pk"]),
                    "latitude": original_camera.geometry.y,
                    "longitude": original_camera.geometry.x,
                }
                Camera.objects.create(**camera_data)
                cameras_created += 1

        except Exception as e:
            print(f"Error processing camera {cameras_df.loc[idx, 'ID']}: {e}")
            cameras_skipped += 1
            continue

    print(
        f"Camera-segment associations created: {cameras_created}, Cameras skipped: {cameras_skipped}"
    )
