# Generated by Django 4.1.1 on 2024-05-22 19:42

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('gtfs_rt', '0004_gpspulse_license_plate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gpspulse',
            name='timestamp',
            field=models.DateTimeField(default=django.utils.timezone.localdate),
        ),
    ]
