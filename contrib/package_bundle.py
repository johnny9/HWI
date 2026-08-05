#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
"""Create a canonical tar.gz archive from a manifested HWI bundle tree."""

import argparse
import gzip
import json
import os
import stat
import tarfile
from pathlib import Path
from typing import Any, Dict, Iterator

from generate_bundle_manifest import MANIFEST_NAME, build_manifest, canonical_json


ARCHIVE_ROOT = Path("hwi")


def verify_manifest(bundle_dir: Path) -> Dict[str, Any]:
    manifest_path = bundle_dir / MANIFEST_NAME
    try:
        encoded = manifest_path.read_bytes()
        manifest = json.loads(encoded)
        expected = build_manifest(
            bundle_dir,
            manifest["platform"],
            manifest["architecture"],
            manifest["hwi_version"],
        )
    except (KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid bundle manifest: {manifest_path}") from error

    if encoded != canonical_json(expected):
        raise ValueError("bundle contents do not match the canonical manifest")

    entrypoint = bundle_dir / manifest["entrypoint"]
    if manifest["platform"] != "windows" and not entrypoint.stat().st_mode & stat.S_IXUSR:
        raise ValueError(f"bundle entry point is not executable: {entrypoint}")
    return manifest


def iter_entries(bundle_dir: Path) -> Iterator[Path]:
    yield bundle_dir
    yield from sorted(
        bundle_dir.rglob("*"),
        key=lambda path: path.relative_to(bundle_dir).as_posix(),
    )


def normalized_mode(path: Path, force_executable: bool = False) -> int:
    mode = path.lstat().st_mode
    if stat.S_ISDIR(mode):
        return 0o755
    if stat.S_ISLNK(mode):
        return 0o777
    if stat.S_ISREG(mode):
        return 0o755 if force_executable or mode & 0o111 else 0o644
    raise ValueError(f"unsupported bundle archive entry: {path}")


def package_bundle(bundle_dir: Path, output: Path, source_date_epoch: int) -> None:
    bundle_dir = bundle_dir.resolve(strict=True)
    if source_date_epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must not be negative")
    manifest = verify_manifest(bundle_dir)
    entrypoint = bundle_dir / manifest["entrypoint"]

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(f".{output.name}.tmp")
    try:
        with temporary_output.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw_output,
                mtime=source_date_epoch,
            ) as gzip_output:
                with tarfile.open(
                    fileobj=gzip_output,
                    mode="w",
                    format=tarfile.GNU_FORMAT,
                ) as archive:
                    for path in iter_entries(bundle_dir):
                        relative = path.relative_to(bundle_dir)
                        archive_name = ARCHIVE_ROOT / relative
                        info = archive.gettarinfo(str(path), archive_name.as_posix())
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mtime = source_date_epoch
                        info.mode = normalized_mode(path, path == entrypoint)
                        if info.isreg():
                            with path.open("rb") as source:
                                archive.addfile(info, source)
                        else:
                            archive.addfile(info)
        os.chmod(temporary_output, 0o644)
        temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "1546300800")),
    )
    args = parser.parse_args()
    package_bundle(args.bundle_dir, args.output, args.source_date_epoch)
    print(args.output)


if __name__ == "__main__":
    main()
