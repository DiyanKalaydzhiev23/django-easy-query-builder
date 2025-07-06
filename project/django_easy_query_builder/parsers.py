import re

class SimpleQueryParser:
    def __init__(self, query):
        self.query = query
        self.tokens = []
        self.pos = 0

    def tokenize(self):
        pattern = r'Q\([^\)]*\)|[&|()~]'
        self.tokens = re.findall(pattern, self.query)
        return self.tokens

    def parse(self):
        self.tokenize()
        return self.parse_expression()

    def parse_expression(self):
        nodes = []
        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]

            if token == '~':
                self.pos += 1
                # next piece can be a Q(...) OR a parenthesised group
                if self.tokens[self.pos].startswith('Q('):
                    nodes.append({'not': self.parse_condition()})
                elif self.tokens[self.pos] == '(':
                    self.pos += 1                     # skip '('
                    nodes.append({'not': self.parse_expression()})
                else:
                    raise SyntaxError("~ must precede Q(...) or ( ... )")
                continue

            if token.startswith('Q('):
                nodes.append(self.parse_condition())
            elif token == '(':
                self.pos += 1
                nodes.append(self.parse_expression())
            elif token == ')':
                self.pos += 1
                break
            elif token in ['&', '|']:
                nodes.append({'op': token})
                self.pos += 1
            else:
                raise SyntaxError(f"Unknown token {token}")
        return nodes

    # ------------ helpers ------------
    def _parse_atom(self, cond):
        if '=' not in cond:
            raise SyntaxError(f"Missing '=' in {cond!r}")
        key, val = cond.split('=', 1)
        return {key.strip(): val.strip()}

    def parse_condition(self):
        token = self.tokens[self.pos]          # Q(a=5&b=6|c=7)
        self.pos += 1
        inner = token[2:-1]                    # strip Q( ... )

        def split_by(op, s):
            return [p.strip() for p in s.split(op) if p.strip()]

        if '|' in inner:
            parts = split_by('|', inner)
            return {
                'or': [self._parse_atom(p) if '&' not in p
                       else {'and': [self._parse_atom(x) for x in split_by('&', p)]}
                       for p in parts]
            }
        if '&' in inner:
            return {'and': [self._parse_atom(p) for p in split_by('&', inner)]}
        return self._parse_atom(inner)


from django.db.models import Q

def build_q(filter_tree):
    if isinstance(filter_tree, dict):
        if 'not' in filter_tree:
            return ~build_q(filter_tree['not'])
        elif 'and' in filter_tree:
            return combine_q_list(filter_tree['and'], '&')
        elif 'or' in filter_tree:
            return combine_q_list(filter_tree['or'], '|')
        else:
            # it's a simple condition
            # example: {'a': '5'}
            key, value = next(iter(filter_tree.items()))
            return Q(**{key: value})
    elif isinstance(filter_tree, list):
        q = None
        current_op = '&'  # default

        for item in filter_tree:
            if isinstance(item, dict) and 'op' in item:
                current_op = item['op']
            else:
                new_q = build_q(item)
                if q is None:
                    q = new_q
                else:
                    if current_op == '&':
                        q &= new_q
                    elif current_op == '|':
                        q |= new_q
        return q
    else:
        raise ValueError(f"Unsupported filter structure: {filter_tree}")

def combine_q_list(filters, op):
    q = None
    for f in filters:
        part_q = build_q(f)
        if q is None:
            q = part_q
        else:
            if op == '&':
                q &= part_q
            elif op == '|':
                q |= part_q
    return q
