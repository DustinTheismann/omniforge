"""
fricas_bridge/offline_cache.py — Swing 1 Step E: the two-mode FriCAS resolver.

The `by fricas_integrate` tactic must run in two environments:

  * **online**  — a developer's machine with FriCAS installed.  Calls the live
    CAS via `backbone.fricas_runtime.client.FriCASClient`, and falls back to the
    committed offline cache if FriCAS is absent or returns no result.
  * **offline** — Mathlib CI, the Lean toolchain, anyone reproducing a runpack.
    *No FriCAS process is spawned.*  Every answer comes from the committed
    `data/fricas_offline_cache.json`.  A cache miss is a hard error, never a
    silent network call.

The cache is keyed by ``sha256(f"{integrand}||{var}")`` — byte-for-byte the same
scheme as `backbone/fricas_runtime/server.py`, so a key computed here is valid
against the live server's SQLite store and vice versa.

The committed JSON is regenerated deterministically from the integral corpus:

    python -m fricas_bridge.offline_cache --generate

and checked in CI:

    python -m fricas_bridge.offline_cache --verify

Public API
----------
cache_key(integrand, var)            → str   (sha256, matches server.py)
load_offline_cache()                 → dict  (parsed JSON)
lookup(integrand, var)               → str | None
build_offline_cache()                → dict  (deterministic, from corpus)
FriCASResolver(mode=...).resolve(..) → ResolveResult
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DATA_DIR    = Path(__file__).parent / "data"
_CACHE_PATH  = _DATA_DIR / "fricas_offline_cache.json"
_SCHEMA_VER  = "0.1.0"
_KEY_SCHEME  = "sha256(integrand||var)"


# ---------------------------------------------------------------------------
# Keying — must stay identical to backbone/fricas_runtime/server.py::_cache_key
# ---------------------------------------------------------------------------

def cache_key(integrand: str, var: str = "x") -> str:
    """Return the cache key for (integrand, var). Matches server.py exactly."""
    return hashlib.sha256(f"{integrand}||{var}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic cache construction from the integral corpus
# ---------------------------------------------------------------------------

def _corpus_entries() -> list[dict]:
    """
    Gather every (integrand, var, antiderivative) the project already trusts:
      1. fricas_integrate.CORPUS  (24-entry Bronstein table, with class labels)
      2. the 9 committed claim-protocol examples (richer provenance)

    Returns a list of normalised entry dicts.  Later sources annotate, never
    overwrite, an antiderivative already present for the same key.
    """
    from fricas_bridge.fricas_integrate import CORPUS

    by_key: dict[str, dict] = {}

    for item in CORPUS:
        integrand = item["integrand"]
        var       = item.get("var", "x")
        key       = cache_key(integrand, var)
        by_key[key] = {
            "integrand":      integrand,
            "var":            var,
            "antiderivative": item["antiderivative"],
            "label":          item["label"],
            "class":          item.get("class", "?"),
            "source":         f"corpus:{item['label']}",
        }

    examples = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"
    for n in range(1, 10):
        claim     = json.loads((examples / f"risch_bronstein_{n:03d}.json").read_text())
        integrand = claim["inputs"]["integrand"]
        var       = "x"
        antideriv = claim["outputs"]["candidate_antiderivative"]
        key       = cache_key(integrand, var)
        cid       = f"pf.integral.bronstein_{n:03d}"
        if key in by_key:
            # Same integral already supplied by CORPUS; record the cross-reference.
            by_key[key]["source"] = f"corpus+claim:{by_key[key]['label']}/{cid}"
        else:
            by_key[key] = {
                "integrand":      integrand,
                "var":            var,
                "antiderivative": antideriv,
                "label":          cid,
                "class":          "?",
                "source":         f"claim:{cid}",
            }

    return list(by_key.values())


def build_offline_cache() -> dict:
    """
    Return the full offline-cache document, deterministically.

    Entries are keyed by cache_key and the whole structure is JSON-serialisable
    with sort_keys=True for a stable on-disk form.
    """
    entries = {cache_key(e["integrand"], e["var"]): e for e in _corpus_entries()}
    return {
        "schema_version": _SCHEMA_VER,
        "description": (
            "Offline FriCAS integration cache for the `by fricas_integrate` "
            "tactic. Lets Lean/Mathlib CI resolve antiderivatives without a "
            "live FriCAS process. Regenerate with "
            "`python -m fricas_bridge.offline_cache --generate`."
        ),
        "key_scheme": _KEY_SCHEME,
        "entry_count": len(entries),
        "entries": entries,
    }


def _serialise(doc: dict) -> str:
    """Canonical JSON text for the cache document (stable, newline-terminated)."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Loading / lookup
# ---------------------------------------------------------------------------

_loaded: Optional[dict] = None


