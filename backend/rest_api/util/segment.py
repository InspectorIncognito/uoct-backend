import geopandas as gpd
import pandas as pd
from geojson import Feature, FeatureCollection, LineString

from rest_api.models import Segment, Stop


class SegmentManager:
    def __init__(self, shape_name=None):
        if shape_name:
            from rest_api.models import Shape

            shapes = Shape.objects.filter(name__startswith=f"{shape_name}_")
            self.segments = Segment.objects.filter(shape__in=shapes)
        else:
            self.segments = Segment.objects.all()

    def segments_to_gdf(self, shape_name=None):
        # Si se proporciona shape_name aquí, filtrar adicionalmente
        if shape_name:
            from rest_api.models import Shape

            shapes = Shape.objects.filter(name__startswith=f"{shape_name}_")
            segments_to_use = Segment.objects.filter(shape__in=shapes)
        else:
            segments_to_use = self.segments

        segments = []
        for segment in segments_to_use:
            segments.append(
                Feature(
                    geometry=LineString(coordinates=segment.geometry),
                    properties={"segment_pk": segment.pk},
                )
            )
        segments = FeatureCollection(features=segments)
        return segments

    def get_services_for_each_segment(self, geojson_data: FeatureCollection):
        gdf = gpd.GeoDataFrame.from_features(geojson_data, crs="epsg:4326")
        for segment in self.segments:
            mask = gpd.GeoDataFrame.from_features(
                [segment.to_geojson()], crs="epsg:4326"
            )
            masked = gpd.clip(gdf, mask)
            shapes = masked["shape_id"].tolist()
            print(f"In {segment} the services are: {shapes}")

    def assign_stops_for_each_segment(self, stops_df: pd.DataFrame):
        # Convertir stops a GeoDataFrame
        stops_gdf = gpd.GeoDataFrame(
            stops_df,
            geometry=gpd.points_from_xy(stops_df["stop_lon"], stops_df["stop_lat"]),
            crs="epsg:4326",
        )

        # Obtener segmentos como GeoDataFrame
        segments = self.segments_to_gdf()
        segments_gdf = gpd.GeoDataFrame.from_features(segments, crs="epsg:4326")

        # VALIDAR Y LIMPIAR GEOMETRÍAS
        # Filtrar stops con coordenadas válidas
        stops_gdf = stops_gdf[
            (stops_gdf.geometry.notna())
            & (stops_gdf.geometry.is_valid)
            & (~stops_gdf.geometry.is_empty)
        ]

        # Validar y reparar geometrías de segmentos
        segments_gdf = segments_gdf[
            (segments_gdf.geometry.notna()) & (~segments_gdf.geometry.is_empty)
        ]
        segments_gdf["geometry"] = segments_gdf.geometry.apply(
            lambda geom: geom if geom.is_valid else geom.buffer(0)
        )

        if len(stops_gdf) == 0 or len(segments_gdf) == 0:
            print("No hay geometrías válidas para procesar")
            return

        # Proyectar a un CRS métrico para cálculos de distancia precisos
        utm_crs = "epsg:32719"  # Ajusta según tu región

        try:
            stops_projected = stops_gdf.to_crs(utm_crs)
            segments_projected = segments_gdf.to_crs(utm_crs)
        except Exception as e:
            print(f"Error en proyección: {e}")
            # Fallback: trabajar directamente en WGS84 con distancias en grados
            stops_projected = stops_gdf
            segments_projected = segments_gdf

        # Para cada parada, encontrar el segmento más cercano
        stops_created = 0
        stops_skipped = 0

        for idx, stop in stops_projected.iterrows():
            try:
                # Calcular distancia a todos los segmentos
                distances = segments_projected.geometry.distance(stop.geometry)

                # Verificar que hay distancias válidas
                if distances.isna().all():
                    stops_skipped += 1
                    continue

                # Encontrar el índice del segmento más cercano
                closest_segment_idx = distances.idxmin()
                closest_segment = segments_gdf.loc[closest_segment_idx]
                min_distance = distances.min()

                if min_distance > 30:  # Ajusta según tus necesidades
                    stops_skipped += 1
                    continue

                # Obtener coordenadas originales (en WGS84)
                original_stop = stops_gdf.loc[idx]

                # Crear la parada asociada al segmento más cercano
                stop_data = {
                    "segment": Segment.objects.get(pk=closest_segment["segment_pk"]),
                    "stop_id": stops_df.loc[idx, "stop_id"],
                    "latitude": original_stop.geometry.y,
                    "longitude": original_stop.geometry.x,
                }
                Stop.objects.create(**stop_data)
                stops_created += 1

            except Exception as e:
                print(f"Error procesando parada {stops_df.loc[idx, 'stop_id']}: {e}")
                stops_skipped += 1
                continue

        print(f"Paradas creadas: {stops_created}, Paradas omitidas: {stops_skipped}")

    def assign_traffic_signals_to_segments(self):
        pass
