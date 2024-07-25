import logging
import django_rq
from django.conf import settings
from gtfs_rt.processors.proto import download_proto_data
from gtfs_rt.utils import flush_gps_pulses
from django_rq.management.commands import rqscheduler
from processors.speed.avg_speed import get_last_month_avg_speed
from rest_api.util.process import calculate_speed_and_check_alerts

scheduler = django_rq.get_scheduler(settings.CRONLIKE_QUEUE)
logger = logging.getLogger(__name__)


def clear_scheduled_jobs():
    print("Deleting jobs")
    for job in scheduler.get_jobs():
        print("Deleting scheduled job %s", job)
        job.delete()
    print("All jobs deleted")


def register_scheduled_jobs():
    print("Adding jobs to scheduler")
    scheduler.cron(
        '0/1 * * * *',  # every minute
        func=download_proto_data,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False  # Interpret hours in the local timezone
    )
    scheduler.cron(
        '0/15 * * * *',  # every 15 minutes
        func=calculate_speed_and_check_alerts,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False  # Interpret hours in the local timezone
    )
    scheduler.cron(
        "0 0 1 * *",  # at 00:00 every day-of-month 1
        func=get_last_month_avg_speed,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False
    )
    scheduler.cron(
        "0 0 1 * *",  # at 00:00 every day-of-month 1
        func=flush_gps_pulses,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False
    )


class Command(rqscheduler.Command):
    def handle(self, *args, **kwargs):
        # This is necessary to prevent duplicates
        clear_scheduled_jobs()

        register_scheduled_jobs()
        super(Command, self).handle(*args, **kwargs)
