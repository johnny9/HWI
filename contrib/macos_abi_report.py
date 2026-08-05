#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
"""Validate Mach-O architecture and deployment targets in a bundle tree."""

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List


VERSION_PATTERN = re.compile(r"^(?:minos|version)\s+(\d+(?:\.\d+)+)$")
VERSION_COMMANDS = {"LC_BUILD_VERSION", "LC_VERSION_MIN_MACOSX"}


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def minimum_versions(load_commands: str) -> List[str]:
    versions = []
    version_command = False
    for line in load_commands.splitlines():
        stripped = line.strip()
        if stripped.startswith("cmd "):
            version_command = stripped.removeprefix("cmd ") in VERSION_COMMANDS
            continue
        if not version_command:
            continue
        match = VERSION_PATTERN.match(stripped)
        if match:
            versions.append(match.group(1))
            version_command = False
    return versions


def inspect_macho(path: Path, root: Path, description: str) -> Dict[str, Any]:
    load_commands = subprocess.run(
        ["otool", "-l", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if "arm64" in description:
        architecture = "arm64"
    elif "x86_64" in description:
        architecture = "x86_64"
    else:
        raise RuntimeError(f"unsupported Mach-O architecture in {path}: {description}")
    minimum_macos_versions = sorted(
        set(minimum_versions(load_commands)),
        key=version_key,
    )
    return {
        "architecture": architecture,
        "minimum_macos_versions": minimum_macos_versions,
        "path": path.relative_to(root).as_posix(),
    }


def build_report(root: Path) -> Dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"artifact tree does not exist: {root}")
    entries: List[Dict[str, Any]] = []
    versions = set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        description = subprocess.run(
            ["file", "-b", str(path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if "Mach-O" not in description:
            continue
        entry = inspect_macho(path, root, description)
        entries.append(entry)
        versions.update(entry["minimum_macos_versions"])
    if not entries:
        raise RuntimeError("artifact tree contains no Mach-O files")
    ordered = sorted(versions, key=version_key)
    return {
        "format": 1,
        "macho_files": entries,
        "maximum_minimum_macos": ordered[-1] if ordered else None,
    }


def validate_report(report: Dict[str, Any], architecture: str, maximum_macos: str) -> None:
    errors = []
    for entry in report["macho_files"]:
        if entry["architecture"] != architecture:
            errors.append(
                f"{entry['path']}: architecture {entry['architecture']} != {architecture}"
            )
    actual = report["maximum_minimum_macos"]
    if actual is None:
        errors.append("Mach-O files contain no macOS deployment version")
    elif version_key(actual) > version_key(maximum_macos):
        errors.append(f"minimum macOS {actual} exceeds {maximum_macos}")
    if errors:
        raise ValueError("\n".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--architecture", choices=("arm64", "x86_64"), required=True)
    parser.add_argument("--maximum-macos", default="14.0")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = build_report(args.root)
    validate_report(report, args.architecture, args.maximum_macos)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    print(
        f"validated {args.architecture} Mach-O, maximum deployment target: "
        f"{report['maximum_minimum_macos']}"
    )


if __name__ == "__main__":
    main()
