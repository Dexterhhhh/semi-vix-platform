"""Client for the in-container Go numerical engine.

Development and unit tests keep the Python implementation as a reference.
Production sets ``SVIX_GO_ENGINE_URL`` and therefore executes the numerical
hot path in the long-lived Go process without changing the public API.
"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

_direct_opener = build_opener(ProxyHandler({}))


def enabled() -> bool:
    return bool(os.getenv("SVIX_GO_ENGINE_URL"))


def call(path: str, payload: dict[str, object]) -> dict[str, object]:
    base = os.environ["SVIX_GO_ENGINE_URL"].rstrip("/")
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload, allow_nan=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _direct_opener.open(request, timeout=20) as response:
            value = json.load(response)
    except HTTPError as exc:
        detail = exc.read(2048).decode(errors="replace").strip()
        raise ValueError(f"Go engine rejected input: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Go calculation engine is unavailable") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Go calculation engine returned an invalid response")
    return value
