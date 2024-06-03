# Generated by Django 4.1.1 on 2024-06-03 01:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rest_api', '0011_alter_speed_timestamp'),
    ]

    operations = [
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField()),
                ('voted_positive', models.IntegerField()),
                ('voted_negative', models.IntegerField()),
                ('detected_speed', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rest_api.speed')),
                ('segment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rest_api.segment')),
            ],
        ),
    ]