#!/usr/bin/env bash
# Reproducibly typeset paper/proofforge-omega.md to PDF (and emit the LaTeX).
#
# We cannot rely on a Unicode font being present, and pdflatex/xelatex only
# *warn* on a missing glyph (the PDF still "succeeds" with a hole) — so we:
#   1. map the handful of non-ASCII math symbols the source uses to LaTeX math,
#      leaving accented names (é, ë) and en/em dashes to pandoc's normal handling;
#   2. compile with pdflatex (no font dependencies);
#   3. FAIL CLOSED if the LaTeX log reports any "Missing character".
#
# Single source of truth: the Markdown keeps its Unicode (renders nicely on
# GitHub); only this transient build copy is rewritten.
set -euo pipefail
cd "$(dirname "$0")"

SRC="proofforge-omega.md"
BUILD="_build.md"
TEX="proofforge-omega.tex"
PDF="proofforge-omega.pdf"

# 1. Map pdflatex-unsafe Unicode to LaTeX math (deterministic, no fonts needed).
python3 - "$SRC" "$BUILD" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
t = open(src, encoding="utf-8").read()
repl = {
    "→": r"$\to$",            # →
    "↔": r"$\leftrightarrow$",# ↔
    "Ω": r"$\Omega$",         # Ω
    "Σ": r"$\Sigma$",         # Σ
    "≥": r"$\ge$",            # ≥
    "≠": r"$\ne$",            # ≠
    "×": r"$\times$",         # ×
    "·": r"$\cdot$",          # ·
    "−": r"$-$",              # − (minus)
    "₁": r"$_{1}$", "₂": r"$_{2}$", "₃": r"$_{3}$",
    "₄": r"$_{4}$", "₅": r"$_{5}$",
    "⁵": r"$^{5}$", "ⁿ": r"$^{n}$", "ᵢ": r"$_{i}$",
    "§": "Sec. ",        # § → "Sec." (non-breaking space)
}
for k, v in repl.items():
    t = t.replace(k, v)
open(out, "w", encoding="utf-8").write(t)
PY

# 2. Markdown -> standalone LaTeX, then pdflatex twice (refs/toc).
pandoc "$BUILD" --from gfm -t latex -s \
    -V geometry:margin=1in -V fontsize=10pt -V colorlinks=true \
    -o "$TEX"

pdflatex -interaction=nonstopmode -halt-on-error "$TEX" >/dev/null 2>&1 || true
pdflatex -interaction=nonstopmode -halt-on-error "$TEX" >/dev/null 2>&1 || true

LOG="${TEX%.tex}.log"
if [ ! -f "$PDF" ]; then
    echo "FAIL: no PDF produced. Last LaTeX log lines:"
    tail -n 60 "$LOG" 2>/dev/null || true
    exit 1
fi
if grep -qi "Missing character" "$LOG"; then
    echo "FAIL: missing glyphs in PDF (fail-closed):"
    grep -i "Missing character" "$LOG" | sort -u
    exit 1
fi

echo "OK: built $PDF and $TEX"
ls -la "$PDF" "$TEX"
