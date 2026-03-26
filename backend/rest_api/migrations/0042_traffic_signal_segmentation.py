# Generated manually for traffic signal segmentation feature

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("rest_api", "0041_alert_rest_api_al_segment_31dc1c_idx_and_more"),
    ]

    operations = [
        # Step 1: Remove the old segment_id FK from TrafficSignal
        migrations.RemoveField(
            model_name="trafficsignal",
            name="segment_id",
        ),
        # Step 2: Add new fields to TrafficSignal
        migrations.AddField(
            model_name="trafficsignal",
            name="osm_id",
            field=models.CharField(default="", max_length=64, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="trafficsignal",
            name="intersecting_ways",
            field=models.TextField(blank=True, default=""),
        ),
        # Step 3: Add start_signal and end_signal FKs to Segment
        migrations.AddField(
            model_name="segment",
            name="start_signal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="segments_starting_here",
                to="rest_api.trafficsignal",
            ),
        ),
        migrations.AddField(
            model_name="segment",
            name="end_signal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="segments_ending_here",
                to="rest_api.trafficsignal",
            ),
        ),
    ]
