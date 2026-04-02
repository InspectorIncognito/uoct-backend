from django.db.models import Prefetch
from geojson.feature import FeatureCollection
from gtfs_rt.utils import get_day_type, get_last_temporal_range, get_temporal_segment
from rest_api.models import Alert, HistoricSpeed, Segment, Services, Shape, Speed
from rest_api.util.alert import get_active_alerts


def shapes_to_geojson():
    # Get temporal parameters for filtering
    start_time, end_time = get_last_temporal_range()
    temporal_segment = get_temporal_segment(start_time)
    day_type = get_day_type(start_time)

    # Prefetch all related data to avoid N+1 queries
    # These prefetches are applied directly to Segment objects
    speed_prefetch = Prefetch(
        "speed_set",
        queryset=Speed.objects.filter(
            timestamp__date=start_time.date(), temporal_segment=temporal_segment
        ),
        to_attr="prefetched_speeds",
    )

    alert_prefetch = Prefetch(
        "alert_set",
        queryset=Alert.objects.filter(temporal_segment=temporal_segment),
        to_attr="prefetched_alerts",
    )

    historic_speed_prefetch = Prefetch(
        "historicspeed_set",
        queryset=HistoricSpeed.objects.filter(
            day_type=day_type, temporal_segment=temporal_segment
        ).order_by("-timestamp"),
        to_attr="prefetched_historic_speeds",
    )

    services_prefetch = Prefetch(
        "services_set", queryset=Services.objects.all(), to_attr="prefetched_services"
    )

    # Create a nested prefetch for segments with all their related data
    segment_prefetch = Prefetch(
        "segment_set",
        queryset=Segment.objects.prefetch_related(
            speed_prefetch, alert_prefetch, historic_speed_prefetch, services_prefetch
        ).order_by("sequence"),
    )

    # Fetch all shapes with their prefetched segments
    shapes = Shape.objects.prefetch_related(segment_prefetch).all()

    features = []
    for shape in shapes:
        features.extend(shape.to_geojson())

    geojson = FeatureCollection(features=features)
    active_alerts = get_active_alerts()
    output_data = dict(geojson=geojson, alerts=active_alerts)
    return output_data
