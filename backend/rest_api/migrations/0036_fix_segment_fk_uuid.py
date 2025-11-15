from django.db import migrations, models


def purge_dependent(apps, schema_editor):
    """Delete dependent rows to allow FK column recreation without cast errors.

    We intentionally drop data in Speed / HistoricSpeed / Alert / Services / Stop /
    TrafficSignal because these are regenerated downstream (e.g., OSM processing,
    speed ingestion). If you need preservation, implement a mapping export BEFORE
    applying this migration.
    """
    for model_name in [
        "Speed",
        "HistoricSpeed",
        "Alert",
        "Services",
        "Stop",
        "TrafficSignal",
    ]:
        Model = apps.get_model("rest_api", model_name)
        Model.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rest_api", "0035_remove_segment_id_alter_segment_segment_id"),
    ]

    operations = [
        migrations.RunPython(purge_dependent, migrations.RunPython.noop),
        # Remove old FK fields (bigint) so we can recreate them as UUID FKs.
        migrations.RemoveField(model_name="speed", name="segment"),
        migrations.RemoveField(model_name="historicspeed", name="segment"),
        migrations.RemoveField(model_name="alert", name="segment"),
        migrations.RemoveField(model_name="services", name="segment"),
        migrations.RemoveField(model_name="stop", name="segment"),
        migrations.RemoveField(model_name="trafficsignal", name="segment_id"),
        # Recreate FK fields pointing to Segment.segment_id (UUID PK)
        migrations.AddField(
            model_name="speed",
            name="segment",
            field=models.ForeignKey(
                to="rest_api.segment", on_delete=models.CASCADE, null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="historicspeed",
            name="segment",
            field=models.ForeignKey(
                to="rest_api.segment", on_delete=models.CASCADE, null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="alert",
            name="segment",
            field=models.ForeignKey(
                to="rest_api.segment", on_delete=models.CASCADE, null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="services",
            name="segment",
            field=models.ForeignKey(
                to="rest_api.segment", on_delete=models.CASCADE, null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="stop",
            name="segment",
            field=models.ForeignKey(
                to="rest_api.segment", on_delete=models.CASCADE, null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="trafficsignal",
            name="segment_id",
            field=models.ForeignKey(
                to="rest_api.segment", on_delete=models.CASCADE, null=True, blank=True
            ),
        ),
    ]
