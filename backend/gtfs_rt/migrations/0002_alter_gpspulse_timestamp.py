# Generated by Django 4.1.1 on 2024-05-22 19:30

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gtfs_rt', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gpspulse',
            name='timestamp',
            field=models.DateTimeField(default=datetime.datetime(2024, 5, 22, 19, 30, 57, 892592, tzinfo=datetime.timezone.utc)),
        ),
    ]