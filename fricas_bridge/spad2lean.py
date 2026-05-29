#!/usr/bin/env python3
"""FriCAS SPAD category → Lean 4 typeclass transpiler."""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Operation:
    name: str
    domain: list  # argument types (% = carrier)
    codomain: str # return type

@dataclass
class Axiom:
    raw: str          # raw equation string from source
    lean: Optional[str] = None  # compiled Lean proposition

@dataclass
class Category:
    abbrev: str
    long_name: str
    params: list      # [(name, kind), ...]
    parents: list     # parent category expressions
    ops: list
    axioms: list

# ---------------------------------------------------------------------------
# SPAD operator → Lean field name
# ---------------------------------------------------------------------------

OP_MAP = {
    "+":   "add",
    "*":   "mul",
    "/":   "div",
    "^":   "pow",
    "=":   "eq",
    "~=":  "ne",
    "<":   "lt",
    ">":   "gt",
    "<=":  "le",
    ">=":  "ge",
    "quo": "quot",
    "rem": "rem_op",
    "0":   "zero",
    "1":   "one",
}

def op_to_field(op: str, arity: int) -> str:
    if op == "-" and arity == 1:
        return "neg"
    if op == "-":
        return "sub"
    return OP_MAP.get(op, re.sub(r'[^a-zA-Z0-9_]', '_', op.strip('"')))


# ---------------------------------------------------------------------------
# Type translation: SPAD → Lean
# ---------------------------------------------------------------------------

def translate_type(t: str, carrier: str = "α") -> str:
    t = t.strip()
    # % is not a word char so \b doesn't work — use literal replacement
    t = t.replace('%', carrier)
    # Union(α,"failed") → Option α  (must run after % replacement)
    t = re.sub(
        r'Union\s*\(\s*' + re.escape(carrier) + r'\s*,\s*"failed"\s*\)',
        f'Option {carrier}', t
    )
    t = re.sub(r'Union\s*\([^)]+,\s*"failed"\s*\)', 'Option _', t)
    # Record(...)  → simplify to a named struct placeholder
    t = re.sub(r'Record\([^)]*\)', 'Record_', t)
    t = t.replace("List(" + carrier + ")", f"List {carrier}")
    t = t.replace("List %", f"List {carrier}")
    t = t.replace("Boolean", "Bool")
    t = t.replace("NonNegativeInteger", "Nat")
    t = t.replace("PositiveInteger", "PosNat")
    t = t.replace("SingleInteger", "Int")
    t = t.replace("Integer", "Int")
    return t


# ---------------------------------------------------------------------------
# Parse parent list from RHS of a category definition
# ---------------------------------------------------------------------------

def _depth_split_commas(s: str) -> list:
    """Split s on commas at parenthesis depth 0."""
    parts = []
    current = []
    depth = 0
    for c in s:
        if c == '(':
            depth += 1
            current.append(c)
        elif c == ')':
            depth -= 1
            current.append(c)
        elif c == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(c)
    if current:
        parts.append(''.join(current).strip())
    return parts

def _find_bare_with(s: str) -> int:
    """Index of a bare 'with' keyword at paren depth 0, or -1."""
    depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif depth == 0:
            m = re.match(r'\bwith\b', s[i:])
            if m and (i == 0 or not s[i-1].isalnum()):
                return i
        i += 1
    return -1

def parse_parents(rhs: str) -> list:
    rhs = rhs.strip()
    # Strip 'with ...' block
    wp = _find_bare_with(rhs)
    if wp >= 0:
        rhs = rhs[:wp].strip()
    # Strip trailing 'add'
    rhs = re.sub(r'\s+add\s*$', '', rhs).strip()

    if rhs.startswith("Join("):
        # Extract inner args
        depth = 0
        start = rhs.index('(') + 1
        end = start
        while end < len(rhs):
            if rhs[end] == '(':
                depth += 1
            elif rhs[end] == ')':
                if depth == 0:
                    break
                depth -= 1
            end += 1
        inner = rhs[start:end]
        parents = []
        for arg in _depth_split_commas(inner):
            arg = arg.strip()
            if arg and arg[0].isupper():
                parents.append(arg)
        return parents
    elif rhs and rhs[0].isupper():
        return [rhs]
    return []


# ---------------------------------------------------------------------------
# Parse operations from a 'with' block
# ---------------------------------------------------------------------------

