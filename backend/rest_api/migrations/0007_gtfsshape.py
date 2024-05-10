# Generated by Django 4.1.1 on 2024-05-09 21:29

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rest_api', '0006_speed_services'),
    ]

    operations = [
        migrations.CreateModel(
            name='GTFSShape',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shape_id', models.CharField(max_length=124)),
                ('geometry', django.contrib.postgres.fields.ArrayField(base_field=django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), size=None), size=None)),
                ('direction', models.IntegerField()),
            ],
        ),
    ]
