import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from django.contrib.admin.options import csrf_protect_m
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import FieldDoesNotExist, FieldError, SuspiciousOperation
from django.db import DatabaseError, DataError, models
from django.db.models import Avg, Count, Max, Min, Sum
from django.http import HttpRequest
from django.template.response import TemplateResponse

from django_easy_query_builder.builders import QueryBuilder
from django_easy_query_builder.parsers import (
    ALLOWED_DJANGO_OPERATORS,
    DJANGO_OPERATOR_SEQUENCE,
    FilterNode,
    QueryParser,
    StructuredQueryParser,
)
from django_easy_query_builder.project_types import QueryBuilderModelAdminMixinProtocol
from django_easy_query_builder.validators import QTreeValidator

_FIELD_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALIAS_SEGMENT_RE = re.compile(r"[^A-Za-z0-9]+")


class QueryBuilderAdminMixin:
    query_builder_fields: List[str] = []
    advanced_search_fields: List[str] = []
    advanced_search_lookups: List[str] = ["__all__"]
    advanced_query_param: str = "advanced_query"
    change_list_template: str = "admin/django_easy_query_builder/change_list.html"
    _TRANSFORM_ANNOTATIONS = {
        "count": Count,
        "sum": Sum,
        "avg": Avg,
        "min": Min,
        "max": Max,
    }

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

    def get_allowed_query_lookups(self) -> List[str]:
        configured = self.advanced_search_lookups
        if isinstance(configured, str):
            raw_lookups: List[str] = [configured]
        else:
            raw_lookups = list(configured)

        include_all = False
        selected: Set[str] = set()
        for raw_lookup in raw_lookups:
            if not isinstance(raw_lookup, str):
                raise ValueError("advanced_search_lookups must contain string values.")

            lookup = raw_lookup.strip()
            if not lookup:
                continue

            if lookup == "__all__":
                include_all = True
                break

            if lookup.startswith("__"):
                lookup = lookup[2:]

            if lookup in {"eq", "ne"}:
                lookup = "exact"

            if lookup not in ALLOWED_DJANGO_OPERATORS:
                raise ValueError(
                    f"Unsupported lookup '{raw_lookup}' in advanced_search_lookups."
                )

            selected.add(lookup)

        if include_all:
            return list(DJANGO_OPERATOR_SEQUENCE)

        if not selected:
            raise ValueError(
                "advanced_search_lookups must contain at least one lookup or '__all__'."
            )

        return [lookup for lookup in DJANGO_OPERATOR_SEQUENCE if lookup in selected]

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
            allowed_lookups = self.get_allowed_query_lookups()
            structured_payload = self._decode_structured_query(raw_query)
            filter_tree = self._parse_advanced_query(
                raw_query,
                structured_payload=structured_payload,
                allowed_lookups=allowed_lookups,
            )
            transform_annotations, transform_filter_aliases = (
                self._build_transform_annotations(structured_payload)
            )

            allowed_fields = (
                list(self.get_allowed_query_fields()) + transform_filter_aliases
            )
            validator = QTreeValidator(
                sorted(set(allowed_fields)),
                allowed_lookups=set(allowed_lookups),
            )
            validator.validate(filter_tree)

            for alias, annotation in transform_annotations:
                queryset = queryset.annotate(**{alias: annotation})

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
            "availableLookups": self.get_allowed_query_lookups(),
            "queryParam": self.advanced_query_param,
            "initialQuery": request.GET.get(self.advanced_query_param, ""),
            "enableTransforms": False,
        }

    def _decode_structured_query(self, raw_query: str) -> Optional[Dict[str, Any]]:
        stripped = raw_query.strip()
        if not stripped.startswith("{"):
            return None

        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise SyntaxError("Advanced query JSON payload must be an object.")
        return payload

    def _parse_advanced_query(
        self,
        raw_query: str,
        structured_payload: Optional[Dict[str, Any]] = None,
        allowed_lookups: Optional[List[str]] = None,
    ) -> FilterNode:
        stripped = raw_query.strip()

        if structured_payload is not None:
            return StructuredQueryParser(
                structured_payload,
                field_types=self.get_allowed_query_field_types(),
                allowed_django_operators=(
                    set(allowed_lookups) if allowed_lookups is not None else None
                ),
            ).parse()

        if stripped.startswith("{"):
            return StructuredQueryParser(
                stripped,
                field_types=self.get_allowed_query_field_types(),
                allowed_django_operators=(
                    set(allowed_lookups) if allowed_lookups is not None else None
                ),
            ).parse()

        return QueryParser(stripped).parse()

    def _build_transform_annotations(
        self,
        structured_payload: Optional[Dict[str, Any]],
    ) -> Tuple[List[Tuple[str, models.Aggregate]], List[str]]:
        if structured_payload is None:
            return [], []

        transform_by_id: Dict[str, Dict[str, str]] = {}
        alias_definitions: Dict[str, Dict[str, str]] = {}
        self._collect_transform_definitions(
            structured_payload,
            transform_by_id,
            alias_definitions,
        )

        if not transform_by_id:
            return [], []

        self._validate_transform_sources(alias_definitions)
        referenced_transform_ids = self._collect_referenced_transform_ids(
            structured_payload,
            transform_by_id,
        )

        if not referenced_transform_ids:
            return [], []

        needed_aliases = self._resolve_needed_transform_aliases(
            referenced_transform_ids,
            transform_by_id,
            alias_definitions,
        )
        ordered_aliases = self._toposort_transform_aliases(
            needed_aliases,
            alias_definitions,
        )

        annotations: List[Tuple[str, models.Aggregate]] = []
        for alias in ordered_aliases:
            definition = alias_definitions[alias]
            transform_name = definition["transform"]
            annotation_factory = self._TRANSFORM_ANNOTATIONS[transform_name]
            source_value = definition["source_value"]
            annotations.append((alias, annotation_factory(source_value)))

        filter_aliases = sorted(
            {
                transform_by_id[transform_id]["alias"]
                for transform_id in referenced_transform_ids
            }
        )
        return annotations, filter_aliases

    def _collect_transform_definitions(
        self,
        group: Dict[str, Any],
        transform_by_id: Dict[str, Dict[str, str]],
        alias_definitions: Dict[str, Dict[str, str]],
    ) -> None:
        conditions = group.get("conditions", [])
        if not isinstance(conditions, list):
            raise SyntaxError("group.conditions must be a list.")

        for condition in conditions:
            if not isinstance(condition, dict):
                raise SyntaxError("Each condition must be an object.")
            self._collect_condition_transforms(
                condition,
                transform_by_id,
                alias_definitions,
            )

        child_groups = group.get("groups", [])
        if not isinstance(child_groups, list):
            raise SyntaxError("group.groups must be a list.")

        for child_group in child_groups:
            if not isinstance(child_group, dict):
                raise SyntaxError("Each nested group must be an object.")
            self._collect_transform_definitions(
                child_group,
                transform_by_id,
                alias_definitions,
            )

    def _collect_condition_transforms(
        self,
        condition: Dict[str, Any],
        transform_by_id: Dict[str, Dict[str, str]],
        alias_definitions: Dict[str, Dict[str, str]],
    ) -> None:
        transforms = condition.get("transforms")
        if transforms is None:
            return
        if not isinstance(transforms, list):
            raise SyntaxError("condition.transforms must be a list when provided.")
        if not transforms:
            return

        field = condition.get("field")
        if not isinstance(field, str) or not field.strip():
            raise SyntaxError("Transform conditions require a non-empty 'field'.")

        source_kind = "alias" if self._condition_has_alias_ref(condition) else "field"
        source_value = field.strip()

        for transform in transforms:
            if not isinstance(transform, dict):
                raise SyntaxError("Each transform must be an object.")

            transform_id = transform.get("id")
            if not isinstance(transform_id, str) or not transform_id.strip():
                raise SyntaxError("Each transform requires a non-empty 'id'.")
            transform_id = transform_id.strip()
            if transform_id in transform_by_id:
                raise SyntaxError(f"Duplicate transform id '{transform_id}'.")

            transform_name = transform.get("value")
            if transform_name not in self._TRANSFORM_ANNOTATIONS:
                raise SyntaxError(f"Unsupported transform '{transform_name}'.")

            normalized_source = source_value
            if source_kind == "field":
                normalized_source = self._to_django_path(source_value)

            alias = self._make_transform_alias(transform_name, source_value)
            transform_definition = {
                "id": transform_id,
                "alias": alias,
                "transform": transform_name,
                "source_kind": source_kind,
                "source_value": normalized_source,
            }
            transform_by_id[transform_id] = transform_definition

            signature = (
                transform_name,
                source_kind,
                normalized_source,
            )
            existing_definition = alias_definitions.get(alias)
            if existing_definition is None:
                alias_definitions[alias] = transform_definition
            else:
                existing_signature = (
                    existing_definition["transform"],
                    existing_definition["source_kind"],
                    existing_definition["source_value"],
                )
                if existing_signature != signature:
                    raise SyntaxError(
                        f"Conflicting transform definitions for alias '{alias}'."
                    )

            source_kind = "alias"
            source_value = alias

    def _condition_has_alias_ref(self, condition: Dict[str, Any]) -> bool:
        field_ref = condition.get("fieldRef")
        if field_ref is None:
            return False
        if not isinstance(field_ref, dict):
            raise SyntaxError("condition.fieldRef must be an object when provided.")
        if field_ref.get("type") != "alias":
            raise SyntaxError("condition.fieldRef.type must be 'alias' when provided.")
        transform_id = field_ref.get("transformId")
        if not isinstance(transform_id, str) or not transform_id.strip():
            raise SyntaxError(
                "condition.fieldRef.transformId must be a non-empty string."
            )
        return True

    def _validate_transform_sources(
        self,
        alias_definitions: Dict[str, Dict[str, str]],
    ) -> None:
        allowed_fields = set(self.get_allowed_query_fields())
        known_aliases = set(alias_definitions.keys())

        for alias, definition in alias_definitions.items():
            source_kind = definition["source_kind"]
            source_value = definition["source_value"]

            if source_kind == "field":
                if source_value not in allowed_fields:
                    raise SyntaxError(
                        f"Transform source field '{source_value}' is not allowed."
                    )
                continue

            if source_kind == "alias" and source_value not in known_aliases:
                raise SyntaxError(
                    f"Transform alias source '{source_value}' is not defined."
                )

            if source_kind not in {"field", "alias"}:
                raise SyntaxError(
                    f"Unsupported transform source kind '{source_kind}' for alias '{alias}'."
                )

    def _collect_referenced_transform_ids(
        self,
        group: Dict[str, Any],
        transform_by_id: Dict[str, Dict[str, str]],
    ) -> Set[str]:
        referenced: Set[str] = set()

        conditions = group.get("conditions", [])
        if not isinstance(conditions, list):
            raise SyntaxError("group.conditions must be a list.")

        for condition in conditions:
            if not isinstance(condition, dict):
                raise SyntaxError("Each condition must be an object.")
            if bool(condition.get("isVariableOnly", False)):
                continue

            field_ref = condition.get("fieldRef")
            if field_ref is None:
                continue
            if not isinstance(field_ref, dict):
                raise SyntaxError("condition.fieldRef must be an object when provided.")
            if field_ref.get("type") != "alias":
                raise SyntaxError(
                    "condition.fieldRef.type must be 'alias' when provided."
                )

            transform_id = field_ref.get("transformId")
            if not isinstance(transform_id, str) or not transform_id.strip():
                raise SyntaxError(
                    "condition.fieldRef.transformId must be a non-empty string."
                )
            transform_id = transform_id.strip()

            transform_definition = transform_by_id.get(transform_id)
            if transform_definition is None:
                raise SyntaxError(f"Unknown transform reference '{transform_id}'.")

            field = condition.get("field")
            if not isinstance(field, str) or not field.strip():
                raise SyntaxError(
                    "Alias filter conditions require a non-empty 'field'."
                )
            if field.strip() != transform_definition["alias"]:
                raise SyntaxError(
                    "condition.field must match the referenced transform alias."
                )

            referenced.add(transform_id)

        child_groups = group.get("groups", [])
        if not isinstance(child_groups, list):
            raise SyntaxError("group.groups must be a list.")
        for child_group in child_groups:
            if not isinstance(child_group, dict):
                raise SyntaxError("Each nested group must be an object.")
            referenced.update(
                self._collect_referenced_transform_ids(child_group, transform_by_id)
            )

        return referenced

    def _resolve_needed_transform_aliases(
        self,
        referenced_transform_ids: Set[str],
        transform_by_id: Dict[str, Dict[str, str]],
        alias_definitions: Dict[str, Dict[str, str]],
    ) -> Set[str]:
        pending = [
            transform_by_id[transform_id]["alias"]
            for transform_id in referenced_transform_ids
        ]
        needed_aliases: Set[str] = set()

        while pending:
            alias = pending.pop()
            if alias in needed_aliases:
                continue
            needed_aliases.add(alias)

            definition = alias_definitions.get(alias)
            if definition is None:
                raise SyntaxError(f"Unknown transform alias '{alias}'.")

            if definition["source_kind"] != "alias":
                continue

            source_alias = definition["source_value"]
            if source_alias not in alias_definitions:
                raise SyntaxError(
                    f"Transform alias source '{source_alias}' is not defined."
                )
            pending.append(source_alias)

        return needed_aliases

    def _toposort_transform_aliases(
        self,
        needed_aliases: Set[str],
        alias_definitions: Dict[str, Dict[str, str]],
    ) -> List[str]:
        ordered: List[str] = []
        visiting: Dict[str, bool] = {}

        def visit(alias: str) -> None:
            if alias in visiting:
                if visiting[alias]:
                    raise SyntaxError("Cyclic transform dependency detected.")
                return

            visiting[alias] = True
            definition = alias_definitions[alias]
            if definition["source_kind"] == "alias":
                source_alias = definition["source_value"]
                if source_alias in needed_aliases:
                    visit(source_alias)
            visiting[alias] = False
            ordered.append(alias)

        for alias in sorted(needed_aliases):
            visit(alias)

        return ordered

    def _to_django_path(self, field: str) -> str:
        orm_path = field.strip().replace(".", "__")
        if not orm_path:
            raise SyntaxError("Field path cannot be empty.")

        parts = orm_path.split("__")
        if any(not part for part in parts):
            raise SyntaxError("Field path contains an empty segment.")

        for part in parts:
            if not _FIELD_SEGMENT_RE.match(part):
                raise SyntaxError(f"Invalid field path segment '{part}'.")

        return orm_path

    def _make_transform_alias(self, transform_name: str, source: str) -> str:
        cleaned_source = _ALIAS_SEGMENT_RE.sub("_", source)
        if not cleaned_source:
            cleaned_source = "value"
        return f"{transform_name}_{cleaned_source}"

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