def parse_operations(with_block: str) -> list:
    ops = []
    # Match:  "op" : (A,B) -> C   or   op : A -> C
    pattern = re.compile(
        r'"([^"]+)"\s*:\s*(.*?)\s*->\s*([^\n]+)'
        r'|'
        r'\b([a-zA-Z_?!][a-zA-Z0-9_?!]*)\s*:\s*((?:\([^)]*\)|[^-\n])+?)\s*->\s*([^\n]+)',
        re.MULTILINE
    )
    seen = set()
    for m in pattern.finditer(with_block):
        if m.group(1) is not None:
            raw_name = m.group(1)
            raw_domain = m.group(2).strip()
            raw_cod = m.group(3).strip()
        else:
            raw_name = m.group(4)
            raw_domain = m.group(5).strip()
            raw_cod = m.group(6).strip()

        # Skip doc comment fragments
        if not raw_name or raw_name.startswith('++'):
            continue
        # Deduplicate (FriCAS may list overloaded ops; we keep first)
        key = (raw_name, raw_domain)
        if key in seen:
            continue
        seen.add(key)

        if raw_domain.startswith('(') and raw_domain.endswith(')'):
            dom = [t.strip() for t in _depth_split_commas(raw_domain[1:-1])]
            if dom == ['']:
                dom = []
        elif raw_domain in ('()', ''):
            dom = []
        else:
            dom = [raw_domain]

        ops.append(Operation(name=raw_name, domain=dom, codomain=raw_cod.strip()))
    return ops


# ---------------------------------------------------------------------------
# Parse axiom equations from ++ Axioms: comment block
# ---------------------------------------------------------------------------

def parse_axioms(doc_block: str) -> list:
    raw_eqs = []
    in_axioms = False
    for line in doc_block.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('++'):
            if in_axioms:
                # If blank line, keep going; otherwise stop
                if stripped == '':
                    continue
                in_axioms = False
            continue
        content = stripped[2:].strip()
        if re.match(r'Axioms?\s*:', content, re.IGNORECASE):
            in_axioms = True
            continue
        if in_axioms:
            spads = re.findall(r'\\spad\{([^}]+)\}', content)
            for s in spads:
                formal = re.split(r'\\tab\{', s)[0].strip()
                if formal:
                    raw_eqs.append(formal)
    return raw_eqs


# ---------------------------------------------------------------------------
# Axiom equation compiler: SPAD equation → Lean proposition
# ---------------------------------------------------------------------------

class AxiomCompiler:
    def __init__(self, category: Category, all_cats: dict):
        self.cat = category
        self.all_cats = all_cats

    def compile(self, eq: str) -> Optional[str]:
        eq = eq.strip()
        # Reject disjunctions (a=0 or b=0)
        if ' or ' in eq.lower():
            return None
        # Reject partial-subtraction sentinels
        if '"failed"' in eq or 'subtractIfCan' in eq:
            return None
        # Reject implications
        if '=>' in eq:
            return None
        # Must contain =
        if '=' not in eq:
            return None

        parts = eq.split('=', 1)
        if len(parts) != 2:
            return None
        lhs_raw, rhs_raw = parts

        try:
            lhs_expr, lhs_vars = self._parse_expr(lhs_raw.strip())
            rhs_expr, rhs_vars = self._parse_expr(rhs_raw.strip())
        except Exception:
            return None

        all_vars = sorted(lhs_vars | rhs_vars)
        if not all_vars:
            return None

        quant = "∀ " + " ".join(all_vars) + " : α, "
        return f"{quant}{lhs_expr} = {rhs_expr}"

    def _parse_expr(self, s: str) -> tuple:
        tokens = self._tokenize(s)
        if not tokens:
            raise ValueError("empty expression")
        expr, vars_, pos = self._parse_add(tokens, 0)
        return expr, vars_

    def _tokenize(self, s: str) -> list:
        return re.findall(
            r'\(|\)|\*\*?|[+\-]|/|[a-zA-Z_][a-zA-Z0-9_]*|\d+|,',
            s
        )

    def _parse_add(self, tokens, pos):
        left, vars_, pos = self._parse_mul(tokens, pos)
        while pos < len(tokens) and tokens[pos] in ('+', '-'):
            op = tokens[pos]; pos += 1
            right, rv, pos = self._parse_mul(tokens, pos)
            vars_ |= rv
            left = f"(add {left} {right})" if op == '+' else f"(sub {left} {right})"
        return left, vars_, pos

    def _parse_mul(self, tokens, pos):
        left, vars_, pos = self._parse_unary(tokens, pos)
        while pos < len(tokens) and tokens[pos] in ('*', '/'):
            op = tokens[pos]; pos += 1
            right, rv, pos = self._parse_unary(tokens, pos)
            vars_ |= rv
            lean_op = "mul" if op == '*' else "div"
            left = f"({lean_op} {left} {right})"
        return left, vars_, pos

    def _parse_unary(self, tokens, pos):
        if pos < len(tokens) and tokens[pos] == '-':
            pos += 1
            inner, vars_, pos = self._parse_atom(tokens, pos)
            return f"(neg {inner})", vars_, pos
        return self._parse_atom(tokens, pos)

    def _parse_atom(self, tokens, pos):
        if pos >= len(tokens):
            raise ValueError("unexpected end")
        tok = tokens[pos]

        if tok == '(':
            pos += 1
            inner, vars_, pos = self._parse_add(tokens, pos)
            if pos < len(tokens) and tokens[pos] == ')':
                pos += 1
            return inner, vars_, pos

        if tok.isdigit():
            return tok, set(), pos + 1

        if tok == 'not':
            pos += 1
            inner, vars_, pos = self._parse_atom(tokens, pos)
            return f"(Not {inner})", vars_, pos

        name = tok; pos += 1

        # Function call: name(args)
        if pos < len(tokens) and tokens[pos] == '(':
            pos += 1  # consume '('
            args = []; avars: set = set()
            while pos < len(tokens) and tokens[pos] != ')':
                if tokens[pos] == ',':
                    pos += 1; continue
                arg, av, pos = self._parse_add(tokens, pos)
                args.append(arg); avars |= av
            if pos < len(tokens):
                pos += 1  # consume ')'
            lean_name = self._map_func(name)
            result = f"({lean_name} {' '.join(args)})" if args else lean_name
            return result, avars, pos

        # Single identifier
        if re.match(r'^[a-z]$', name):
            return name, {name}, pos
        if name[0].islower():
            return name, {name}, pos
        return name, set(), pos

    def _map_func(self, name: str) -> str:
        return {
            'inv': 'inv', 'differentiate': 'differentiate',
            'not': 'Not', 'zero': 'zero', 'one': 'one',
            'lookup': 'lookup', 'index': 'index', 'sup': 'sup',
        }.get(name, name)


