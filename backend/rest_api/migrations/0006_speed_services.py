# Generated by Django 4.1.1 on 2024-05-07 20:37

import django.contrib.postgres.fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rest_api', '0005_alter_shape_grid_max_lat_alter_shape_grid_max_lon_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Speed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('speed', models.FloatField()),
                ('segment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rest_api.segment')),
            ],
        ),
        migrations.CreateModel(
            name='Services',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('services', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=124), size=None)),
                ('segment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rest_api.segment')),
            ],
        ),
    ]