def load_offline_cache(*, force_reload: bool = False) -> dict:
    """Load and memoise the committed offline cache document."""
    global _loaded
    if _loaded is None or force_reload:
        if not _CACHE_PATH.exists():
            raise FileNotFoundError(
                f"offline cache not found at {_CACHE_PATH}; "
                f"generate it with `python -m fricas_bridge.offline_cache --generate`"
            )
        _loaded = json.loads(_CACHE_PATH.read_text())
    return _loaded


def lookup(integrand: str, var: str = "x") -> Optional[str]:
    """Return the cached antiderivative for (integrand, var), or None on miss."""
    doc = load_offline_cache()
    entry = doc["entries"].get(cache_key(integrand, var))
    return entry["antiderivative"] if entry else None


# ---------------------------------------------------------------------------
# Two-mode resolver
# ---------------------------------------------------------------------------

@dataclass
class ResolveResult:
    """Outcome of a resolve() call."""
    integrand: str
    var: str
    antiderivative: Optional[str]
    origin: str          # "offline_cache" | "fricas_live" | "miss"
    cached: bool         # True if served without spawning FriCAS

    @property
    def ok(self) -> bool:
        return self.antiderivative is not None


class FriCASResolver:
    """
    Resolve an integrand → antiderivative in one of two modes.

    mode="offline" (default):
        Cache-only.  Never spawns FriCAS.  Suitable for Mathlib CI and runpack
        reproduction.  A miss yields ``origin="miss"`` (and, if strict, raises).

    mode="online":
        Try the live FriCAS runtime first; on absence/failure/empty-result,
        fall back to the committed offline cache.
    """

    def __init__(self, mode: str = "offline", *, strict: bool = False) -> None:
        if mode not in ("offline", "online"):
            raise ValueError(f"mode must be 'offline' or 'online', got {mode!r}")
        self.mode = mode
        self.strict = strict

    def resolve(self, integrand: str, var: str = "x", *, timeout: int = 30) -> ResolveResult:
        if self.mode == "online":
            live = self._try_live(integrand, var, timeout=timeout)
            if live is not None:
                return ResolveResult(integrand, var, live, "fricas_live", cached=False)

        cached = lookup(integrand, var)
        if cached is not None:
            return ResolveResult(integrand, var, cached, "offline_cache", cached=True)

        if self.strict:
            raise KeyError(
                f"no antiderivative for integrate({integrand}, {var}) in offline cache "
                f"(mode={self.mode}); add it to the corpus and regenerate the cache"
            )
        return ResolveResult(integrand, var, None, "miss", cached=True)

    # -- internal -----------------------------------------------------------

    @staticmethod
    def _try_live(integrand: str, var: str, *, timeout: int) -> Optional[str]:
        """Attempt a live FriCAS call; return None if unavailable or empty."""
        try:
            from backbone.fricas_runtime.client import FriCASClient
        except Exception:
            return None
        try:
            with FriCASClient() as client:
                res = client.integrate(integrand, var, timeout=timeout)
            anti = res.get("antiderivative")
            return anti if anti else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _verify() -> bool:
    """Return True iff the committed cache matches a fresh deterministic build."""
    expected = _serialise(build_offline_cache())
    if not _CACHE_PATH.exists():
        print(f"FAIL: {_CACHE_PATH} does not exist", file=sys.stderr)
        return False
    actual = _CACHE_PATH.read_text()
    if actual != expected:
        print("FAIL: fricas_offline_cache.json is out of sync with the corpus.\n"
              "Regenerate with `python -m fricas_bridge.offline_cache --generate`.",
              file=sys.stderr)
        return False
    doc = json.loads(actual)
    print(f"OK: offline cache matches corpus ({doc['entry_count']} entries)")
    return True


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Two-mode FriCAS offline cache")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true",
                       help="(re)write data/fricas_offline_cache.json from the corpus")
    group.add_argument("--verify", action="store_true",
                       help="check the committed cache matches the corpus")
    group.add_argument("--lookup", metavar="INTEGRAND",
                       help="print the cached antiderivative for an integrand")
    parser.add_argument("--var", default="x", help="integration variable (default: x)")
    args = parser.parse_args()

    if args.generate:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        doc = build_offline_cache()
        _CACHE_PATH.write_text(_serialise(doc))
        print(f"Written {_CACHE_PATH} ({doc['entry_count']} entries)")
    elif args.verify:
        sys.exit(0 if _verify() else 1)
    else:  # --lookup
        anti = lookup(args.lookup, args.var)
        if anti is None:
            print(f"miss: no cached antiderivative for integrate({args.lookup}, {args.var})",
                  file=sys.stderr)
            sys.exit(1)
        print(anti)


if __name__ == "__main__":
    main()
