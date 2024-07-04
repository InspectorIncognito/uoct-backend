# Generated by Django 4.1.1 on 2024-07-04 00:03

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('rest_api', '0018_alert_temporal_segment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alert',
            name='timestamp',
            field=models.DateTimeField(default=django.utils.timezone.localtime),
        ),
    ]