# ---------------------------------------------------------------------------
# Lean 4 code generator
# ---------------------------------------------------------------------------

class LeanGenerator:
    def __init__(self, categories: list):
        self.categories = categories
        self.cat_by_name = {c.long_name: c for c in categories}

    def _translate_parent(self, p: str) -> Optional[str]:
        p = p.strip()
        if not p or not p[0].isupper():
            return None
        # Parametric parent: Name(arg) or Name(arg1, arg2, ...)
        m = re.match(r'([A-Za-z][A-Za-z0-9]*)\s*\((.+)\)$', p, re.DOTALL)
        if m:
            base = m.group(1)
            raw_args = m.group(2).strip()
            # Split args at depth-0 commas
            args = _depth_split_commas(raw_args)
            lean_args = []
            for arg in args:
                arg = arg.strip()
                if arg == '%' or re.search(r':\s*Rng|:\s*Ring', arg):
                    lean_args.append('α')
                else:
                    lean_args.append(translate_type(arg))
            return f"{base} {' '.join(lean_args)}"
        return p

    def generate_class(self, cat: Category) -> str:
        lines = []
        extends = [self._translate_parent(p) for p in cat.parents]
        extends = [e for e in extends if e]

        if cat.params:
            pstr = " ".join(f"({n} : {k})" for n, k in cat.params)
            header = f"class {cat.long_name} {pstr} (α : Type*)"
        else:
            header = f"class {cat.long_name} (α : Type*)"

        ext = (" extends " + ", ".join(extends)) if extends else ""
        lines.append(f"{header}{ext} where")

        # Operations (deduplicate by lean field name — keep first signature)
        seen_fields: set = set()
        emitted_ops = 0
        for op in cat.ops:
            lean_name = op_to_field(op.name, len(op.domain))
            if lean_name in seen_fields:
                continue
            seen_fields.add(lean_name)
            dom = [translate_type(t) for t in op.domain]
            cod = translate_type(op.codomain)
            sig = " → ".join(dom + [cod]) if dom else cod
            lines.append(f"  {lean_name} : {sig}")
            emitted_ops += 1

        if emitted_ops == 0:
            lines.append("  -- (no new operations)")

        # Axioms
        compiler = AxiomCompiler(cat, self.cat_by_name)
        compiled = []
        informal = []
        for ax in cat.axioms:
            lp = compiler.compile(ax.raw)
            if lp:
                compiled.append((ax.raw, lp))
            else:
                informal.append(ax.raw)

        if compiled or informal:
            lines.append("")
        for i, (raw, lp) in enumerate(compiled):
            lines.append(f"  ax{i} : {lp}")
        for raw in informal:
            lines.append(f"  -- (informal) {raw}")

        return "\n".join(lines)

    def generate_file(self) -> str:
        parts = [
            "-- Auto-generated by spad2lean.py",
            "-- FriCAS category hierarchy → Lean 4 typeclasses",
            "-- Source: fricas/fricas src/algebra/catdef.spad",
            "",
        ]
        for cat in self.categories:
            parts.append(f"-- {'─'*68}")
            parts.append(f"-- {cat.long_name}  [{cat.abbrev}]")
            parts.append(f"-- {'─'*68}")
            parts.append(self.generate_class(cat))
            parts.append("")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# SPAD file parser
