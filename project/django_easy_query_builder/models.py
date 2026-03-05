from django.conf import settings
from django.db import models

from django_easy_query_builder.saved_views import JSONValue, build_query_hash


class View(models.Model):
    name = models.CharField(max_length=120)
    model_label = models.CharField(max_length=255, db_index=True)
    query_payload = models.JSONField()
    query_hash = models.CharField(max_length=64, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="saved_query_views",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["model_label", "query_hash"],
                name="unique_saved_query_view_per_model",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.model_label})"

    @classmethod
    def build_query_hash(cls: type["View"], payload: dict[str, JSONValue]) -> str:
        return build_query_hash(payload)
