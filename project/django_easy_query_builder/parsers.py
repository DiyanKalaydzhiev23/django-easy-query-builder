import json
import re
from typing import Any, Dict, List, Optional, Union

FilterNode = Union[List["FilterNode"], Dict[str, Any]]

DJANGO_OPERATOR_SEQUENCE = (
    "exact",
    "iexact",
    "contains",
    "icontains",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "isnull",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "range",
    "date",
    "year",
    "month",
)

ALLOWED_DJANGO_OPERATORS = set(DJANGO_OPERATOR_SEQUENCE)

FRONTEND_OPERATOR_LOOKUPS = {
    "equals": "exact",
    "not_equals": "exact",
    "contains": "contains",
    "not_contains": "contains",
    "greater_than": "gt",
    "less_than": "lt",
    "in": "in",
    "not_in": "in",
}

NEGATED_FRONTEND_OPERATORS = {"not_equals", "not_contains", "not_in"}
OPERATOR_ALIASES = {
    "eq": "exact",
    "ne": "exact",
    "starts_with": "startswith",
    "istarts_with": "istartswith",
    "i_starts_with": "istartswith",
    "ends_with": "endswith",
    "iends_with": "iendswith",
    "i_ends_with": "iendswith",
}
NEGATED_OPERATOR_ALIASES = {"ne"}

_SUPPORTED_TRANSFORMS = {"count", "sum", "avg", "min", "max"}

_FIELD_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

ScalarValue = Union[str, int, float, bool, None]
NormalizedValue = Union[ScalarValue, List[ScalarValue]]


class QueryParser:
    def __init__(self, query: str) -> None:
        self.query = query
        self.tokens: List[str] = []
        self.pos = 0
        self._token_handlers = {
            "~": self._handle_not,
            "(": self._handle_group,
            "&": lambda: self._handle_operator("&"),
            "|": lambda: self._handle_operator("|"),
        }

    def tokenize(self) -> List[str]:
        pattern = r"Q\([^\)]*\)|[&|()~]"
        self.tokens = re.findall(pattern, self.query)
        return self.tokens

    def parse(self) -> FilterNode:
        self.tokenize()
        return self.parse_expression()

    def parse_expression(self) -> FilterNode:
        nodes: List[FilterNode] = []

        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]

            if token.startswith("Q("):
                nodes.append(self.parse_condition())
                continue

            if token == ")":
                self.pos += 1
                break

            handler = self._token_handlers.get(token)

            if handler is None:
                raise SyntaxError(f"Unknown token {token}")

            nodes.append(handler())
        return nodes

    def _handle_not(self) -> Dict[str, FilterNode]:
        self.pos += 1

        if self.pos >= len(self.tokens):
            raise SyntaxError("~ must precede Q(...) or ( ... )")

        next_token = self.tokens[self.pos]

        if next_token.startswith("Q("):
            return {"not": self.parse_condition()}
        if next_token == "(":
            self.pos += 1
            return {"not": self.parse_expression()}

        raise SyntaxError("~ must precede Q(...) or ( ... )")

    def _handle_group(self) -> FilterNode:
        self.pos += 1
        return self.parse_expression()

    def _handle_operator(self, token: str) -> Dict[str, str]:
        self.pos += 1
        return {"op": token}

    def _parse_atom(self, cond: str) -> Dict[str, str]:
        if "=" not in cond:
            raise SyntaxError(f"Missing '=' in {cond!r}")

        key, val = cond.split("=", 1)

        return {key.strip(): val.strip()}

    def parse_condition(self) -> Dict[str, Any]:
        token = self.tokens[self.pos]
        self.pos += 1
        inner = token[2:-1]

        disjunctions = self._split(inner, "|")
        if len(disjunctions) > 1:
            return {"or": [self._parse_conjunction(part) for part in disjunctions]}

        return self._parse_conjunction(inner)

    def _parse_conjunction(self, expr: str) -> Dict[str, Any]:
        conjunctions = self._split(expr, "&")

        if len(conjunctions) > 1:
            return {"and": [self._parse_atom(part) for part in conjunctions]}

        return self._parse_atom(expr)

    def _split(self, text: str, delimiter: str) -> List[str]:
        return [segment.strip() for segment in text.split(delimiter) if segment.strip()]


