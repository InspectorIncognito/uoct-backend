# Generated by Django 4.1.1 on 2024-05-22 19:42

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('rest_api', '0009_alter_speed_timestamp'),
    ]

    operations = [
        migrations.AlterField(
            model_name='speed',
            name='timestamp',
            field=models.DateTimeField(default=django.utils.timezone.localdate),
        ),
    ]