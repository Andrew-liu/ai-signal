#!/usr/bin/env python3
"""Remove secret-like URL parameters and sensitive fields from public JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


try:
    from scripts.safe_io import atomic_write_json
except ModuleNotFoundError:
    from safe_io import atomic_write_json

SENSITIVE_KEYS = {
    "api_key", "apikey", "x_api_key", "access_token", "auth_token", "authorization", "bearer_token",

    "client_secret", "cookie", "cookies", "password", "private_key", "refresh_token",
    "secret", "token", "xsec_token",
}
SENSITIVE_QUERY_KEYS = SENSITIVE_KEYS | {"key", "sig", "signature"}


def normalize_sensitive_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


SENSITIVE_KEY_NAMES = {normalize_sensitive_name(key) for key in SENSITIVE_KEYS}
SENSITIVE_QUERY_KEY_NAMES = {normalize_sensitive_name(key) for key in SENSITIVE_QUERY_KEYS}


def is_http_url(value: str) -> bool:
    return str(value or "").lstrip().lower().startswith(("http://", "https://"))


def clean_url(value: str) -> str:
    try:
        parsed = urlparse(str(value or "").strip())
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            return value
        query = [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if normalize_sensitive_name(key) not in SENSITIVE_QUERY_KEY_NAMES
        ]
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunparse(parsed._replace(scheme=scheme, netloc=host, query=urlencode(query, doseq=True), fragment=""))
    except Exception:
        return value



def clean(value: Any, key: str = "") -> Any:
    normalized = normalize_sensitive_name(key)
    if normalized in SENSITIVE_KEY_NAMES:

        return None
    if isinstance(value, dict):
        return {name: clean(child, str(name)) for name, child in value.items()}
    if isinstance(value, list):
        return [clean(child) for child in value]
    if isinstance(value, str):
        if is_http_url(value):
            return clean_url(value)

        if normalized in {"summary", "preview", "description"} and len(value) > 360:
            return value[:359].rstrip() + "…"
    return value



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    compact_files = {
        "archive.json", "latest-24h-all.json", "latest-24h-all-raw.json", "stories-merged.json"
    }
    for path in sorted(args.data_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        compact = path.name in compact_files
        atomic_write_json(path, clean(payload), indent=None if compact else 2, compact=compact)
        print(f"sanitized: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
