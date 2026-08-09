#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
"""Validate PE architecture and subsystem versions in a bundle tree."""

import argparse
import json
from pathlib import Path
import struct
from typing import Any, Dict, List, Optional


PE_MACHINES = {
    0x8664: "x86_64",
}


def inspect_pe(path: Path, root: Path) -> Optional[Dict[str, Any]]:
    data = path.read_bytes()
    if len(data) < 64 or data[:2] != b"MZ":
        return None
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"invalid PE header: {path}")
    machine_value = struct.unpack_from("<H", data, pe_offset + 4)[0]
    machine = PE_MACHINES.get(machine_value)
    if machine is None:
        raise ValueError(f"unsupported PE machine 0x{machine_value:04x}: {path}")
    optional_offset = pe_offset + 24
    if optional_offset + 52 > len(data):
        raise ValueError(f"truncated PE optional header: {path}")
    magic = struct.unpack_from("<H", data, optional_offset)[0]
    if magic != 0x20B:
        raise ValueError(f"expected PE32+ optional header: {path}")
    subsystem = struct.unpack_from("<HH", data, optional_offset + 48)
    return {
        "machine": machine,
        "path": path.relative_to(root).as_posix(),
        "subsystem_version": f"{subsystem[0]}.{subsystem[1]}",
    }


def build_report(root: Path) -> Dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"artifact tree does not exist: {root}")
    entries: List[Dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        entry = inspect_pe(path, root)
        if entry is not None:
            entries.append(entry)
    if not entries:
        raise RuntimeError("artifact tree contains no PE files")
    return {"format": 1, "pe_files": entries}


def validate_report(report: Dict[str, Any], architecture: str) -> None:
    errors = [
        f"{entry['path']}: machine {entry['machine']} != {architecture}"
        for entry in report["pe_files"]
        if entry["machine"] != architecture
    ]
    if errors:
        raise ValueError("\n".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--architecture", default="x86_64")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = build_report(args.root)
    validate_report(report, args.architecture)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    print(f"validated {len(report['pe_files'])} {args.architecture} PE files")


if __name__ == "__main__":
    main()
