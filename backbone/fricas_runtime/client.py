"""
FriCAS client — two modes:

  Direct mode (default, no server needed):
    Calls FriCAS subprocess directly with SQLite caching via the server module.

  Server mode (pass server_proc to __init__):
    Communicates with a running server.py over stdin/stdout pipes.

Usage:
    from backbone.fricas_runtime.client import FriCASClient

    with FriCASClient() as client:
        result = client.integrate("x/(x^2+1)", "x")
        print(result["antiderivative"])   # "log(x^2+1)/2"
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

_SERVER = Path(__file__).parent / "server.py"


class FriCASClient:
    """Synchronous client for the FriCAS JSON-RPC server."""

    def __init__(
        self,
        *,
        server_script: Path = _SERVER,
        python: str = sys.executable,
        env: Optional[dict] = None,
    ) -> None:
        self._proc = subprocess.Popen(
            [python, str(server_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        self._lock = threading.Lock()
        self._next_id = 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def integrate(self, integrand: str, var: str = "x", timeout: int = 30) -> dict:
        """Return the FriCAS result dict for integrate(integrand, var).

        Keys: antiderivative (str|None), raw_output (str),
              elapsed_ms (float), cached (bool), error (str, optional).
        """
        return self._call("integrate",
                          {"integrand": integrand, "var": var, "timeout": timeout})

    def ping(self) -> str:
        return self._call("ping", {})["result"]

    def cache_stats(self) -> dict:
        return self._call("cache_stats", {})["result"]

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def close(self) -> None:
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()

    def __enter__(self) -> "FriCASClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(self, method: str, params: dict) -> dict:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            req = json.dumps({"method": method, "params": params, "id": req_id})
            self._proc.stdin.write(req + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()

        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(f"FriCAS server error: {resp['error']}")
        return resp
