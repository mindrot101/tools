"""A small, safe display-filter language compiled to parametrized SQL.

Grammar (case-insensitive keywords):
  expr   := term (('and'|'or') term)*
  term   := 'not'? atom
  atom   := '(' expr ')' | field op value
  field  := src|dst|proto|sport|dport|len|protocol|dup
  op     := == | = | != | > | < | >= | <= | ~   (~ = contains)
Examples:
  proto == TCP and dport == 443
  src ~ 10.0 and (protocol == dns or protocol == tls)
  len > 1000 and not dup == 1
"""
import re
from typing import List, Tuple

_FIELDS = {"src": "src", "dst": "dst", "proto": "proto", "sport": "sport",
           "dport": "dport", "len": "length", "dup": "is_dup"}
_TOKEN = re.compile(r"\s*(\(|\)|>=|<=|==|!=|=|>|<|~|\band\b|\bor\b|\bnot\b|'[^']*'|\"[^\"]*\"|[^\s()]+)",
                    re.IGNORECASE)


def _tokenize(expr: str) -> List[str]:
    toks, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            break
        toks.append(m.group(1))
        pos = m.end()
    return toks


class _Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self) -> Tuple[str, list]:
        sql, params = self._expr()
        if self.i != len(self.t):
            raise ValueError(f"unexpected token: {self.peek()}")
        return sql, params

    def _expr(self):
        sql, params = self._term()
        while (self.peek() or "").lower() in ("and", "or"):
            op = self.next().upper()
            r_sql, r_params = self._term()
            sql = f"({sql} {op} {r_sql})"
            params += r_params
        return sql, params

    def _term(self):
        if (self.peek() or "").lower() == "not":
            self.next()
            sql, params = self._atom()
            return f"(NOT {sql})", params
        return self._atom()

    def _atom(self):
        if self.peek() == "(":
            self.next()
            sql, params = self._expr()
            if self.next() != ")":
                raise ValueError("missing )")
            return sql, params
        return self._comparison()

    def _comparison(self):
        field = (self.next() or "").lower()
        op = self.next()
        value = self.next()
        if value is None or op is None:
            raise ValueError("incomplete comparison")
        value = value.strip("'\"")
        if field == "protocol":
            if op not in ("==", "=", "!="):
                raise ValueError("protocol supports == or !=")
            neg = "NOT " if op == "!=" else ""
            return f"({neg}protocols LIKE ?)", [f'%"{value.lower()}"%']
        if field not in _FIELDS:
            raise ValueError(f"unknown field: {field}")
        col = _FIELDS[field]
        if op == "~":
            return f"{col} LIKE ?", [f"%{value}%"]
        sql_op = {"==": "=", "=": "=", "!=": "!=", ">": ">", "<": "<", ">=": ">=", "<=": "<="}.get(op)
        if not sql_op:
            raise ValueError(f"bad operator: {op}")
        param = int(value) if col in ("sport", "dport", "length", "is_dup") and value.lstrip("-").isdigit() else value
        return f"{col} {sql_op} ?", [param]


def compile_filter(expr: str) -> Tuple[str, list]:
    expr = (expr or "").strip()
    if not expr:
        return "", []
    toks = _tokenize(expr)
    if not toks:
        return "", []
    return _Parser(toks).parse()
