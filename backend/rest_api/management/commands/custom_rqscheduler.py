import logging

import django_rq
from django.conf import settings
from django_rq.management.commands import rqscheduler
from gtfs_rt.processors.proto import download_proto_data
from gtfs_rt.utils import flush_gps_pulses, update_gtfs_data
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
    scheduler.cron(
        "0/15 * * * *",  # every 15 minutes
        func=calculate_speed_and_check_alerts,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=False,  # Interpret hours in the local timezone
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
