from typing import Any, Dict, List, Protocol, Union

from django.contrib.admin.options import csrf_protect_m
from django.db import models
from django.http import HttpRequest
from django.template.response import TemplateResponse


class ModelAdminProtocol(Protocol):
    model: models.Model

    @csrf_protect_m
    def changelist_view(
        self: "ModelAdminProtocol",
        request: HttpRequest,
        extra_context: Union[Dict[str, Any], None] = None,
    ) -> TemplateResponse: ...


class QueryBuilderAdminMixinProtocol(Protocol):
    query_builder_fields: List[str]
    advanced_search_fields: List[str]
    change_list_template: str

    def get_allowed_query_fields(self) -> List[str]: ...
    def get_allowed_query_field_types(self) -> Dict[str, str]: ...
    def get_query_builder_frontend_config(
        self, request: HttpRequest
    ) -> Dict[str, Any]: ...

    def get_query_builder_fields_mapping(
        self: "QueryBuilderAdminMixinProtocol",
    ) -> List[Dict[str, Any]]: ...


class QueryBuilderModelAdminMixinProtocol(
    ModelAdminProtocol, QueryBuilderAdminMixinProtocol
): ...
