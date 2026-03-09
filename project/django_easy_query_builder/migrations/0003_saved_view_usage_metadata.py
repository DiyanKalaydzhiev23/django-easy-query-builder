from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_easy_query_builder", "0002_upgrade_query_hash_to_sha256"),
    ]

    operations = [
        migrations.AddField(
            model_name="view",
            name="last_used_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="view",
            name="usage_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
