#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK="$ROOT/tools/toolchain.lock.json"
BIN="$ROOT/tools/bin"
SRC="$ROOT/tools/src"

mkdir -p "$BIN" "$SRC"

get_ref() { python3 - <<PY
import json
d=json.load(open("$LOCK"))
print(d["$1"]["ref"])
PY
}

CADICAL_REF="$(get_ref cadical)"
DRAT_REF="$(get_ref drat_trim)"
LRAT_TRIM_REF="$(get_ref lrat_trim)"

# CaDiCaL
if [ ! -x "$BIN/cadical" ]; then
  rm -rf "$SRC/cadical"
  git clone --depth 1 --branch "$CADICAL_REF" https://github.com/arminbiere/cadical.git "$SRC/cadical"
  (cd "$SRC/cadical" && ./configure && make -j2)
  cp "$SRC/cadical/build/cadical" "$BIN/cadical"
fi

# DRAT-trim
if [ ! -x "$BIN/drat-trim" ]; then
  rm -rf "$SRC/drat-trim"
  git clone --depth 1 --branch "$DRAT_REF" https://github.com/marijnheule/drat-trim.git "$SRC/drat-trim"
  (cd "$SRC/drat-trim" && make -j2)
  cp "$SRC/drat-trim/drat-trim" "$BIN/drat-trim"
fi

# LRAT-trim
if [ ! -x "$BIN/lrat-trim" ]; then
  rm -rf "$SRC/lrat-trim"
  git clone --depth 1 --branch "$LRAT_TRIM_REF" https://github.com/arminbiere/lrat-trim.git "$SRC/lrat-trim"
  (cd "$SRC/lrat-trim" && ./configure && make -j2)
  cp "$SRC/lrat-trim/lrat-trim" "$BIN/lrat-trim"
fi

echo "OK: SAT toolchain installed"
