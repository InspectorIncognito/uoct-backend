# Generated by Django 4.1.1 on 2024-06-23 23:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rest_api', '0015_stop'),
    ]

    operations = [
        migrations.AddField(
            model_name='speed',
            name='temporal_segment',
            field=models.IntegerField(default=0),
        ),
    ]
