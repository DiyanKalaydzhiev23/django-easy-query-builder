import json
from typing import Dict, List, Optional

from django.contrib.admin.options import csrf_protect_m
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import FieldDoesNotExist, FieldError, SuspiciousOperation
from django.db import DatabaseError, DataError, models
from django.http import HttpRequest
from django.template.response import TemplateResponse

from django_easy_query_builder.builders import QueryBuilder
from django_easy_query_builder.parsers import (
    FilterNode,
    QueryParser,
    StructuredQueryParser,
)
from django_easy_query_builder.project_types import QueryBuilderModelAdminMixinProtocol
from django_easy_query_builder.validators import QTreeValidator


class QueryBuilderAdminMixin:
    query_builder_fields: List[str] = []
    advanced_search_fields: List[str] = []
    advanced_query_param: str = "advanced_query"
    change_list_template: str = "admin/django_easy_query_builder/change_list.html"

    class QueryBuilderChangeList(ChangeList):
        def get_filters_params(
            self, params: Optional[Dict[str, List[str]]] = None
        ) -> Dict[str, List[str]]:
            lookup_params = super().get_filters_params(params=params)
            advanced_query_param = getattr(
                self.model_admin,
                "advanced_query_param",
                "advanced_query",
            )
            lookup_params.pop(advanced_query_param, None)
            return lookup_params

    def get_allowed_query_fields(self) -> List[str]:
        if self.advanced_search_fields:
            return list(self.advanced_search_fields)
        return list(self.query_builder_fields)

    def get_query_builder_fields_mapping(
        self: QueryBuilderModelAdminMixinProtocol,
    ) -> List[Dict[str, Any]]:
        """
        Returns a list of dicts with info about the allowed fields for this model.
        """
        result = []

        for field_path in self.get_allowed_query_fields():
            resolved_field = self._resolve_field_path(field_path)
            if resolved_field is None:
                continue

            type_name = self._field_type_name(resolved_field)
            field_info = {
                "name": field_path.replace("__", "."),
                "orm_path": field_path,
                "type": type_name,
                "verbose_name": getattr(resolved_field, "verbose_name", field_path),
            }
            if getattr(resolved_field, "is_relation", False):
                related_model = getattr(resolved_field, "related_model", None)
                if related_model is not None:
                    field_info["related_model"] = related_model.__name__

            result.append(field_info)

        return result

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[models.Model]:
        queryset = super().get_queryset(request)

        raw_query = request.GET.get(self.advanced_query_param)
        if not raw_query:
            return queryset

        try:
            filter_tree = self._parse_advanced_query(raw_query)
            validator = QTreeValidator(self.get_allowed_query_fields())
            validator.validate(filter_tree)
            query_builder = QueryBuilder(root_model=self.model)
            return queryset.filter(query_builder.build_q(filter_tree))
        except (
            ValueError,
            SyntaxError,
            json.JSONDecodeError,
            FieldError,
            DataError,
            DatabaseError,
            TypeError,
        ) as exc:
            raise SuspiciousOperation(f"Invalid advanced query payload: {exc}") from exc

    def get_changelist(
        self, request: HttpRequest, **kwargs: object
    ) -> type[ChangeList]:
        return self.QueryBuilderChangeList

    @csrf_protect_m
    def changelist_view(
        self: QueryBuilderModelAdminMixinProtocol,
        request: HttpRequest,
        extra_context: Optional[dict] = None,
    ) -> TemplateResponse:
        if extra_context is None:
            extra_context = {}

        extra_context["query_builder_fields"] = self.get_query_builder_fields_mapping()
        extra_context["query_builder_frontend_config"] = (
            self.get_query_builder_frontend_config(request)
        )

        return super().changelist_view(request, extra_context=extra_context)

    def get_query_builder_frontend_config(self, request: HttpRequest) -> Dict[str, Any]:
        return {
            "availableFields": [
                item["name"] for item in self.get_query_builder_fields_mapping()
            ],
            "queryParam": self.advanced_query_param,
            "initialQuery": request.GET.get(self.advanced_query_param, ""),
            "enableTransforms": False,
        }

    def _parse_advanced_query(self, raw_query: str) -> FilterNode:
        stripped = raw_query.strip()

        if stripped.startswith("{"):
            return StructuredQueryParser(
                stripped,
                field_types=self.get_allowed_query_field_types(),
            ).parse()

        return QueryParser(stripped).parse()

    def get_allowed_query_field_types(self) -> Dict[str, str]:
        field_types: Dict[str, str] = {}
        for field_path in self.get_allowed_query_fields():
            resolved_field = self._resolve_field_path(field_path)
            if resolved_field is None:
                continue
            field_types[field_path] = self._field_type_name(resolved_field)
        return field_types

    def _resolve_field_path(self, field_path: str) -> Optional[models.Field]:
        current_model = self.model
        current_field = None

        for part in field_path.split("__"):
            try:
                current_field = current_model._meta.get_field(part)
            except FieldDoesNotExist:
                return None

            if current_field.is_relation:
                related_model = getattr(current_field, "related_model", None)
                if related_model is not None:
                    current_model = related_model

        return current_field

    def _field_type_name(self, field: object) -> str:
        get_internal_type = getattr(field, "get_internal_type", None)
        if callable(get_internal_type):
            return get_internal_type()
        return field.__class__.__name__


class AdvancedSearchAdminMixin(QueryBuilderAdminMixin):
    pass
