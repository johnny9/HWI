#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
"""Compare two canonical HWI sidecar archives and identify every mismatch."""

import argparse
import hashlib
import os
from pathlib import Path
import tarfile
from typing import Dict, List, Optional, Tuple


Member = Tuple[tarfile.TarInfo, Optional[bytes]]
METADATA_FIELDS = (
    "gid",
    "gname",
    "linkname",
    "mode",
    "mtime",
    "size",
    "type",
    "uid",
    "uname",
)


def sha256_bytes(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def read_archive(path: Path) -> Dict[str, Member]:
    members: Dict[str, Member] = {}
    with tarfile.open(path, "r:gz") as archive:
        for info in archive.getmembers():
            if info.name in members:
                raise ValueError(f"duplicate archive member: {info.name}")
            extracted = archive.extractfile(info) if info.isreg() else None
            contents = extracted.read() if extracted is not None else None
            members[info.name] = (info, contents)
    return members


def compare_archives(first: Path, second: Path) -> List[str]:
    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    if first_bytes == second_bytes:
        return []

    differences: List[str] = []
    first_members = read_archive(first)
    second_members = read_archive(second)
    for name in sorted(first_members.keys() | second_members.keys()):
        if name not in first_members:
            differences.append(f"only in {second.name}: {name}")
            continue
        if name not in second_members:
            differences.append(f"only in {first.name}: {name}")
            continue

        first_info, first_contents = first_members[name]
        second_info, second_contents = second_members[name]
        for field in METADATA_FIELDS:
            first_value = getattr(first_info, field)
            second_value = getattr(second_info, field)
            if first_value != second_value:
                differences.append(
                    f"metadata differs for {name}: {field} "
                    f"{first_value!r} != {second_value!r}"
                )
        if first_contents != second_contents:
            if first_contents is None or second_contents is None:
                differences.append(f"archive entry kind differs for {name}")
            else:
                differences.append(
                    f"content differs for {name}: "
                    f"{sha256_bytes(first_contents)} != "
                    f"{sha256_bytes(second_contents)}"
                )

    if not differences:
        differences.append("gzip bytes differ but uncompressed archives match")
    return differences


def github_escape(message: str) -> str:
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()

    differences = compare_archives(args.first, args.second)
    if not differences:
        print(f"archives match: {sha256_bytes(args.first.read_bytes())}")
        return

    for difference in differences[:50]:
        print(difference)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(
                "::error title=Sidecar archive mismatch::"
                f"{github_escape(difference)}"
            )
    if len(differences) > 50:
        print(f"... and {len(differences) - 50} additional differences")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
