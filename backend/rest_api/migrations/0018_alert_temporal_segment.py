# Generated by Django 4.1.1 on 2024-06-28 20:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rest_api', '0017_historicspeed_temporal_segment'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='temporal_segment',
            field=models.IntegerField(default=0),
        ),
    ]