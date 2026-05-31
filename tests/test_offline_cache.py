"""
Tests for fricas_bridge/offline_cache.py — Swing 1 Step E (two-mode resolver).

Verifies:
  - cache_key matches backbone/fricas_runtime/server.py exactly
  - the committed JSON is in sync with a fresh deterministic build
  - lookup() returns the corpus antiderivatives for the 4 Class A claims
  - FriCASResolver offline mode is cache-only and never spawns FriCAS
  - FriCASResolver online mode falls back to the cache when FriCAS is absent
  - strict mode raises on a miss; non-strict returns origin="miss"

Run with:  python -m pytest tests/test_offline_cache.py -v
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fricas_bridge.offline_cache import (
    FriCASResolver,
    ResolveResult,
    build_offline_cache,
    cache_key,
    load_offline_cache,
    lookup,
)

_CACHE_PATH = Path(__file__).parent.parent / "fricas_bridge" / "data" / "fricas_offline_cache.json"


# ---------------------------------------------------------------------------
# Key scheme parity with the live server
# ---------------------------------------------------------------------------

def test_cache_key_is_sha256_of_integrand_var():
    expected = hashlib.sha256("x/(x^2+1)||x".encode()).hexdigest()
    assert cache_key("x/(x^2+1)", "x") == expected


def test_cache_key_matches_server_module():
    """The offline key must equal the live server's _cache_key byte-for-byte."""
    from backbone.fricas_runtime.server import _cache_key
    for integrand, var in [("x/(x^2+1)", "x"), ("1/x", "x"), ("2*x/(1+x^4)", "x")]:
        assert cache_key(integrand, var) == _cache_key(integrand, var)


def test_cache_key_var_sensitive():
    assert cache_key("x/(x^2+1)", "x") != cache_key("x/(x^2+1)", "t")


# ---------------------------------------------------------------------------
# Committed file integrity
# ---------------------------------------------------------------------------

def test_cache_file_exists():
    assert _CACHE_PATH.exists(), f"offline cache not found at {_CACHE_PATH}"


def test_cache_file_is_valid_json():
    doc = json.loads(_CACHE_PATH.read_text())
    assert "entries" in doc
    assert "schema_version" in doc
    assert doc["key_scheme"] == "sha256(integrand||var)"


def test_cache_file_matches_generator():
    """Committed JSON must equal a fresh deterministic build (CI guard)."""
    expected = build_offline_cache()
    actual = json.loads(_CACHE_PATH.read_text())
    assert actual == expected, (
        "fricas_offline_cache.json is out of sync with the corpus.\n"
        "Regenerate with: python -m fricas_bridge.offline_cache --generate"
    )


def test_cache_entry_count_matches_field():
    doc = load_offline_cache(force_reload=True)
    assert doc["entry_count"] == len(doc["entries"])


def test_cache_has_at_least_20_entries():
    doc = load_offline_cache()
    assert len(doc["entries"]) >= 20


def test_every_entry_key_is_consistent():
    """Each entry's dict key must equal cache_key(integrand, var)."""
    doc = load_offline_cache()
    for key, entry in doc["entries"].items():
        assert key == cache_key(entry["integrand"], entry["var"]), (
            f"entry key {key} does not match cache_key for {entry['integrand']!r}"
        )


def test_every_entry_has_required_fields():
    doc = load_offline_cache()
    for entry in doc["entries"].values():
        for field in ("integrand", "var", "antiderivative", "label", "class", "source"):
            assert field in entry, f"entry missing {field}: {entry}"


# ---------------------------------------------------------------------------
# lookup() — Class A claims and known corpus values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("integrand,expected", [
    ("x/(x^2+1)",                   "log(x^2+1)/2"),
    ("2*x/(1+x^4)",                 "atan(x^2)"),
    ("1/(x^2+2*x+2)",               "atan(x+1)"),
    ("(2*x*log(x^2+1)+x^3)/(x^2+1)", "log(x^2+1)^2/2 + x^2/2 - log(x^2+1)/2"),
    ("1/x",                         "log(x)"),
    ("1/(x^2-1)",                   "log(x-1)/2 - log(x+1)/2"),
])
def test_lookup_known(integrand: str, expected: str):
    assert lookup(integrand) == expected


def test_lookup_miss_returns_none():
    assert lookup("exp(x^17 + sin(x))") is None


# ---------------------------------------------------------------------------
# FriCASResolver — offline mode
# ---------------------------------------------------------------------------

def test_offline_resolver_hits_cache():
    r = FriCASResolver(mode="offline")
    res = r.resolve("x/(x^2+1)")
    assert isinstance(res, ResolveResult)
    assert res.ok
    assert res.antiderivative == "log(x^2+1)/2"
    assert res.origin == "offline_cache"
    assert res.cached is True


def test_offline_resolver_miss_nonstrict():
    r = FriCASResolver(mode="offline")
    res = r.resolve("totally_unknown_integrand(x)")
    assert not res.ok
    assert res.origin == "miss"
    assert res.antiderivative is None


def test_offline_resolver_miss_strict_raises():
    r = FriCASResolver(mode="offline", strict=True)
    with pytest.raises(KeyError):
        r.resolve("totally_unknown_integrand(x)")


def test_offline_resolver_never_calls_live(monkeypatch):
    """Offline mode must not even attempt a live FriCAS call."""
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("offline mode must not call FriCAS")

    monkeypatch.setattr(FriCASResolver, "_try_live", staticmethod(_boom))
    r = FriCASResolver(mode="offline")
    res = r.resolve("x/(x^2+1)")
    assert res.ok
    assert called["n"] == 0


# ---------------------------------------------------------------------------
# FriCASResolver — online mode
# ---------------------------------------------------------------------------

def test_online_resolver_falls_back_to_cache(monkeypatch):
    """When the live call yields nothing, online mode serves the cache."""
    monkeypatch.setattr(FriCASResolver, "_try_live", staticmethod(lambda *a, **k: None))
    r = FriCASResolver(mode="online")
    res = r.resolve("x/(x^2+1)")
    assert res.ok
    assert res.origin == "offline_cache"
    assert res.cached is True


def test_online_resolver_prefers_live(monkeypatch):
    """When the live call succeeds, online mode returns it (cached=False)."""
    monkeypatch.setattr(
        FriCASResolver, "_try_live",
        staticmethod(lambda *a, **k: "LIVE_RESULT"),
    )
    r = FriCASResolver(mode="online")
    res = r.resolve("x/(x^2+1)")
    assert res.antiderivative == "LIVE_RESULT"
    assert res.origin == "fricas_live"
    assert res.cached is False


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        FriCASResolver(mode="sideways")
