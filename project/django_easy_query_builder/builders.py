from operator import and_, or_
from typing import Any, Callable, Iterable, List, Optional

from django.db import models
from django.db.models import F, OuterRef, Q, Subquery

from django_easy_query_builder.parsers import AliasReference, FilterNode


class QueryBuilder:
    _LOGIC_SYMBOLS = {"and": "&", "or": "|"}
    _OPERATORS: dict[str, Callable[[Q, Q], Q]] = {"&": and_, "|": or_}

    def __init__(self, root_model: Optional[type[models.Model]] = None) -> None:
        self.root_model = root_model

    def build_q(self, filter_tree: FilterNode) -> Q:
        if isinstance(filter_tree, dict):
            return self._build_from_mapping(filter_tree)
        if isinstance(filter_tree, list):
            return self._build_from_sequence(filter_tree)
        raise ValueError(f"Unsupported filter structure: {filter_tree}")

    def combine_q_list(self, filters: List[FilterNode], op: str) -> Q:
        return self._combine_nodes(filters, op)

    def _build_from_mapping(self, node: dict[str, Any]) -> Q:
        if "not" in node:
            return ~self.build_q(node["not"])

        if "subquery" in node:
            return self._build_subquery_q(node["subquery"])

        for key, symbol in self._LOGIC_SYMBOLS.items():
            if key in node:
                return self._combine_nodes(node[key], symbol)

        field, value = next(iter(node.items()))
        return Q(**{field: self._resolve_filter_value(value)})

    def _build_from_sequence(self, nodes: Iterable[FilterNode]) -> Q:
        result: Q | None = None
        current_op = self._operator_for_symbol("&")

        for item in nodes:
            if isinstance(item, dict) and "op" in item:
                current_op = self._operator_for_symbol(item["op"])
                continue

            new_q = self.build_q(item)
            result = new_q if result is None else current_op(result, new_q)

        return result if result is not None else Q()

    def _combine_nodes(self, nodes: Iterable[FilterNode], symbol: str) -> Q:
        operator_fn = self._operator_for_symbol(symbol)
        result: Q | None = None

        for node in nodes:
            new_q = self.build_q(node)
            result = new_q if result is None else operator_fn(result, new_q)

        return result if result is not None else Q()

    def _build_subquery_q(self, payload: dict[str, Any]) -> Q:
        if self.root_model is None:
            raise ValueError("Subquery nodes require QueryBuilder(root_model=...).")

        if set(payload.keys()) != {"relation", "query"}:
            raise ValueError(
                "Subquery payload must contain only 'relation' and 'query'."
            )

        relation = payload["relation"]
        if not isinstance(relation, str) or not relation:
            raise ValueError("Subquery relation must be a non-empty string.")

        subquery_tree = self._prefix_tree_fields(payload["query"], relation)
        subquery_filters = self.build_q(subquery_tree)

        queryset = (
            self.root_model._default_manager.filter(pk=OuterRef("pk"))
            .filter(subquery_filters)
            .values("pk")
        )

        return Q(pk__in=Subquery(queryset))

    def _prefix_tree_fields(self, node: FilterNode, relation: str) -> FilterNode:
        if isinstance(node, list):
            return [self._prefix_tree_fields(item, relation) for item in node]

        if not isinstance(node, dict):
            raise ValueError(f"Unsupported subquery child node: {node!r}")

        key, value = next(iter(node.items()))

        if key in {"op", "not", "and", "or", "subquery"}:
            if key == "op":
                return {"op": value}
            if key == "subquery":
                # Nested subqueries are already absolute to the root model.
                return {"subquery": value}
            if isinstance(value, list):
                return {
                    key: [self._prefix_tree_fields(child, relation) for child in value]
                }
            return {key: self._prefix_tree_fields(value, relation)}

        return {f"{relation}__{key}": value}

    def _resolve_filter_value(self, value: object) -> object:
        if isinstance(value, AliasReference):
            return F(value.alias)
        return value

    def _operator_for_symbol(self, symbol: str) -> Callable[[Q, Q], Q]:
        try:
            return self._OPERATORS[symbol]
        except KeyError as exc:
            raise ValueError(f"Unsupported operator '{symbol}'") from exc
