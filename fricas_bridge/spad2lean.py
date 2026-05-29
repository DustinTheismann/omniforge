#!/usr/bin/env python3
"""FriCAS SPAD category → Lean 4 typeclass transpiler.

Processes multiple SPAD files, deduplicates by long_name (first file wins),
emits one Lean 4 file with class declarations, typed fields (% → α,
Union(%,"failed") → Option α, Join(A,B) → extends A α, B α), and compiled
axiom propositions.
"""

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
    domain: list       # argument types (% = carrier); [] for constants/nullary
    codomain: str      # return type
    doc: str = ''      # per-field docstring

@dataclass
class Axiom:
    raw: str           # raw equation string from source
    lean: Optional[str] = None

@dataclass
class Category:
    abbrev: str
    long_name: str
    params: list       # [(name, kind), ...]
    parents: list      # parent category expressions (raw SPAD strings)
    ops: list
    axioms: list
    source_file: str = ''

# ---------------------------------------------------------------------------
# SPAD operator → Lean field name
# ---------------------------------------------------------------------------

OP_MAP = {
    "+":    "add",
    "-":    "sub",     # binary; arity=1 handled below
    "*":    "mul",
    "/":    "div",
    "^":    "pow",
    "=":    "eq",
    "~=":   "ne",
    "<":    "lt",
    ">":    "gt",
    "<=":   "le",
    ">=":   "ge",
    "quo":  "quot",
    "rem":  "rem_op",
    # Constant-valued operations
    "0":    "zero",
    "1":    "one",
    # Logic / lattice specials
    "T":    "top",
    "_/_\\":  "meet",
    "_\\_/":  "join",
    "__|__":  "bot",
    "_~":   "lnot",
    "true":  "true_val",
    "false": "false_val",
}

def op_to_field(op: str, arity: int) -> str:
    """Map a SPAD operator name to a valid Lean field identifier."""
    if op == "-" and arity == 1:
        return "neg"
    mapped = OP_MAP.get(op)
    if mapped:
        return mapped
    # Sanitize: keep alphanumerics and underscores
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', op.strip('"'))
    # Lean doesn't allow leading digits
    if clean and clean[0].isdigit():
        clean = "val_" + clean
    return clean or "unknown"


# ---------------------------------------------------------------------------
# Type translation: SPAD → Lean
# ---------------------------------------------------------------------------

def translate_type(t: str, carrier: str = "α") -> str:
    t = t.strip()
    # % is not a word char — use literal replacement (not regex \b)
    t = t.replace('%', carrier)
    # Union(α,"failed") → Option α
    t = re.sub(
        r'Union\s*\(\s*' + re.escape(carrier) + r'\s*,\s*"failed"\s*\)',
        f'Option {carrier}', t
    )
    t = re.sub(r'Union\s*\([^)]+,\s*"failed"\s*\)', 'Option _', t)
    # Record(...) → opaque placeholder
    t = re.sub(r'Record\s*\([^)]*\)', 'Record_', t)
    # List(%) → List α
    t = re.sub(r'List\s*\(\s*' + re.escape(carrier) + r'\s*\)', f'List {carrier}', t)
    # Common integer/boolean types
    t = t.replace("Boolean", "Bool")
    t = t.replace("NonNegativeInteger", "Nat")
    t = t.replace("PositiveInteger", "PosNat")
    t = t.replace("SingleInteger", "Int")
    t = t.replace("Integer", "Int")
    return t


# ---------------------------------------------------------------------------
# Comma-splitting at paren depth 0
# ---------------------------------------------------------------------------

def _depth_split(s: str) -> list:
    """Split s on commas at parenthesis depth 0."""
    parts, cur, depth = [], [], 0
    for c in s:
        if c == '(':
            depth += 1; cur.append(c)
        elif c == ')':
            depth -= 1; cur.append(c)
        elif c == ',' and depth == 0:
            parts.append(''.join(cur).strip()); cur = []
        else:
            cur.append(c)
    if cur:
        parts.append(''.join(cur).strip())
    return parts


# ---------------------------------------------------------------------------
# Parse parent list from category definition RHS
# ---------------------------------------------------------------------------

def _bare_with_pos(s: str) -> int:
    """Index of a bare 'with' keyword at depth 0, or -1."""
    depth = 0
    for i, c in enumerate(s):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif depth == 0 and s[i:i+5] == ' with':
            after = s[i+5:i+6]
            if not (after.isalnum() or after == '_'):
                return i
    return -1

