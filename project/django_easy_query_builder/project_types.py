from typing import Protocol
from django.contrib.admin.options import csrf_protect_m
from django.db import models
from django.http import HttpRequest
from django.template.response import TemplateResponse


class ModelAdminProtocol(Protocol):
    model: models.Model

    @csrf_protect_m
    def changelist_view(self, request: HttpRequest, extra_context: dict=None) -> TemplateResponse:
        ...


class QueryBuilderAdminMixinProtocol(Protocol):
    query_builder_fields: list[str]

    def get_query_builder_fields_mapping(self) -> list[dict]:
        ...


class QueryBuilderModelAdminMixinProtocol(ModelAdminProtocol, QueryBuilderAdminMixinProtocol):
    ...
