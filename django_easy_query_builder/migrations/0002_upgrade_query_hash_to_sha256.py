from django.db import migrations, models


def recalculate_query_hashes(apps: object, schema_editor: object) -> None:
    view_model = apps.get_model("django_easy_query_builder", "View")
    from django_easy_query_builder.saved_views import build_query_hash

    for saved_view in view_model.objects.all().iterator():
        payload = saved_view.query_payload
        if not isinstance(payload, dict):
            continue
        saved_view.query_hash = build_query_hash(payload)
        saved_view.save(update_fields=["query_hash"])


class Migration(migrations.Migration):
    dependencies = [
        ("django_easy_query_builder", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="view",
            name="query_hash",
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.RunPython(
            recalculate_query_hashes,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