def parse_parents(rhs: str) -> list:
    rhs = rhs.strip()
    wp = _bare_with_pos(rhs)
    if wp >= 0:
        rhs = rhs[:wp].strip()
    rhs = re.sub(r'\s+add\s*$', '', rhs).strip()

    if rhs.startswith("Join("):
        depth, start = 0, rhs.index('(') + 1
        end = start
        while end < len(rhs):
            if rhs[end] == '(':
                depth += 1
            elif rhs[end] == ')':
                if depth == 0:
                    break
                depth -= 1
            end += 1
        parts = []
        for arg in _depth_split(rhs[start:end]):
            arg = arg.strip()
            if arg and arg[0].isupper():
                parts.append(arg)
        return parts
    elif rhs and rhs[0].isupper():
        return [rhs]
    return []


# ---------------------------------------------------------------------------
# Parse operations from a 'with' block
# (handles constants, digit names, per-field docstrings)
# ---------------------------------------------------------------------------

# Matches: "op" or word or digit-start  :  constant  ->  Type
_CONST_RE = re.compile(
    r'(?:"(?P<qn>[^"\n]+)"|(?P<dn>\d[\w]*)|(?P<wn>[a-zA-Z_?!][a-zA-Z0-9_?!]*))'
    r'\s*:\s*constant\s*->\s*(?P<cod>[^\n]+)',
    re.MULTILINE
)

# Matches:  "op" or word  :  Domain  ->  Codomain
_OP_RE = re.compile(
    r'(?:"(?P<qn>[^"\n]+)"|(?P<wn>[a-zA-Z_?!][a-zA-Z0-9_?!]*))'
    r'\s*:\s*(?P<dom>(?:\([^)]*\)|[^-\n])*?)\s*->\s*(?P<cod>[^\n]+)',
    re.MULTILINE
)

def _strip_inline_doc(s: str) -> tuple:
    """Split 'value  ++ doc comment' into (value, doc)."""
    idx = s.find('++')
    if idx >= 0:
        return s[:idx].strip(), s[idx+2:].strip()
    return s.strip(), ''

def parse_operations(with_block: str) -> list:
    ops = []
    seen_lean: set = set()

    # Pass 1 — constants (nullary, including digit names like 0, 1)
    for m in _CONST_RE.finditer(with_block):
        name = m.group('qn') or m.group('dn') or m.group('wn') or ''
        name = name.strip()
        cod_raw = m.group('cod') or ''
        cod, doc = _strip_inline_doc(cod_raw)
        if not name:
            continue
        lean = op_to_field(name, 0)
        if lean not in seen_lean:
            seen_lean.add(lean)
            ops.append(Operation(name=name, domain=[], codomain=cod, doc=doc))

    # Pass 2 — regular ops (skip 'constant' domain)
    for m in _OP_RE.finditer(with_block):
        name = (m.group('qn') or m.group('wn') or '').strip()
        dom_str = (m.group('dom') or '').strip()
        cod_raw = (m.group('cod') or '').strip()

        if not name or name.startswith('++'):
            continue
        if dom_str == 'constant':
            continue  # handled in pass 1

        cod, doc = _strip_inline_doc(cod_raw)

        # Parse domain
        if dom_str.startswith('(') and dom_str.endswith(')'):
            dom = [t.strip() for t in _depth_split(dom_str[1:-1])]
            dom = [d for d in dom if d]
        elif dom_str in ('()', ''):
            dom = []
        else:
            dom = [dom_str]

        lean = op_to_field(name, len(dom))
        if lean not in seen_lean:
            seen_lean.add(lean)
            ops.append(Operation(name=name, domain=dom, codomain=cod, doc=doc))

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
            if in_axioms and stripped:
                in_axioms = False
            continue
        content = stripped[2:].strip()
        if re.match(r'Axioms?\s*:', content, re.IGNORECASE):
            in_axioms = True
            continue
        if in_axioms:
            spads = re.findall(r'\\spad\{([^}]+)\}', content)
            if spads:
                for s in spads:
                    formal = re.split(r'\\tab\{', s)[0].strip()
                    if formal:
                        raw_eqs.append(formal)
            else:
                # Bare equation (no \spad{} wrapper), e.g. from naalgc.spad
                eq = content.strip()
                # Strip leftIdentity(...) wrapper — just take the human-readable part
                bare = re.search(r'\)\s+(.+)$', eq)
                if bare:
                    eq = bare.group(1).strip()
                if eq and '=' in eq and not eq.startswith('++'):
                    raw_eqs.append(eq)
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
        if ' or ' in eq.lower():
            return None
        if '"failed"' in eq or 'subtractIfCan' in eq:
            return None
        if '=>' in eq:
            return None
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
        expr, vars_, _ = self._parse_add(tokens, 0)
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
            lean_op = "add" if op == '+' else "sub"
            left = f"({lean_op} {left} {right})"
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

        if pos < len(tokens) and tokens[pos] == '(':
            pos += 1
            args, avars = [], set()
            while pos < len(tokens) and tokens[pos] != ')':
                if tokens[pos] == ',':
                    pos += 1; continue
                a, av, pos = self._parse_add(tokens, pos)
                args.append(a); avars |= av
            if pos < len(tokens):
                pos += 1
            lean_name = {'inv': 'inv', 'differentiate': 'differentiate',
                         'not': 'Not', 'lookup': 'lookup', 'index': 'index'
                         }.get(name, name)
            result = f"({lean_name} {' '.join(args)})" if args else lean_name
            return result, avars, pos

        # Only single-letter lowercase names are universally-quantified variables.
        # Multi-char lowercase names (top, bot, zero, one, inv, …) are field
        # references to in-scope class constants — not free variables.
        if re.match(r'^[a-z]$', name):
            return name, {name}, pos
        return name, set(), pos


