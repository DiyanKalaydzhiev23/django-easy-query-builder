from typing import Dict, List, Set, Tuple

from django_easy_query_builder.parsers import FilterNode


class QTreeValidator:
    ALLOWED_LOOKUPS: Set[str] = {
        "exact",
        "iexact",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "contains",
        "icontains",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "range",
        "isnull",
        "date",
        "year",
        "month",
        "day",
        "week_day",
    }

    """
    Validate a parsed Q tree produced by SimpleQueryParser.
    """

    def __init__(self, allowed_fields: List[str]) -> None:
        self.allowed_fields = set(allowed_fields)
        self._dict_handlers = {
            "not": self._handle_not,
            "and": lambda children: self._handle_collection(children),
            "or": lambda children: self._handle_collection(children),
        }

    def validate(self, node: FilterNode) -> None:
        self._walk(node)

    def _walk(self, node: FilterNode) -> None:
        if isinstance(node, list):
            self._walk_list(node)
            return

        if isinstance(node, dict):
            key, value = self._unpack_dict(node)
            handler = self._dict_handlers.get(key)

            if handler:
                handler(value)
                return

            self._validate_atom(key)
            return

        raise ValueError(f"Unexpected tree node: {node!r}")

    def _walk_list(self, nodes: List[FilterNode]) -> None:
        for part in nodes:
            if isinstance(part, dict) and "op" in part:
                continue

            self._walk(part)

    def _split_field(self, field: str) -> Tuple[List[str], str]:
        """
        Split "author__email__icontains"  →
        path=['author', 'email'], lookup='icontains'

        If there is no __lookup part, default lookup is 'exact'.
        """
        parts = field.split("__")
        if not parts:
            raise ValueError("Field name cannot be empty.")

        lookup = "exact"
        if len(parts) > 1 and parts[-1] in self.ALLOWED_LOOKUPS:
            lookup = parts.pop()

        if not parts:
            raise ValueError("Field path cannot consist solely of a lookup.")

        return parts, lookup

    def _check_field(self, path: List[str]) -> None:
        if "__".join(path) in self.allowed_fields:
            return

        for segment in path:
            if segment not in self.allowed_fields:
                path_repr = "__".join(path)
                raise ValueError(
                    f"Field '{segment}' in path '{path_repr}' is not allowed."
                )

    def _check_lookup(self, lookup: str) -> None:
        if lookup not in self.ALLOWED_LOOKUPS:
            raise ValueError(f"Lookup '{lookup}' is not permitted.")

    def _handle_not(self, child: FilterNode) -> None:
        self._walk(child)

    def _handle_collection(self, nodes: List[FilterNode]) -> None:
        for child in nodes:
            self._walk(child)

    def _validate_atom(self, field: str) -> None:
        path, lookup = self._split_field(field)
        self._check_field(path)
        self._check_lookup(lookup)

    def _unpack_dict(self, node: Dict[str, FilterNode]) -> Tuple[str, FilterNode]:
        if not node:
            raise ValueError("Empty dictionary node is not allowed.")

        key, value = next(iter(node.items()))
        return key, value
