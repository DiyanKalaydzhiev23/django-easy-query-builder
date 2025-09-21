import re
from typing import Any, Dict, List, Union

FilterNode = Union[List["FilterNode"], Dict[str, Any]]


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
