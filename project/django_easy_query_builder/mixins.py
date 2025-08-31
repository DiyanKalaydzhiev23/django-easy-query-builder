from typing import Any, Dict, List

from django.contrib.admin.options import csrf_protect_m
from django.http import HttpRequest
from django.template.response import TemplateResponse

from django_easy_query_builder.project_types import QueryBuilderModelAdminMixinProtocol


class QueryBuilderAdminMixin:
    query_builder_fields: List[str] = []

    def get_query_builder_fields_mapping(
        self: QueryBuilderModelAdminMixinProtocol,
    ) -> List[Dict[str, Any]]:
        """
        Returns a list of dicts with info about the allowed fields for this model.
        """
        model_fields = {}
        for field in self.model._meta.get_fields():
            model_fields[field.name] = field

        result = []

        for field_name in self.query_builder_fields:
            field = model_fields.get(field_name)
            if field:
                field_info = {
                    "name": field.name,
                    "type": field.get_internal_type(),
                    "verbose_name": getattr(field, "verbose_name", field.name),
                }
                if field.is_relation:
                    field_info["related_model"] = field.related_model.__name__

                result.append(field_info)

        return result

    @csrf_protect_m
    def changelist_view(
        self: QueryBuilderModelAdminMixinProtocol,
        request: HttpRequest,
        extra_context: dict = None,
    ) -> TemplateResponse:
        if extra_context is None:
            extra_context = {}

        extra_context["query_builder_fields"] = self.get_query_builder_fields_mapping()

        return super().changelist_view(request, extra_context=extra_context)
