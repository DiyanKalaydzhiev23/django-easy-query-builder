from operator import and_, or_
from typing import Callable, Iterable, List

from django.db.models import Q

from django_easy_query_builder.parsers import FilterNode


class QueryBuilder:
    _LOGIC_SYMBOLS = {"and": "&", "or": "|"}
    _OPERATORS: dict[str, Callable[[Q, Q], Q]] = {"&": and_, "|": or_}

    def build_q(self, filter_tree: FilterNode) -> Q:
        if isinstance(filter_tree, dict):
            return self._build_from_mapping(filter_tree)
        if isinstance(filter_tree, list):
            return self._build_from_sequence(filter_tree)
        raise ValueError(f"Unsupported filter structure: {filter_tree}")

    def combine_q_list(self, filters: List[FilterNode], op: str) -> Q:
        return self._combine_nodes(filters, op)

    def _build_from_mapping(self, node: dict) -> Q:
        if "not" in node:
            return ~self.build_q(node["not"])

        for key, symbol in self._LOGIC_SYMBOLS.items():
            if key in node:
                return self._combine_nodes(node[key], symbol)

        field, value = next(iter(node.items()))
        return Q(**{field: value})

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

    def _operator_for_symbol(self, symbol: str) -> Callable[[Q, Q], Q]:
        try:
            return self._OPERATORS[symbol]
        except KeyError as exc:
            raise ValueError(f"Unsupported operator '{symbol}'") from exc
