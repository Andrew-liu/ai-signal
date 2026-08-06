#!/usr/bin/env python3
"""Atomically promote a validated candidate snapshot to data/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.safe_io import atomic_write_json
except ModuleNotFoundError:
    from safe_io import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, default=Path("data"))
    parser.add_argument("--publish-email-digest", action="store_true")
    args = parser.parse_args()

    args.target_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(args.candidate_dir.glob("*.json"))
    if not files:
        raise SystemExit("candidate directory contains no JSON")
    for source in files:
        if source.name == "email-digest.json" and not args.publish_email_digest:
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        compact = source.name in {
            "archive.json", "latest-24h-all.json", "latest-24h-all-raw.json", "stories-merged.json"
        }
        atomic_write_json(args.target_dir / source.name, payload, indent=None if compact else 2, compact=compact)
    print(f"promoted {len(files)} candidate JSON files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
