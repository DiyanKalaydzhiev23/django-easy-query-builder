class QTreeValidator:
    ALLOWED_LOOKUPS = {
        "exact", "iexact", "in", "gt", "gte", "lt", "lte",
        "contains", "icontains", "startswith", "istartswith",
        "endswith", "iendswith", "range", "isnull", "date",
        "year", "month", "day", "week_day",
    }

    """
    Validate a parsed Q tree produced by SimpleQueryParser.
    """
    def __init__(self, allowed_fields):
        self.allowed_fields = set(allowed_fields)

    def validate(self, node):
        self._walk(node)

    def _walk(self, node):
        if isinstance(node, list):
            for part in node:
                # skip {'op': '&'} / {'op': '|'}
                if isinstance(part, dict) and "op" in part:
                    continue
                self._walk(part)
            return

        if isinstance(node, dict):
            if "not" in node:
                self._walk(node["not"]);  return
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
            base, lookup = self._split_field(field)
            self._check_field(base)
            self._check_lookup(lookup)
            return

        # anything else is unexpected
        raise ValueError(f"Unexpected tree node: {node!r}")

    def _split_field(self, field: str):
        """
        Split "author__email__icontains"  →
        base='author', lookup='icontains'

        If there is no __lookup part, default lookup is 'exact'.
        """
        parts = field.split("__")
        if len(parts) == 1:
            return parts[0], "exact"
        return parts[0], parts[-1]

    def _check_field(self, base: str):
        if base not in self.allowed_fields:
            raise ValueError(f"Field '{base}' is not allowed.")

    def _check_lookup(self, lookup: str):
        if lookup not in self.ALLOWED_LOOKUPS:
            raise ValueError(f"Lookup '{lookup}' is not permitted.")