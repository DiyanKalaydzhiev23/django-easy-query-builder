import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from django.contrib import messages
from django.contrib.admin.options import csrf_protect_m
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import FieldDoesNotExist, FieldError, SuspiciousOperation
from django.db import DatabaseError, DataError, models
from django.db.models import Avg, Count, Max, Min, Subquery, Sum, Value
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
            transform_annotations: List[Tuple[str, models.Expression]] = []
            transform_filter_aliases: List[str] = []
            transform_catalog: Optional[Dict[str, Dict[str, str]]] = None

            if structured_payload is not None:
                transform_catalog, alias_definitions = self._collect_transform_catalog(
                    structured_payload
                )
                self._normalize_payload_value_alias_references(
                    structured_payload,
                    transform_catalog,
                )
                transform_annotations, transform_filter_aliases = (
                    self._build_transform_annotations(
                        structured_payload,
                        base_queryset=queryset,
                        transform_by_id=transform_catalog,
                        alias_definitions=alias_definitions,
                    )
                )

            filter_tree = self._parse_advanced_query(
                raw_query,
                structured_payload=structured_payload,
                allowed_lookups=allowed_lookups,
            )

            validator = QTreeValidator(
                sorted(set(self.get_allowed_query_fields())),
                allowed_aliases=transform_filter_aliases,
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
            message = f"Invalid advanced query payload: {exc}"
            if getattr(request, "_advanced_query_suppress_errors", False):
                if not getattr(request, "_advanced_query_error_reported", False):
                    self.message_user(request, message, level=messages.ERROR)
                    request._advanced_query_error_reported = True
                return queryset
            raise SuspiciousOperation(message) from exc

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
        request._advanced_query_suppress_errors = True
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
        base_queryset: Optional[models.QuerySet[models.Model]] = None,
        transform_by_id: Optional[Dict[str, Dict[str, str]]] = None,
        alias_definitions: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Tuple[List[Tuple[str, models.Expression]], List[str]]:
        if structured_payload is None:
            return [], []

        catalog = transform_by_id
        alias_catalog = alias_definitions
        if catalog is None or alias_catalog is None:
            catalog, alias_catalog = self._collect_transform_catalog(structured_payload)

        if not catalog:
            return [], []
        referenced_transform_ids = self._collect_referenced_transform_ids(
            structured_payload,
            catalog,
        )

        if not referenced_transform_ids:
            return [], []

        needed_aliases = self._resolve_needed_transform_aliases(
            referenced_transform_ids,
            catalog,
            alias_catalog,
        )
        ordered_aliases = self._toposort_transform_aliases(
            needed_aliases,
            alias_catalog,
        )

        annotations: List[Tuple[str, models.Expression]] = []
        for alias in ordered_aliases:
            definition = alias_catalog[alias]
            annotations.append(
                (
                    alias,
                    self._build_transform_annotation_expression(
                        definition,
                        base_queryset,
                    ),
                )
            )

        filter_aliases = sorted(
            {
                catalog[transform_id]["alias"]
                for transform_id in referenced_transform_ids
            }
        )
        return annotations, filter_aliases

    def _build_transform_annotation_expression(
        self,
        definition: Dict[str, str],
        base_queryset: Optional[models.QuerySet[models.Model]],
    ) -> models.Expression:
        transform_name = definition["transform"]
        annotation_factory = self._TRANSFORM_ANNOTATIONS[transform_name]
        source_value = definition["source_value"]

        if self._should_use_scalar_transform_annotation(definition):
            return self._build_scalar_transform_subquery(
                base_queryset,
                annotation_factory,
                source_value,
            )

        return annotation_factory(source_value)

    def _should_use_scalar_transform_annotation(
        self,
        definition: Dict[str, str],
    ) -> bool:
        if definition["source_kind"] != "field":
            return False

        source_value = definition["source_value"]
        if "__" in source_value:
            return False

        resolved_field = self._resolve_field_path(source_value)
        if resolved_field is None:
            return False

        return not getattr(resolved_field, "is_relation", False)

    def _build_scalar_transform_subquery(
        self,
        base_queryset: Optional[models.QuerySet[models.Model]],
        annotation_factory: type[models.Aggregate],
        source_value: str,
    ) -> models.Subquery:
        scalar_group_alias = "_dqe_scalar_group"
        scalar_value_alias = "_dqe_scalar_value"
        queryset = (
            base_queryset
            if base_queryset is not None
            else self.model._default_manager.all()
        )

        scalar_queryset = (
            queryset.order_by()
            .annotate(**{scalar_group_alias: Value(1)})
            .values(scalar_group_alias)
            .annotate(**{scalar_value_alias: annotation_factory(source_value)})
            .values(scalar_value_alias)[:1]
        )
        return Subquery(scalar_queryset)

    def _collect_transform_catalog(
        self,
        structured_payload: Dict[str, Any],
    ) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
        transform_by_id: Dict[str, Dict[str, str]] = {}
        alias_definitions: Dict[str, Dict[str, str]] = {}
        self._collect_transform_definitions(
            structured_payload,
            transform_by_id,
            alias_definitions,
        )
        if transform_by_id:
            self._validate_transform_sources(alias_definitions)
        return transform_by_id, alias_definitions

    def _normalize_payload_value_alias_references(
        self,
        root_group: Dict[str, Any],
        transform_by_id: Dict[str, Dict[str, str]],
    ) -> None:
        if not transform_by_id:
            return

        field_types = self.get_allowed_query_field_types()
        transforms_per_group: Dict[int, List[Dict[str, str]]] = {}
        children_by_group: Dict[int, List[int]] = {}
        parent_by_group: Dict[int, int] = {}

        def collect(group: Dict[str, Any]) -> int:
            group_key = id(group)
            direct_transforms: List[Dict[str, str]] = []

            conditions = group.get("conditions", [])
            if not isinstance(conditions, list):
                raise SyntaxError("group.conditions must be a list.")
            for condition in conditions:
                if not isinstance(condition, dict):
                    raise SyntaxError("Each condition must be an object.")
                transforms = condition.get("transforms")
                if not isinstance(transforms, list):
                    continue
                for transform in transforms:
                    if not isinstance(transform, dict):
                        continue
                    transform_id = transform.get("id")
                    if not isinstance(transform_id, str):
                        continue
                    transform_definition = transform_by_id.get(transform_id.strip())
                    if transform_definition is not None:
                        direct_transforms.append(transform_definition)

            transforms_per_group[group_key] = direct_transforms

            child_keys: List[int] = []
            child_groups = group.get("groups", [])
            if not isinstance(child_groups, list):
                raise SyntaxError("group.groups must be a list.")
            for child in child_groups:
                if not isinstance(child, dict):
                    raise SyntaxError("Each nested group must be an object.")
                child_key = collect(child)
                parent_by_group[child_key] = group_key
                child_keys.append(child_key)

            children_by_group[group_key] = child_keys
            return group_key

        root_key = collect(root_group)
        subtree_transforms: Dict[int, List[Dict[str, str]]] = {}

        def gather_subtree(group_key: int) -> List[Dict[str, str]]:
            collected = list(transforms_per_group.get(group_key, []))
            for child_key in children_by_group.get(group_key, []):
                collected.extend(gather_subtree(child_key))
            subtree_transforms[group_key] = collected
            return collected

        gather_subtree(root_key)

        alias_lookup_by_group: Dict[int, Dict[str, Dict[str, str]]] = {}
        for group_key in subtree_transforms:
            accessible = list(subtree_transforms.get(group_key, []))
            current_parent = parent_by_group.get(group_key)
            while current_parent is not None:
                accessible.extend(transforms_per_group.get(current_parent, []))
                current_parent = parent_by_group.get(current_parent)
            alias_lookup_by_group[group_key] = {
                definition["alias"]: definition for definition in accessible
            }

        def normalize_group(group: Dict[str, Any]) -> None:
            group_key = id(group)
            alias_lookup = alias_lookup_by_group.get(group_key, {})

            conditions = group.get("conditions", [])
            if not isinstance(conditions, list):
                raise SyntaxError("group.conditions must be a list.")
            for condition in conditions:
                if not isinstance(condition, dict):
                    raise SyntaxError("Each condition must be an object.")
                if bool(condition.get("isVariableOnly", False)):
                    continue

                raw_value = condition.get("value")
                if condition.get("valueRef") is not None:
                    continue
                if not isinstance(raw_value, str):
                    continue

                value = raw_value.strip()
                if not value:
                    continue

                matched_alias = alias_lookup.get(value)
                if matched_alias is not None:
                    condition["value"] = matched_alias["alias"]
                    condition["valueRef"] = {
                        "type": "alias",
                        "transformId": matched_alias["id"],
                    }
                    continue

                if not self._should_treat_value_as_variable_candidate(
                    condition,
                    field_types,
                ):
                    continue

                if "_" in value and _FIELD_SEGMENT_RE.match(value):
                    raise SyntaxError(f"Unknown variable '{value}'.")

            child_groups = group.get("groups", [])
            if not isinstance(child_groups, list):
                raise SyntaxError("group.groups must be a list.")
            for child in child_groups:
                if not isinstance(child, dict):
                    raise SyntaxError("Each nested group must be an object.")
                normalize_group(child)

        normalize_group(root_group)

    def _should_treat_value_as_variable_candidate(
        self,
        condition: Dict[str, Any],
        field_types: Dict[str, str],
    ) -> bool:
        operator = condition.get("operator", "equals")
        if not isinstance(operator, str):
            return False

        normalized_operator = operator.strip()
        if normalized_operator.startswith("__"):
            normalized_operator = normalized_operator[2:]
        if normalized_operator.startswith("not_"):
            normalized_operator = normalized_operator[4:]

        if normalized_operator in {"in", "range", "isnull"}:
            return False

        if condition.get("fieldRef") is not None:
            return True

        field = condition.get("field")
        if not isinstance(field, str) or not field.strip():
            return False

        field_path = self._to_django_path(field)
        field_type = field_types.get(field_path)
        return field_type not in {
            "CharField",
            "TextField",
            "EmailField",
            "SlugField",
            "URLField",
        }

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

            field_transform_id = self._resolve_condition_transform_reference(
                condition,
                "fieldRef",
                transform_by_id,
            )
            if field_transform_id is not None:
                transform_definition = transform_by_id[field_transform_id]
                field = condition.get("field")
                if not isinstance(field, str) or not field.strip():
                    raise SyntaxError(
                        "Alias filter conditions require a non-empty 'field'."
                    )
                if field.strip() != transform_definition["alias"]:
                    raise SyntaxError(
                        "condition.field must match the referenced transform alias."
                    )
                referenced.add(field_transform_id)

            value_transform_id = self._resolve_condition_transform_reference(
                condition,
                "valueRef",
                transform_by_id,
            )
            if value_transform_id is not None:
                transform_definition = transform_by_id[value_transform_id]
                value = condition.get("value")
                if not isinstance(value, str) or not value.strip():
                    raise SyntaxError(
                        "Variable comparison conditions require a non-empty 'value'."
                    )
                if value.strip() != transform_definition["alias"]:
                    raise SyntaxError(
                        "condition.value must match the referenced transform alias."
                    )
                referenced.add(value_transform_id)

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

    def _resolve_condition_transform_reference(
        self,
        condition: Dict[str, Any],
        key: str,
        transform_by_id: Dict[str, Dict[str, str]],
    ) -> Optional[str]:
        ref = condition.get(key)
        if ref is None:
            return None
        if not isinstance(ref, dict):
            raise SyntaxError(f"condition.{key} must be an object when provided.")
        if ref.get("type") != "alias":
            raise SyntaxError(f"condition.{key}.type must be 'alias' when provided.")

        transform_id = ref.get("transformId")
        if not isinstance(transform_id, str) or not transform_id.strip():
            raise SyntaxError(
                f"condition.{key}.transformId must be a non-empty string."
            )

        normalized_transform_id = transform_id.strip()
        if normalized_transform_id not in transform_by_id:
            raise SyntaxError(
                f"Unknown transform reference '{normalized_transform_id}'."
            )

        return normalized_transform_id

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
