#!/usr/bin/env python3
"""Validate generated AI Signal data before it can replace the live snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

PUBLIC_FILES = (
    "latest-24h.json",
    "latest-24h-all.json",
    "daily-brief.json",
    "source-status.json",
    "stories-merged.json",
    "top3-personas.json",
    "waytoagi-7d.json",
)
SENSITIVE_KEYS = {
    "api_key", "apikey", "x_api_key", "access_token", "auth_token", "authorization",

    "bearer_token", "client_secret", "cookie", "cookies", "password",
    "private_key", "refresh_token", "secret", "token", "xsec_token",
}
SENSITIVE_QUERY_KEYS = SENSITIVE_KEYS | {"key", "sig", "signature"}


def normalize_sensitive_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


SENSITIVE_KEY_NAMES = {normalize_sensitive_name(key) for key in SENSITIVE_KEYS}
SENSITIVE_QUERY_KEY_NAMES = {normalize_sensitive_name(key) for key in SENSITIVE_QUERY_KEYS}
SECRET_PATTERNS = (

    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.I),
    re.compile(r"\bsk-(?!hynix(?:\b|-))[A-Za-z0-9_-]{20,}\b", re.I),
)


class GateError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid JSON: {path}: {exc}") from exc


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise GateError(f"invalid generated_at: {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateError(f"invalid ISO time: {value!r}") from exc
    if parsed.tzinfo is None:
        raise GateError(f"generated_at must include timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def validate_item(item: Any, context: str) -> None:
    require(isinstance(item, dict), f"{context} must be an object")
    require(bool(item.get("id") or item.get("story_id")), f"{context} needs id/story_id")
    require(isinstance(item.get("title"), str) and bool(item["title"].strip()), f"{context} needs title")
    url = item.get("url") or item.get("primary_url")
    if url:
        parsed = urlparse(str(url))
        require(parsed.scheme in {"http", "https"}, f"{context} has unsafe URL scheme")


def validate_shapes(payloads: dict[str, Any]) -> None:
    latest = payloads["latest-24h.json"]
    require(isinstance(latest, dict), "latest-24h.json must be an object")
    require(isinstance(latest.get("total_items"), int), "latest total_items must be integer")
    latest_items = latest.get("items_ai") or latest.get("items") or []
    require(isinstance(latest_items, list), "latest items must be a list")
    require(latest["total_items"] == len(latest_items), "latest total_items mismatch")
    for index, item in enumerate(latest_items):
        validate_item(item, f"latest item {index}")

    all_payload = payloads["latest-24h-all.json"]
    require(isinstance(all_payload, dict), "latest-24h-all.json must be an object")
    all_items = all_payload.get("items_all") or []
    require(isinstance(all_items, list), "items_all must be a list")

    brief = payloads["daily-brief.json"]
    brief_items = brief.get("items") if isinstance(brief, dict) else None
    require(isinstance(brief_items, list), "daily brief items must be a list")
    require(brief.get("total_items") == len(brief_items), "daily brief total_items mismatch")
    for index, item in enumerate(brief_items):
        validate_item(item, f"brief item {index}")

    status = payloads["source-status.json"]
    require(isinstance(status.get("sites"), list), "source status sites must be a list")
    require(isinstance(status.get("successful_sites"), int), "successful_sites must be integer")

    stories = payloads["stories-merged.json"]
    story_items = stories.get("stories") if isinstance(stories, dict) else None
    require(isinstance(story_items, list), "stories must be a list")
    require(stories.get("total_stories") == len(story_items), "total_stories mismatch")
    for index, item in enumerate(story_items):
        validate_item(item, f"story {index}")

    personas = payloads["top3-personas.json"]
    require(isinstance(personas.get("items"), list), "top3 persona items must be a list")

    waytoagi = payloads["waytoagi-7d.json"]
    require(isinstance(waytoagi.get("updates_7d"), list), "WaytoAGI updates_7d must be a list")


def walk_sensitive(value: Any, path: str = "$", issues: list[str] | None = None) -> list[str]:
    issues = issues if issues is not None else []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = normalize_sensitive_name(str(key))
            if normalized in SENSITIVE_KEY_NAMES and child not in (None, "", False, 0, [], {}):
                issues.append(f"{path}.{key}: sensitive field is populated")
            walk_sensitive(child, f"{path}.{key}", issues)

    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk_sensitive(child, f"{path}[{index}]", issues)
    elif isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                issues.append(f"{path}: secret-like value")
                break
        if value.lstrip().lower().startswith(("http://", "https://")):
            parsed = urlparse(value.strip())

            if parsed.username or parsed.password:
                issues.append(f"{path}: URL contains credentials")
            if parsed.fragment:
                issues.append(f"{path}: URL contains a fragment")
            for key, child in parse_qsl(parsed.query, keep_blank_values=True):
                if normalize_sensitive_name(key) in SENSITIVE_QUERY_KEY_NAMES and child:
                    issues.append(f"{path}: sensitive URL parameter {key}")

    return issues


def validate_quality(
    payloads: dict[str, Any],
    baseline_dir: Path | None,
    max_age_hours: float,
    min_success_ratio: float,
    min_brief_items: int,
    min_latest_items: int,
    max_drop_ratio: float,
) -> None:
    latest = payloads["latest-24h.json"]
    status = payloads["source-status.json"]
    brief = payloads["daily-brief.json"]

    generated_at = parse_time(latest.get("generated_at"))
    if max_age_hours > 0:
        age_hours = (datetime.now(timezone.utc) - generated_at).total_seconds() / 3600
        require(-1 <= age_hours <= max_age_hours, f"snapshot age {age_hours:.1f}h exceeds limit")

    sites = status.get("sites") or []
    require(len(sites) >= 5, "fewer than 5 source adapters reported")
    successful = int(status.get("successful_sites") or 0)
    ratio = successful / len(sites)
    require(ratio >= min_success_ratio, f"source success ratio {ratio:.1%} below threshold")
    require(int(brief.get("total_items") or 0) >= min_brief_items, "daily brief is too small")
    require(int(latest.get("total_items") or 0) >= min_latest_items, "latest AI pool is too small")

    if baseline_dir and (baseline_dir / "latest-24h.json").is_file():
        baseline = load_json(baseline_dir / "latest-24h.json")
        before = int(baseline.get("total_items") or 0)
        after = int(latest.get("total_items") or 0)
        if before > 0:
            drop = max(0.0, (before - after) / before)
            require(drop <= max_drop_ratio, f"latest item count dropped {drop:.1%}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--max-age-hours", type=float, default=0)
    parser.add_argument("--min-success-ratio", type=float, default=0.70)
    parser.add_argument("--min-brief-items", type=int, default=5)
    parser.add_argument("--min-latest-items", type=int, default=20)
    parser.add_argument("--max-drop-ratio", type=float, default=0.70)
    args = parser.parse_args()

    try:
        payloads = {name: load_json(args.data_dir / name) for name in PUBLIC_FILES}
        validate_shapes(payloads)
        validate_quality(
            payloads,
            args.baseline_dir,
            args.max_age_hours,
            args.min_success_ratio,
            args.min_brief_items,
            args.min_latest_items,
            args.max_drop_ratio,
        )
        issues: list[str] = []
        # Scan every candidate JSON, not only the seven public-site files. Internal
        # state is cached between runs and must be safe even though it is not deployed.
        for path in sorted(args.data_dir.glob("*.json")):
            walk_sensitive(load_json(path), path.name, issues)
        if issues:

            raise GateError("sensitive data found:\n- " + "\n- ".join(issues[:30]))
    except GateError as exc:
        print(f"quality gate failed: {exc}", file=sys.stderr)
        return 1

    print(f"quality gate passed: {args.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
