#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
"""Validate bundle targets and emit GitHub Actions build matrices."""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


TARGETS_PATH = Path(__file__).with_name("bundle-targets.json")
CORE_TARGETS = {
    "aarch64-linux-gnu",
    "arm-linux-gnueabihf",
    "arm64-apple-darwin",
    "powerpc64-linux-gnu",
    "riscv64-linux-gnu",
    "x86_64-apple-darwin",
    "x86_64-linux-gnu",
    "x86_64-w64-mingw32",
}


def load_targets(path: Path = TARGETS_PATH) -> List[Dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf8"))
    if document.get("format") != 1 or not isinstance(document.get("targets"), list):
        raise ValueError("unsupported bundle target document")
    targets = document["targets"]
    validate_targets(targets)
    return targets


def require_fields(target: Dict[str, Any], fields: Iterable[str]) -> None:
    missing = sorted(field for field in fields if field not in target)
    if missing:
        raise ValueError(f"{target.get('triple', '<unknown>')}: missing {', '.join(missing)}")


def validate_targets(targets: List[Dict[str, Any]]) -> None:
    triples = [target.get("triple") for target in targets]
    if len(triples) != len(set(triples)):
        raise ValueError("bundle target triples must be unique")
    if set(triples) != CORE_TARGETS:
        missing = sorted(CORE_TARGETS - set(triples))
        extra = sorted(set(triples) - CORE_TARGETS)
        raise ValueError(f"bundle target set differs from Bitcoin Core: missing={missing}, extra={extra}")

    common = ("architecture", "builder", "group", "hosted", "platform", "runner", "triple")
    linux = common + (
        "endianness",
        "expected_interpreter",
        "glibc_maximum",
        "machine",
    )
    for target in targets:
        require_fields(target, linux if target.get("platform") == "linux" else common)
        if target.get("platform") == "linux" and target["glibc_maximum"] != "2.31":
            raise ValueError(f"{target['triple']}: Linux GLIBC maximum must be 2.31")
        if target["group"] == "linux-guix":
            require_fields(target, ("guix_system",))


def build_matrix(
    targets: List[Dict[str, Any]],
    group: str,
    reproducers: Iterable[str],
) -> Dict[str, Any]:
    rows = []
    for target in targets:
        if target["group"] != group or not target["hosted"]:
            continue
        for reproducer in reproducers:
            row = dict(target)
            row["reproducer"] = reproducer
            rows.append(row)
    if not rows:
        raise ValueError(f"no hosted targets in group: {group}")
    return {"include": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", choices=("linux-guix", "macos", "windows"))
    parser.add_argument("--reproducers", default="a,b")
    args = parser.parse_args()

    targets = load_targets()
    if args.matrix:
        reproducers = [item for item in args.reproducers.split(",") if item]
        if not reproducers:
            raise ValueError("at least one reproducer is required")
        print(json.dumps(build_matrix(targets, args.matrix, reproducers), separators=(",", ":")))
    else:
        print(f"validated {len(targets)} Bitcoin Core bundle targets")


if __name__ == "__main__":
    main()
