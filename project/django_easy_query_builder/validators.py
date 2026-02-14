from typing import Dict, List, Set, Tuple

from django_easy_query_builder.parsers import ALLOWED_DJANGO_OPERATORS, FilterNode


class QTreeValidator:
    ALLOWED_LOOKUPS: Set[str] = set(ALLOWED_DJANGO_OPERATORS)
    _ALLOWED_SEQUENCE_OPERATORS = {"&", "|"}

    def __init__(
        self,
        allowed_fields: List[str],
        allowed_lookups: Set[str] | None = None,
    ) -> None:
        self.allowed_fields = {
            field.strip() for field in allowed_fields if field.strip()
        }
        self.allowed_lookups = (
            set(allowed_lookups)
            if allowed_lookups is not None
            else set(self.ALLOWED_LOOKUPS)
        )
        self._dict_handlers = {
            "not": self._handle_not,
            "and": lambda children: self._handle_collection(children),
            "or": lambda children: self._handle_collection(children),
            "subquery": self._handle_subquery,
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
        if not nodes:
            return

        expecting_operand = True

        for part in nodes:
            if isinstance(part, dict) and "op" in part:
                if set(part.keys()) != {"op"}:
                    raise ValueError("Operator node must only contain the 'op' key.")

                operator = part["op"]
                if operator not in self._ALLOWED_SEQUENCE_OPERATORS:
                    raise ValueError(f"Unsupported logical operator '{operator}'.")

                if expecting_operand:
                    raise ValueError("Logical operator cannot appear here.")

                expecting_operand = True
                continue

            if not expecting_operand:
                raise ValueError("Missing logical operator between expressions.")

            self._walk(part)
            expecting_operand = False

        if expecting_operand:
            raise ValueError("Expression cannot end with a logical operator.")

    def _split_field(self, field: str) -> Tuple[List[str], str]:
        parts = field.split("__")
        if not parts:
            raise ValueError("Field name cannot be empty.")

        lookup = "exact"
        if len(parts) > 1 and parts[-1] in self.allowed_lookups:
            lookup = parts.pop()

        if not parts:
            raise ValueError("Field path cannot consist solely of a lookup.")

        return parts, lookup

    def _check_field(self, path: List[str]) -> None:
        joined = "__".join(path)
        if joined not in self.allowed_fields:
            raise ValueError(f"Field path '{joined}' is not allowed.")

    def _check_lookup(self, lookup: str) -> None:
        if lookup not in self.allowed_lookups:
            raise ValueError(f"Lookup '{lookup}' is not permitted.")

    def _handle_not(self, child: FilterNode) -> None:
        self._walk(child)

    def _handle_collection(self, nodes: object) -> None:
        if not isinstance(nodes, list):
            raise ValueError("Logical collection node must contain a list.")

        for child in nodes:
            self._walk(child)

    def _handle_subquery(self, subquery: object) -> None:
        if not isinstance(subquery, dict):
            raise ValueError("Subquery node must be an object.")

        if set(subquery.keys()) != {"relation", "query"}:
            raise ValueError("Subquery node must contain only 'relation' and 'query'.")

        relation = subquery["relation"]
        if not isinstance(relation, str) or not relation.strip():
            raise ValueError("Subquery relation must be a non-empty string.")

        relation_path = relation.strip()
        if not self._is_allowed_relation_prefix(relation_path):
            raise ValueError(f"Subquery relation '{relation_path}' is not allowed.")

        prefixed_query = self._prefix_tree_fields(subquery["query"], relation_path)
        self._walk(prefixed_query)

    def _is_allowed_relation_prefix(self, relation_path: str) -> bool:
        prefix = f"{relation_path}__"
        for allowed_field in self.allowed_fields:
            if allowed_field == relation_path or allowed_field.startswith(prefix):
                return True
        return False

    def _prefix_tree_fields(self, node: FilterNode, relation: str) -> FilterNode:
        if isinstance(node, list):
            return [self._prefix_tree_fields(part, relation) for part in node]

        if not isinstance(node, dict):
            raise ValueError(f"Unsupported subquery child node: {node!r}")

        key, value = self._unpack_dict(node)
        if key == "op":
            return {"op": value}
        if key in {"not", "and", "or"}:
            if isinstance(value, list):
                return {
                    key: [self._prefix_tree_fields(part, relation) for part in value]
                }
            return {key: self._prefix_tree_fields(value, relation)}
        if key == "subquery":
            return {"subquery": value}

        return {f"{relation}__{key}": value}

    def _validate_atom(self, field: str) -> None:
        path, lookup = self._split_field(field)
        self._check_field(path)
        self._check_lookup(lookup)

    def _unpack_dict(self, node: Dict[str, FilterNode]) -> Tuple[str, FilterNode]:
        if not node:
            raise ValueError("Empty dictionary node is not allowed.")

        if len(node) != 1:
            raise ValueError("Each tree node dictionary must contain exactly one key.")

        key, value = next(iter(node.items()))
        return key, value
