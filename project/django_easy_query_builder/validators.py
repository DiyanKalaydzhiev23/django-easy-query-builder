from typing import List, Set, Tuple

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

    def validate(self, node: FilterNode) -> None:
        self._walk(node)

    def _walk(self, node: FilterNode) -> None:
        if isinstance(node, list):
            for part in node:
                # skip {'op': '&'} / {'op': '|'}
                if isinstance(part, dict) and "op" in part:
                    continue
                self._walk(part)
            return

        if isinstance(node, dict):
            if "not" in node:
                self._walk(node["not"])
                return
            if "and" in node:
                for child in node["and"]:
                    self._walk(child)

                return
            if "or" in node:
                for child in node["or"]:
                    self._walk(child)

                return

            # atomic   {'field__lookup': 'value'}
            field, _ = next(iter(node.items()))
            path, lookup = self._split_field(field)
            self._check_field(path)
            self._check_lookup(lookup)
            return

        # anything else is unexpected
        raise ValueError(f"Unexpected tree node: {node!r}")

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
