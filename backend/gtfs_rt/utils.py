import shutil
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pytz
import requests
from bs4 import BeautifulSoup
from decouple import config
from django.utils import timezone

from gtfs_rt.models import GPSPulse

MAD_CONST = 1.4826


def median_absolute_deviation(x):
    median = np.median(x)
    abs_deviations = np.abs(x - median)
    return np.median(abs_deviations) * MAD_CONST


def speed_threshold(x):
    median = np.median(x)
    abs_deviations = np.abs(x - median)
    MAD = np.median(abs_deviations) * MAD_CONST
    return (x - median) / MAD


def get_temporal_segment(date: datetime, interval: int = 15):
    day_minutes = date.hour * 60 + date.minute
    return day_minutes // interval


def get_temporal_range(temporal_segment, reference_datetime=None):
    # Base: ahora en UTC
    if reference_datetime is None:
        reference_datetime = timezone.now()

    start_minutes = temporal_segment * 15
    start_hour = start_minutes // 60
    start_minute = start_minutes % 60

    # Construir un datetime en UTC, conservando la fecha actual
    start_time = reference_datetime.replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )

    end_time = start_time + timedelta(minutes=15)
    return start_time, end_time


@lru_cache(maxsize=1)
def _get_last_temporal_range_cached(minute_key):
    """
    Internal cached version of get_last_temporal_range.
    Uses minute_key to invalidate cache every minute.
    """
    delta = timedelta(minutes=15)
    now = timezone.now()
    last_15_minutes = now - delta
    last_temporal_segment = get_temporal_segment(last_15_minutes)
    return get_temporal_range(last_temporal_segment, reference_datetime=last_15_minutes)


def get_last_temporal_range():
    """
    Get the last temporal range (15-minute window).
    Cached for 1 minute to avoid redundant calculations.
    """
    # Use current minute as cache key - cache expires every minute
    minute_key = timezone.now().replace(second=0, microsecond=0)
    return _get_last_temporal_range_cached(minute_key)


def get_last_temporal_segment():
    delta = timedelta(minutes=15)
    now = timezone.now()
    last_15_minutes = now - delta
    last_temporal_segment = get_temporal_segment(last_15_minutes)
    return last_15_minutes.date(), last_temporal_segment


def get_day_type(dt: datetime):
    if dt.tzinfo is None:
        raise ValueError("datetime instance must have a tzinfo")
    # Convertir a Santiago solo para determinar día de semana
    santiago_tz = pytz.timezone("America/Santiago")
    converted_timestamp = dt.astimezone(santiago_tz)
    weekday = converted_timestamp.weekday()
    day_type = "L" if weekday < 5 else "S" if weekday == 5 else "D"

    return day_type


def get_previous_month():
    current_datetime = timezone.now()
    current_date = current_datetime.replace(day=1)
    current_date = current_date - timedelta(days=1)
    return current_date.month


def flush_gps_pulses():
    print("Calling flush_gps_pulses command...")
    GPSPulse.objects.all().delete()


def get_gtfs_vigente_download_url(timeout: int = 15) -> str:
    """Scrape the DTPM website to find the current GTFS download URL."""
    DTPM_GTFS_URL = config("DTPM_GTFS_URL")
    response = requests.get(DTPM_GTFS_URL, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    links = soup.find_all("a", href=True)

    for link in links:
        href = link["href"].lower()
        text = link.get_text(strip=True).lower()

        if href.endswith(".zip") and "gtfs" in href:
            return urljoin(DTPM_GTFS_URL, link["href"])

        if href.endswith(".zip") and "gtfs" in text:
            return urljoin(DTPM_GTFS_URL, link["href"])

    raise RuntimeError("No se encontró el link del GTFS vigente")


def download_gtfs_zip(download_url: str, output_dir: Path) -> Path:
    """Download the GTFS zip file from the given URL."""
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = download_url.split("/")[-1]
    output_path = output_dir / filename

    with requests.get(download_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)

    return output_path


def get_current_gtfs_url() -> str:
    """
    Get the current GTFS URL by scraping DTPM website.
    Falls back to GTFS_URL from environment if scraping fails.

    Returns:
        str: URL to download the current GTFS zip file.
    """

    try:
        print("Buscando GTFS vigente en DTPM...")
        gtfs_url = get_gtfs_vigente_download_url()
        print(f"URL encontrada: {gtfs_url}")
        return gtfs_url
    except Exception as e:
        print(f"No se pudo obtener URL del sitio DTPM: {str(e)}")
        fallback_url = config("GTFS_URL")
        print(f"Usando URL de fallback: {fallback_url}")
        return fallback_url


def update_gtfs_data():
    """Update GTFS shapes and stops using the current GTFS URL."""

    print("Iniciando actualización de datos GTFS...")

    try:
        # Get the current GTFS URL
        gtfs_url = get_current_gtfs_url()

        # Import here to avoid circular imports
        from rest_api.util.services import (
            assign_routes_to_segments,
            flush_services_from_db,
        )
        from rest_api.util.stops import assign_stops_to_segments, flush_stops_from_db
        from velocity.gtfs import GTFSManager

        # Update shapes
        print("Actualizando shapes del GTFS...")
        gtfs_manager = GTFSManager(gtfs_url=gtfs_url)
        processed_shapes = gtfs_manager.get_processed_shapes()
        gtfs_manager.save_gtfs_shapes_to_db(processed_shapes)
        print("Shapes actualizados")

        # Update routes/services
        print("Actualizando rutas/servicios del GTFS...")
        flush_services_from_db()
        assign_routes_to_segments()
        print("Rutas/servicios actualizados")

        # Update stops
        print("Actualizando stops del GTFS...")
        flush_stops_from_db()
        assign_stops_to_segments()
        print("Stops actualizados")

        print("Actualización de GTFS completada exitosamente")

    except Exception as e:
        print(f"Error durante la actualización del GTFS: {str(e)}")
        raise