class StructuredQueryParser:
    """
    Parse the frontend JSON query builder payload into the internal FilterNode tree.
    """

    _GROUP_KEYS = {
        "id",
        "logicalOperator",
        "operators",
        "conditions",
        "groups",
        "negated",
    }
    _CONDITION_KEYS = {
        "id",
        "field",
        "operator",
        "value",
        "negated",
        "transforms",
        "isVariableOnly",
        "fieldRef",
        "query",
    }
    _TRANSFORM_KEYS = {"id", "value"}
    _FIELD_REF_KEYS = {"type", "transformId"}
    _SUBQUERY_OPERATORS = {"exists", "not_exists"}

    _TEXTUAL_FIELD_TYPES = {
        "CharField",
        "TextField",
        "EmailField",
        "SlugField",
        "URLField",
    }

    def __init__(
        self,
        query: Union[str, Dict[str, Any]],
        field_types: Optional[Dict[str, str]] = None,
        allowed_django_operators: Optional[set[str]] = None,
    ) -> None:
        self.query = query
        self.field_types = field_types or {}
        self.allowed_django_operators = (
            set(allowed_django_operators)
            if allowed_django_operators is not None
            else set(ALLOWED_DJANGO_OPERATORS)
        )

    def parse(self) -> FilterNode:
        payload = self._decode_payload(self.query)
        if not isinstance(payload, dict):
            raise SyntaxError("Top-level advanced query must be a JSON object.")
        return self._parse_group(payload)

    def _decode_payload(self, payload: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload

        if not isinstance(payload, str):
            raise SyntaxError("Advanced query payload must be a JSON string.")

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SyntaxError("Invalid JSON payload for advanced query.") from exc

        if not isinstance(decoded, dict):
            raise SyntaxError("Advanced query JSON payload must be an object.")

        return decoded

    def _parse_group(self, group: Dict[str, Any]) -> FilterNode:
        self._validate_keys(group, self._GROUP_KEYS, "group")

        logical_operator = group.get("logicalOperator", "AND")
        if logical_operator not in {"AND", "OR"}:
            raise SyntaxError("group.logicalOperator must be 'AND' or 'OR'.")

        negated = bool(group.get("negated", False))
        operators = group.get("operators")
        parsed_operators: Optional[List[str]] = None
        if operators is not None:
            if not isinstance(operators, list):
                raise SyntaxError("group.operators must be a list when provided.")

            parsed_operators = []
            for operator in operators:
                if operator not in {"AND", "OR"}:
                    raise SyntaxError("group.operators values must be 'AND' or 'OR'.")
                parsed_operators.append(operator)

        conditions = group.get("conditions", [])
        if not isinstance(conditions, list):
            raise SyntaxError("group.conditions must be a list.")

        groups = group.get("groups", [])
        if not isinstance(groups, list):
            raise SyntaxError("group.groups must be a list.")

        parsed_items: List[FilterNode] = []

        for condition in conditions:
            parsed_condition = self._parse_condition(condition)
            if parsed_condition is not None:
                parsed_items.append(parsed_condition)

        for child_group in groups:
            if not isinstance(child_group, dict):
                raise SyntaxError("Each nested group must be an object.")
            parsed_items.append(self._parse_group(child_group))

        return self._combine_items(
            parsed_items,
            logical_operator,
            negated,
            parsed_operators,
        )

    def _combine_items(
        self,
        items: List[FilterNode],
        logical_operator: str,
        negated: bool,
        operators: Optional[List[str]] = None,
    ) -> FilterNode:
        if operators is not None and len(operators) != max(len(items) - 1, 0):
            raise SyntaxError(
                "group.operators length must equal number of item boundaries."
            )

        combined: List[FilterNode] = []
        for index, item in enumerate(items):
            if index > 0:
                if operators is None:
                    operator = logical_operator
                else:
                    operator = operators[index - 1]
                symbol = "&" if operator == "AND" else "|"
                combined.append({"op": symbol})
            combined.append(item)

        if negated:
            return {"not": combined}

        return combined

    def _parse_condition(self, condition: object) -> Union[FilterNode, None]:
        if not isinstance(condition, dict):
            raise SyntaxError("Each condition must be an object.")

        self._validate_keys(condition, self._CONDITION_KEYS, "condition")
        self._validate_optional_frontend_metadata(condition)

        if condition.get("query") is not None:
            return self._parse_subquery_condition(condition)

        if bool(condition.get("isVariableOnly", False)):
            return None

        field = condition.get("field")
        if not isinstance(field, str) or not field.strip():
            raise SyntaxError(
                "condition.field is required and must be a non-empty string."
            )

        operator = condition.get("operator", "equals")
        if not isinstance(operator, str):
            raise SyntaxError("condition.operator must be a string.")

        field_path = self._to_django_path(field)
        lookup, is_negated_operator = self._resolve_operator(operator, field_path)
        value = self._normalize_value(lookup, condition.get("value", ""))
        key = field_path if lookup == "exact" else f"{field_path}__{lookup}"
        node: FilterNode = {key: value}

        should_negate = bool(condition.get("negated", False)) ^ is_negated_operator
        if should_negate:
            return {"not": node}

        return node

    def _parse_subquery_condition(self, condition: Dict[str, Any]) -> FilterNode:
        field = condition.get("field")
        if not isinstance(field, str) or not field.strip():
            raise SyntaxError("Subquery condition requires a non-empty 'field'.")

        query_group = condition.get("query")
        if not isinstance(query_group, dict):
            raise SyntaxError("Subquery condition requires a nested 'query' object.")

        operator = condition.get("operator", "exists")
        if not isinstance(operator, str) or operator not in self._SUBQUERY_OPERATORS:
            raise SyntaxError("Subquery operator must be 'exists' or 'not_exists'.")

        relation_path = self._to_django_path(field)
        parsed_query = self._parse_group(query_group)

        node: FilterNode = {
            "subquery": {
                "relation": relation_path,
                "query": parsed_query,
            }
        }

        should_negate = bool(condition.get("negated", False)) ^ (
            operator == "not_exists"
        )
        if should_negate:
            return {"not": node}

        return node

    def _resolve_operator(self, operator: str, field_path: str) -> tuple[str, bool]:
        normalized_operator = operator.strip()
        if normalized_operator.startswith("__"):
            normalized_operator = normalized_operator[2:]

        field_type = self.field_types.get(field_path)
        if normalized_operator in {"date", "not_date"} and field_type == "DateField":
            if "exact" in self.allowed_django_operators:
                return "exact", normalized_operator == "not_date"
            raise SyntaxError(f"Unsupported operator '{normalized_operator}'.")

        if normalized_operator.startswith("not_"):
            negated_target = normalized_operator[4:]
            negated_lookup = OPERATOR_ALIASES.get(negated_target, negated_target)
            if negated_lookup in self.allowed_django_operators:
                return negated_lookup, True

        if normalized_operator in OPERATOR_ALIASES:
            lookup = OPERATOR_ALIASES[normalized_operator]
            if lookup in self.allowed_django_operators:
                return lookup, normalized_operator in NEGATED_OPERATOR_ALIASES
            raise SyntaxError(f"Unsupported operator '{normalized_operator}'.")

        if normalized_operator in {"equals", "not_equals"} and self._is_textual_field(
            field_path
        ):
            preferred_lookup = (
                "iexact" if "iexact" in self.allowed_django_operators else "exact"
            )
            if preferred_lookup in self.allowed_django_operators:
                return (
                    preferred_lookup,
                    normalized_operator in NEGATED_FRONTEND_OPERATORS,
                )
            raise SyntaxError(f"Unsupported operator '{normalized_operator}'.")

        if normalized_operator in FRONTEND_OPERATOR_LOOKUPS:
            lookup = FRONTEND_OPERATOR_LOOKUPS[normalized_operator]
            if lookup in self.allowed_django_operators:
                return lookup, normalized_operator in NEGATED_FRONTEND_OPERATORS
            raise SyntaxError(f"Unsupported operator '{normalized_operator}'.")

        if (
            normalized_operator.startswith("not_")
            and normalized_operator[4:] in self.allowed_django_operators
        ):
            return normalized_operator[4:], True

        if normalized_operator in self.allowed_django_operators:
            return normalized_operator, False

        raise SyntaxError(f"Unsupported operator '{normalized_operator}'.")

    def _is_textual_field(self, field_path: str) -> bool:
        field_type = self.field_types.get(field_path)
        return field_type in self._TEXTUAL_FIELD_TYPES

    def _normalize_value(self, lookup: str, value: object) -> NormalizedValue:
        if lookup in {"in", "range"}:
            normalized_values = self._normalize_list_value(value)
            if lookup == "range" and len(normalized_values) != 2:
                raise SyntaxError("range operator requires exactly two values.")
            return normalized_values

        if lookup == "isnull":
            return self._normalize_bool(value)

        if isinstance(value, (dict, list)):
            raise SyntaxError("Condition value must be scalar for this operator.")

        if isinstance(value, str):
            return value.strip()

        return value

    def _normalize_list_value(self, value: object) -> List[ScalarValue]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]

        if isinstance(value, list):
            normalized: List[ScalarValue] = []
            for item in value:
                if isinstance(item, (dict, list)):
                    raise SyntaxError(
                        "in/range operators accept only scalar list values."
                    )
                if isinstance(item, str):
                    normalized.append(item.strip())
                elif isinstance(item, (int, float, bool)) or item is None:
                    normalized.append(item)
                else:
                    normalized.append(str(item))
            return normalized

        raise SyntaxError(
            "in/range operators require a list or comma-separated string value."
        )

    def _normalize_bool(self, value: object) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1"}:
                return True
            if lowered in {"false", "0"}:
                return False

        raise SyntaxError("isnull operator requires a boolean value.")

    def _validate_optional_frontend_metadata(self, condition: Dict[str, Any]) -> None:
        transforms = condition.get("transforms")
        if transforms is not None:
            if not isinstance(transforms, list):
                raise SyntaxError("condition.transforms must be a list when provided.")
            for transform in transforms:
                if not isinstance(transform, dict):
                    raise SyntaxError("Each transform must be an object.")
                self._validate_keys(transform, self._TRANSFORM_KEYS, "transform")
                transform_value = transform.get("value")
                if (
                    transform_value is not None
                    and transform_value not in _SUPPORTED_TRANSFORMS
                ):
                    raise SyntaxError(f"Unsupported transform '{transform_value}'.")

        field_ref = condition.get("fieldRef")
        if field_ref is not None:
            if not isinstance(field_ref, dict):
                raise SyntaxError("condition.fieldRef must be an object when provided.")
            self._validate_keys(field_ref, self._FIELD_REF_KEYS, "fieldRef")
            field_ref_type = field_ref.get("type")
            if field_ref_type is not None and field_ref_type != "alias":
                raise SyntaxError(
                    "condition.fieldRef.type must be 'alias' when provided."
                )

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

    def _validate_keys(
        self, payload: Dict[str, Any], allowed_keys: set[str], context: str
    ) -> None:
        unknown = set(payload.keys()) - allowed_keys
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            raise SyntaxError(f"Unknown keys in {context}: {unknown_list}")
