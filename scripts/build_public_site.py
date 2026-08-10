#!/usr/bin/env python3
"""Build a strict public-site allowlist into dist/."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PUBLIC_DATA_FILES = (
    "latest-24h.json",
    "latest-24h-all.json",
    "daily-brief.json",
    "source-status.json",
    "stories-merged.json",
    "top3-personas.json",
    "waytoagi-7d.json",
)
ROOT_FILES = (
    "index.html",
    "site.webmanifest",
    "privacy.html",
    "content-policy.html",
    "robots.txt",
)
ROOT_DIRS = ("assets",)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()

    root = args.root.resolve()
    data_dir = args.data_dir.resolve()
    output = args.output_dir.resolve()
    if output == root or root in output.parents and output.name in {"assets", "data"}:
        raise SystemExit("refusing unsafe output directory")

    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    for name in ROOT_FILES:
        source = root / name
        if not source.is_file():
            raise SystemExit(f"missing public file: {source}")
        shutil.copy2(source, output / name)
    for name in ROOT_DIRS:
        source = root / name
        if not source.is_dir():
            raise SystemExit(f"missing public directory: {source}")
        shutil.copytree(source, output / name)

    public_data = output / "data"
    public_data.mkdir()
    for name in PUBLIC_DATA_FILES:
        source = data_dir / name
        if not source.is_file():
            raise SystemExit(f"missing public data: {source}")
        shutil.copy2(source, public_data / name)

    print(f"built public site: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