# ---------------------------------------------------------------------------
# Lean 4 code generator
# ---------------------------------------------------------------------------

class LeanGenerator:
    def __init__(self, categories: list):
        self.categories = categories
        self.cat_by_name = {c.long_name: c for c in categories}

    def _translate_parent(self, p: str) -> Optional[str]:
        """Translate a SPAD parent expression to a Lean extends clause with α applied."""
        p = p.strip()
        if not p or not p[0].isupper():
            return None

        # Parametric parent: Name(arg1, arg2, ...)
        m = re.match(r'([A-Za-z][A-Za-z0-9]*)\s*\((.+)\)$', p, re.DOTALL)
        if m:
            base = m.group(1)
            raw_args = m.group(2).strip()
            args = _depth_split(raw_args)
            lean_args = []
            for arg in args:
                arg = arg.strip()
                if arg == '%' or re.search(r':\s*(?:Rng|Ring|SemiRng)\b', arg):
                    lean_args.append('α')
                else:
                    lean_args.append(translate_type(arg))
            lean_args.append('α')          # carrier type always last
            return f"{base} {' '.join(lean_args)}"

        # Non-parametric bare name → apply carrier α
        return f"{p} α"

    def generate_class(self, cat: Category) -> str:
        lines = []

        # extends list — all parents get α applied
        extends = [self._translate_parent(p) for p in cat.parents]
        extends = [e for e in extends if e]

        # Class header
        if cat.params:
            pstr = " ".join(f"({n} : {k})" for n, k in cat.params)
            header = f"class {cat.long_name} {pstr} (α : Type*)"
        else:
            header = f"class {cat.long_name} (α : Type*)"

        ext = (" extends " + ", ".join(extends)) if extends else ""
        lines.append(f"{header}{ext} where")

        # Operations (deduplicated by lean field name; constants emitted as values)
        seen_fields: set = set()
        emitted = 0
        for op in cat.ops:
            lean_name = op_to_field(op.name, len(op.domain))
            if lean_name in seen_fields:
                continue
            seen_fields.add(lean_name)
            dom = [translate_type(t) for t in op.domain]
            cod = translate_type(op.codomain)
            # Nullary: emit as a value field, not a function
            if dom:
                sig = " → ".join(dom + [cod])
            else:
                sig = cod
            doc_suffix = f"  -- {op.doc}" if op.doc else ""
            lines.append(f"  {lean_name} : {sig}{doc_suffix}")
            emitted += 1

        if emitted == 0:
            lines.append("  -- (no new operations beyond inherited)")

        # Axioms — compiled to Lean propositions where possible
        compiler = AxiomCompiler(cat, self.cat_by_name)
        compiled, informal = [], []
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
            "-- Sources: catdef.spad · naalgc.spad · logic.spad",
            "",
        ]
        for cat in self.categories:
            src = f"  [{cat.source_file}]" if cat.source_file else ""
            parts.append(f"-- {'─'*68}")
            parts.append(f"-- {cat.long_name}  [{cat.abbrev}]{src}")
            parts.append(f"-- {'─'*68}")
            parts.append(self.generate_class(cat))
            parts.append("")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# SPAD file parser
