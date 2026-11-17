from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rest_api", "0041_alert_rest_api_al_segment_31dc1c_idx_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="historicspeed",
            index=models.Index(
                fields=["day_type", "temporal_segment"],
                name="rest_api_hi_day_typ_d02b40_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="speed",
            index=models.Index(
                fields=["timestamp", "temporal_segment"],
                name="rest_api_sp_timesta_9ff1ee_idx",
            ),
        ),
    ]
