"""
FriCAS expression → Lean 4 expression converter.

This is the inverse of `fricas_bridge/lean_statement_parser.py`:
  lean_statement_parser  :  Lean 4 statement text  →  FriCAS string
  fricas_to_lean         :  FriCAS string          →  Lean 4 expression text

Public API
----------
fricas_antideriv_to_lean(fricas, variable="t") → Lean 4 lambda body string
to_lean_lambda(fricas, variable="t")           → full lambda: "fun t : ℝ => <expr>"

The Python implementation is the operational test authority for Step C.
The Lean 4 counterpart (FriCASParser.lean) provides the same contract
via Term.elabTerm; both are validated against the same 9 claim round-trips.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------

@dataclass
class Num:
    value: str


@dataclass
class Var:
    name: str


@dataclass
class Call:
    fn: str
    arg: "Node"


@dataclass
class BinOp:
    op: str
    left: "Node"
    right: "Node"


@dataclass
class UnaryMinus:
    arg: "Node"


Node = Union[Num, Var, Call, BinOp, UnaryMinus]

# ---------------------------------------------------------------------------
# FriCAS → Lean name map
# ---------------------------------------------------------------------------

FN_MAP: dict[str, str] = {
    "log": "Real.log",
    "atan": "Real.arctan",
    "exp": "Real.exp",
    "sin": "Real.sin",
    "cos": "Real.cos",
    "sqrt": "Real.sqrt",
}

PREC: dict[str, int] = {"+": 1, "-": 1, "*": 2, "/": 2, "^": 3}

# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TK_NUM = "NUM"
_TK_ID  = "ID"
_TK_OP  = "OP"
_TK_END = "END"


def _tokenize(s: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            tokens.append((_TK_NUM, s[i:j]))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            tokens.append((_TK_ID, s[i:j]))
            i = j
        elif c in "+-*/^()":
            tokens.append((_TK_OP, c))
            i += 1
        else:
            i += 1  # skip unrecognised (e.g. Unicode)
    tokens.append((_TK_END, ""))
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> tuple[str, str]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return (_TK_END, "")

    def _consume(self) -> tuple[str, str]:
        t = self._peek()
        self._pos += 1
        return t

    def _expect(self, val: str) -> None:
        tk_type, tk_val = self._consume()
        if tk_val != val:
            raise ValueError(f"Expected '{val}', got '{tk_val}'")

    # expr = term { ('+' | '-') term }
    def parse_expr(self) -> Node:
        left = self._parse_term()
        while self._peek()[0] == _TK_OP and self._peek()[1] in ("+", "-"):
            op = self._consume()[1]
            right = self._parse_term()
            left = BinOp(op, left, right)
        return left

    # term = unary { ('*' | '/') unary }
    def _parse_term(self) -> Node:
        left = self._parse_unary()
        while self._peek()[0] == _TK_OP and self._peek()[1] in ("*", "/"):
            op = self._consume()[1]
            right = self._parse_unary()
            left = BinOp(op, left, right)
        return left

    def _parse_unary(self) -> Node:
        if self._peek() == (_TK_OP, "-"):
            self._consume()
            arg = self._parse_power()
            return UnaryMinus(arg)
        return self._parse_power()

    # power = atom [ '^' unary ]  (right-associative)
    def _parse_power(self) -> Node:
        base = self._parse_atom()
        if self._peek() == (_TK_OP, "^"):
            self._consume()
            exp = self._parse_unary()
            return BinOp("^", base, exp)
        return base

    # atom = '(' expr ')' | ID '(' expr ')' | ID | NUM
    def _parse_atom(self) -> Node:
        tk_type, tk_val = self._peek()
        if tk_type == _TK_NUM:
            self._consume()
            return Num(tk_val)
        if tk_type == _TK_ID:
            self._consume()
            if self._peek() == (_TK_OP, "("):
                self._consume()  # (
                arg = self.parse_expr()
                self._expect(")")
                return Call(tk_val, arg)
            return Var(tk_val)
        if tk_type == _TK_OP and tk_val == "(":
            self._consume()  # (
            inner = self.parse_expr()
            self._expect(")")
            return inner
        raise ValueError(f"Unexpected token type={tk_type!r} val={tk_val!r}")


def _parse(s: str) -> Node:
    p = _Parser(_tokenize(s))
    tree = p.parse_expr()
    if p._peek()[0] != _TK_END:
        raise ValueError(f"Trailing tokens at pos {p._pos}: {p._peek()}")
    return tree


# ---------------------------------------------------------------------------
# Lean 4 emitter
# ---------------------------------------------------------------------------

def _need_parens_left(node: Node, outer_prec: int) -> bool:
    return isinstance(node, BinOp) and PREC[node.op] < outer_prec


def _need_parens_right(node: Node, outer_op: str, outer_prec: int) -> bool:
    if not isinstance(node, BinOp):
        return False
    inner_prec = PREC[node.op]
    if outer_op == "^":
        return inner_prec < outer_prec   # right-assoc: only strictly lower
    return inner_prec <= outer_prec      # left-assoc: equal or lower


def _emit(node: Node, var: str) -> str:
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Var):
        return var if node.name == "x" else node.name
    if isinstance(node, Call):
        lean_fn = FN_MAP.get(node.fn, node.fn)
        arg_str = _emit(node.arg, var)
        if isinstance(node.arg, (BinOp, Call)):
            return f"{lean_fn} ({arg_str})"
        return f"{lean_fn} {arg_str}"
    if isinstance(node, BinOp):
        outer_prec = PREC[node.op]
        l = _emit(node.left, var)
        r = _emit(node.right, var)
        if _need_parens_left(node.left, outer_prec):
            l = f"({l})"
        if _need_parens_right(node.right, node.op, outer_prec):
            r = f"({r})"
        return f"{l} {node.op} {r}"
    if isinstance(node, UnaryMinus):
        arg_str = _emit(node.arg, var)
        if isinstance(node.arg, BinOp):
            return f"-({arg_str})"
        return f"-{arg_str}"
    return "??"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fricas_antideriv_to_lean(fricas: str, variable: str = "t") -> str:
    """
    Convert a FriCAS antiderivative string to a Lean 4 lambda-body expression.

    The FriCAS integration variable `x` is mapped to *variable* (default ``"t"``
    to match the lambda binder used in `RischVerification.lean`).

    Example::

        >>> fricas_antideriv_to_lean("log(x^2+1)/2")
        'Real.log (t ^ 2 + 1) / 2'

        >>> fricas_antideriv_to_lean("log(x)")
        'Real.log t'

        >>> fricas_antideriv_to_lean("atan(x+1)")
        'Real.arctan (t + 1)'
    """
    return _emit(_parse(fricas), variable)


def to_lean_lambda(fricas: str, variable: str = "t") -> str:
    """
    Convert a FriCAS antiderivative string to a Lean 4 lambda expression.

    Returns: ``"fun <variable> : ℝ => <body>"``
    """
    body = fricas_antideriv_to_lean(fricas, variable)
    return f"fun {variable} : ℝ => {body}"