# ---------------------------------------------------------------------------

def _strip_dash_comments(text: str) -> str:
    """Strip -- comments from non-doc lines, preserving ++ doc lines."""
    cleaned = []
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('++'):
            cleaned.append(line)
            continue
        out, in_str, i = [], False, 0
        while i < len(line):
            c = line[i]
            if c == '"':
                in_str = not in_str; out.append(c)
            elif not in_str and line[i:i+2] == '--':
                break
            else:
                out.append(c)
            i += 1
        cleaned.append(''.join(out))
    return '\n'.join(cleaned)

def parse_spad_file(path: Path) -> list:
    text = _strip_dash_comments(path.read_text())
    categories = []
    abbrev_re = re.compile(r'\)abbrev\s+category\s+(\w+)\s+(\w+)', re.MULTILINE)
    matches = list(abbrev_re.finditer(text))

    for idx, m in enumerate(matches):
        abbrev, long_name = m.group(1), m.group(2)
        start = m.start()
        end = matches[idx+1].start() if idx+1 < len(matches) else len(text)
        block = text[start:end]

        # Split block into doc-comment section and signature section
        doc_lines, sig_lines, past_abbrev = [], [], False
        for line in block.split('\n'):
            if not past_abbrev:
                past_abbrev = True; continue
            s = line.strip()
            if not sig_lines and (s.startswith('++') or s == ''):
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
            abbrev=abbrev, long_name=long_name,
            params=params, parents=parents,
            ops=ops, axioms=axioms,
            source_file=path.name,
        ))

    return categories


def _parse_signature(sig_block: str, long_name: str) -> tuple:
    pat = re.compile(
        r'\b' + re.escape(long_name) + r'\s*'
        r'(?:\(([^)]*)\))?\s*:\s*Category\s*==\s*(.*)',
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
# Multi-file entry point
# ---------------------------------------------------------------------------

def parse_spad_files(paths: list) -> list:
    """Parse multiple SPAD files; first definition of a category wins."""
    seen: set = set()
    all_cats = []
    for path in paths:
        p = Path(path)
        if not p.exists():
            print(f"Warning: {p} not found — skipping", file=sys.stderr)
            continue
        for cat in parse_spad_file(p):
            if cat.long_name not in seen:
                seen.add(cat.long_name)
                all_cats.append(cat)
    return all_cats


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def report_stats(categories: list) -> str:
    total_ops = sum(len(c.ops) for c in categories)
    total_axioms = sum(len(c.axioms) for c in categories)
    cats_with_axioms = sum(1 for c in categories if c.axioms)
    no_axioms = sorted(c.long_name for c in categories if not c.axioms)
    density = 100 * cats_with_axioms / len(categories) if categories else 0

    # Count constants parsed
    total_constants = sum(
        1 for c in categories for op in c.ops if op.domain == []
    )

    by_file: dict = {}
    for c in categories:
        by_file.setdefault(c.source_file, 0)
        by_file[c.source_file] += 1

    lines = [
        f"Categories parsed:          {len(categories)}",
    ]
    for fname, count in sorted(by_file.items()):
        lines.append(f"  {fname or '(unknown)':<30} {count}")
    lines += [
        f"Operations extracted:       {total_ops}",
        f"  of which constants/nullary: {total_constants}",
        f"Axiom equations found:      {total_axioms}",
        f"Categories with axioms:     {cats_with_axioms} / {len(categories)} "
        f"({density:.1f}% formalization density)",
        "",
        f"Implicit-contract gap — {len(no_axioms)} categories state no axioms:",
    ]
    for name in no_axioms:
        lines.append(f"  - {name}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_FILES = [
    DATA_DIR / "catdef.spad",
    DATA_DIR / "naalgc.spad",
    DATA_DIR / "logic.spad",
    DATA_DIR / "aggcat.spad",
]

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Transpile FriCAS SPAD categories to Lean 4")
    ap.add_argument("spad_files", nargs='*',
                    default=[str(f) for f in DEFAULT_FILES],
                    help="SPAD source files (default: catdef.spad naalgc.spad logic.spad aggcat.spad)")
    ap.add_argument("--output", "-o",
                    default=str(Path(__file__).parent / "output" / "FriCAS_Algebra.lean"))
    args = ap.parse_args()

    categories = parse_spad_files(args.spad_files)
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
