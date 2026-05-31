#!/usr/bin/env python3
"""
FriCAS JSON-RPC server — newline-delimited JSON over stdin/stdout.

Each request line: {"method": "integrate", "params": {"integrand": "...", "var": "x"}, "id": 1}
Each response line: {"result": {"antiderivative": "...", "elapsed_ms": 230, "cached": false}, "id": 1}

Cache: SQLite at $FRICAS_CACHE_DIR (default ~/.cache/fricas_runtime/cache.db).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

FRICAS_BIN: str = os.environ.get("FRICAS_BIN", "fricas")
CACHE_DIR: Path = Path(os.environ.get(
    "FRICAS_CACHE_DIR",
    Path.home() / ".cache" / "fricas_runtime"
))

_PREAMBLE = ")set output algebra on\n)set output mathml off\n)set output tex off\n"
_RESULT_RE = re.compile(r'\(1\)\s+(.*?)(?=\n\(|\Z)', re.DOTALL)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class _Cache:
    def __init__(self, db_path: Path) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                key          TEXT PRIMARY KEY,
                integrand    TEXT NOT NULL,
                var          TEXT NOT NULL,
                antiderivative TEXT,
                raw_output   TEXT,
                elapsed_ms   REAL NOT NULL,
                cached_at    TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def get(self, key: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT antiderivative, raw_output, elapsed_ms FROM results WHERE key = ?",
            (key,)
        ).fetchone()
        if row is None:
            return None
        return {"antiderivative": row[0], "raw_output": row[1],
                "elapsed_ms": row[2], "cached": True}

    def put(self, key: str, integrand: str, var: str, result: dict) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO results
                (key, integrand, var, antiderivative, raw_output, elapsed_ms, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (key, integrand, var,
              result.get("antiderivative"),
              result.get("raw_output"),
              result.get("elapsed_ms", 0.0),
              datetime.now(timezone.utc).isoformat()))
        self._conn.commit()


def _cache_key(integrand: str, var: str) -> str:
    return hashlib.sha256(f"{integrand}||{var}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# FriCAS caller (one subprocess per request — reliable, cache amortises cost)
# ---------------------------------------------------------------------------

def _call_fricas(integrand: str, var: str, timeout: int = 30) -> dict:
    if not shutil.which(FRICAS_BIN):
        return {"antiderivative": None, "raw_output": "fricas not found",
                "elapsed_ms": 0.0, "cached": False, "error": "fricas_not_found"}

    cmd = f"{_PREAMBLE}integrate({integrand}, {var})\n)quit\n"
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [FRICAS_BIN, "-nosman"],
            input=cmd, capture_output=True, text=True, timeout=timeout
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        output = proc.stdout or ""

        # Parse antiderivative from "(1) <expr>" pattern
        antiderivative: Optional[str] = None
        m = _RESULT_RE.search(output)
        if m:
            candidate = m.group(1).strip().replace("\n", " ")
            candidate = re.sub(r"\s+", " ", candidate)
            # Reject known non-results
            if not any(kw in candidate.lower() for kw in
                       ("closed form", "error", "cannot", "not found", "type mismatch")):
                antiderivative = candidate

        return {"antiderivative": antiderivative, "raw_output": output,
                "elapsed_ms": elapsed_ms, "cached": False}

    except subprocess.TimeoutExpired:
        return {"antiderivative": None, "raw_output": "timeout",
                "elapsed_ms": timeout * 1000.0, "cached": False, "error": "timeout"}
    except Exception as exc:
        return {"antiderivative": None, "raw_output": str(exc),
                "elapsed_ms": (time.monotonic() - t0) * 1000, "cached": False,
                "error": str(exc)}


# ---------------------------------------------------------------------------
# JSON-RPC dispatch
# ---------------------------------------------------------------------------

def _handle(req: dict, cache: _Cache) -> dict:
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params") or {}

    if method == "ping":
        return {"result": "pong", "id": req_id}

    if method == "integrate":
        integrand = str(params.get("integrand", ""))
        var = str(params.get("var", "x"))
        if not integrand:
            return {"error": {"code": -32602, "message": "missing integrand"}, "id": req_id}

        key = _cache_key(integrand, var)
        result = cache.get(key)
        if result is None:
            result = _call_fricas(integrand, var,
                                  timeout=int(params.get("timeout", 30)))
            cache.put(key, integrand, var, result)
        return {"result": result, "id": req_id}

    if method == "cache_stats":
        conn = cache._conn
        row = conn.execute("SELECT COUNT(*) FROM results").fetchone()
        hits = conn.execute(
            "SELECT COUNT(*) FROM results WHERE antiderivative IS NOT NULL"
        ).fetchone()
        return {"result": {"total": row[0], "with_antiderivative": hits[0]}, "id": req_id}

    return {"error": {"code": -32601, "message": f"unknown method: {method}"}, "id": req_id}


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _Cache(CACHE_DIR / "cache.db")

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            resp = {"error": {"code": -32700, "message": str(exc)}, "id": None}
        else:
            resp = _handle(req, cache)

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
