import logging
from datetime import datetime, timedelta, timezone

import django_rq
from django.conf import settings
from django_rq.management.commands import rqscheduler
from gtfs_rt.processors.proto import download_proto_data
from gtfs_rt.utils import flush_gps_pulses, update_gtfs_data
from processors.speed.avg_speed import get_last_month_avg_speed

from rest_api.util.process import calculate_speed_and_check_alerts
from velocity.constants import TEMPORAL_SEGMENT_SECONDS

scheduler = django_rq.get_scheduler(settings.CRONLIKE_QUEUE)
logger = logging.getLogger(__name__)

SPEED_JOB_DELAY_SECONDS = 30


def next_temporal_window_start() -> datetime:
    """Start (UTC) of the next temporal window, e.g. hh:00:00, hh:07:30, hh:15:00, ..."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (now - midnight).total_seconds()
    windows = int(elapsed // TEMPORAL_SEGMENT_SECONDS) + 1
    return midnight + timedelta(seconds=windows * TEMPORAL_SEGMENT_SECONDS)


def clear_scheduled_jobs():
    print("Deleting jobs")
    for job in scheduler.get_jobs():
        print("Deleting scheduled job %s", job)
        job.delete()
    print("All jobs deleted")


def register_scheduled_jobs():
    print("Adding jobs to scheduler")
    # scheduler.schedule(
    #    scheduled_time=timezone.now(),  # Empezar ahora
    #    func=download_proto_data,
    #    args=[],
    #    interval=30,  # segundos
    #    repeat=None,  # repetir indefinidamente
    #    queue_name=settings.CRONLIKE_QUEUE,
    # )
    scheduler.cron(
        "0/1 * * * *",  # every minute
        func=download_proto_data,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False,  # Interpret hours in the local timezone
    )
    # TODO: Analyze if we need to delete speeds records periodically
    # Speeds every TEMPORAL_SEGMENT_SECONDS (7.5 min does not fit in cron), aligned to the
    # window boundaries plus a small delay so the last GPS pulses are already stored.
    scheduler.schedule(
        scheduled_time=next_temporal_window_start() + timedelta(seconds=SPEED_JOB_DELAY_SECONDS),
        func=calculate_speed_and_check_alerts,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        interval=TEMPORAL_SEGMENT_SECONDS,  # seconds between runs
        queue_name=settings.SPEED_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
    )
    scheduler.cron(
        "0 0 1 * *",  # at 00:00 every day-of-month 1
        func=get_last_month_avg_speed,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False,
    )
    scheduler.cron(
        "0 0 1,15 * *",  # at 00:00 on the 1st and 15th of each month (every two weeks)
        func=flush_gps_pulses,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False,
    )
    scheduler.cron(
        "0 2 * * *",  # at 02:00 every day
        func=update_gtfs_data,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False,
    )


class Command(rqscheduler.Command):
    def handle(self, *args, **kwargs):
        # This is necessary to prevent duplicates
        clear_scheduled_jobs()

        register_scheduled_jobs()
        super(Command, self).handle(*args, **kwargs)