# ---------------------------------------------------------------------------

def parse_spad_file(path: Path) -> list:
    text = path.read_text()

    # Strip -- comments (but preserve ++ doc lines)
    cleaned = []
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('++'):
            cleaned.append(line)
            continue
        # Remove -- from non-doc lines
        out = []
        in_str = False
        i = 0
        while i < len(line):
            c = line[i]
            if c == '"':
                in_str = not in_str
                out.append(c)
            elif not in_str and line[i:i+2] == '--':
                break
            else:
                out.append(c)
            i += 1
        cleaned.append(''.join(out))
    text = '\n'.join(cleaned)

    categories = []
    abbrev_re = re.compile(r'\)abbrev\s+category\s+(\w+)\s+(\w+)', re.MULTILINE)
    matches = list(abbrev_re.finditer(text))

    for idx, m in enumerate(matches):
        abbrev = m.group(1)
        long_name = m.group(2)
        start = m.start()
        end = matches[idx+1].start() if idx+1 < len(matches) else len(text)
        block = text[start:end]

        # Split into doc and sig blocks
        doc_lines = []
        sig_lines = []
        past_abbrev = False
        for line in block.split('\n'):
            if not past_abbrev:
                past_abbrev = True
                continue
            s = line.strip()
            if s.startswith('++') or (not sig_lines and s == ''):
                if s.startswith('++'):
                    doc_lines.append(s)
            else:
                sig_lines.append(line)

        doc_block = '\n'.join(doc_lines)
        sig_block = '\n'.join(sig_lines)

        params, parents = _parse_signature(sig_block, long_name)

        ops = []
        wm = re.search(r'\bwith\b(.*?)(?:\badd\b|$)', sig_block, re.DOTALL)
        if wm:
            ops = parse_operations(wm.group(1))

        raw_axioms = parse_axioms(doc_block)
        axioms = [Axiom(raw=eq) for eq in raw_axioms]

        categories.append(Category(
            abbrev=abbrev,
            long_name=long_name,
            params=params,
            parents=parents,
            ops=ops,
            axioms=axioms,
        ))

    return categories


def _parse_signature(sig_block: str, long_name: str) -> tuple:
    pat = re.compile(
        r'\b' + re.escape(long_name) + r'\s*'
        r'(?:\(([^)]*)\))?\s*'
        r':\s*Category\s*==\s*(.*)',
        re.DOTALL
    )
    m = pat.search(sig_block)
    if not m:
        return [], []

    raw_params = m.group(1) or ''
    rhs = m.group(2).strip()

    params = []
    for part in raw_params.split(','):
        part = part.strip()
        pm = re.match(r'(\w+)\s*:\s*(.+)', part)
        if pm:
            params.append((pm.group(1).strip(), pm.group(2).strip()))

    parents = parse_parents(rhs)
    return params, parents


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def report_stats(categories: list) -> str:
    total_ops = sum(len(c.ops) for c in categories)
    total_axioms = sum(len(c.axioms) for c in categories)
    cats_with_axioms = sum(1 for c in categories if c.axioms)
    no_axioms = sorted(c.long_name for c in categories if not c.axioms)
    density = 100 * cats_with_axioms / len(categories) if categories else 0

    lines = [
        f"Categories parsed:          {len(categories)}",
        f"Operations extracted:       {total_ops}",
        f"Axiom equations found:      {total_axioms}",
        f"Categories with axioms:     {cats_with_axioms} / {len(categories)} "
        f"({density:.1f}% formalization density)",
        "",
        f"Implicit-contract gap — {len(no_axioms)} categories declare ops but state no axioms:",
    ]
    for name in no_axioms:
        lines.append(f"  - {name}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Transpile FriCAS SPAD categories to Lean 4")
    ap.add_argument("spad_file", nargs='?',
                    default=str(Path(__file__).parent / "data" / "catdef.spad"))
    ap.add_argument("--output", "-o",
                    default=str(Path(__file__).parent / "output" / "FriCAS_Algebra.lean"))
    args = ap.parse_args()

    spad_path = Path(args.spad_file)
    if not spad_path.exists():
        print(f"Error: {spad_path} not found", file=sys.stderr)
        sys.exit(1)

    categories = parse_spad_file(spad_path)
    print(report_stats(categories))
    print()

    gen = LeanGenerator(categories)
    lean_code = gen.generate_file()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(lean_code)
    print(f"Lean output: {out_path}")


if __name__ == "__main__":
    main()
