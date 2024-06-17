import datetime
import logging
import django_rq
from django.conf import settings
from django_rq.management.commands import rqscheduler
from gtfs_rt.management.commands import download_proto_scheduler, calculate_speed

scheduler = django_rq.get_scheduler(settings.CRONLIKE_QUEUE)
logger = logging.getLogger(__name__)


def clear_scheduled_jobs():
    for job in scheduler.get_jobs():
        logger.info("Deleting scheduled job %s", job)
        job.delete()


# TODO: Add the following commands:
#  - gtfs_rt.commands.download_proto_scheduler
#  - gtfs_rt.commands.calculate_speed
def register_scheduled_jobs():
    logger.info("Adding jobs to scheduler")
    scheduler.cron(
        '* * * * *',  # every minute
        func=download_proto_scheduler,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever)
        use_local_timezone=True  # Interpret hours in the local timezone
    )
    scheduler.cron(
        '*/15 * * * *',  # every 15 minutes
        func=calculate_speed,  # Function to be queued
        args=[],  # Arguments passed into function when executed
        queue_name=settings.CRONLIKE_QUEUE,  # In which queue the job should be put in
        repeat=None,  # Repeat this number of times (None means repeat forever
        use_local_timezone=True  # Interpret hours in the local timezone
    )
