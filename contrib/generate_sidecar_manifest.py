#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
"""Generate the canonical file manifest for an HWI sidecar directory."""

import argparse
import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Dict, List

from hwilib import __version__ as HWI_VERSION


MANIFEST_NAME = "hwi-manifest.json"
SIGNATURE_NAME = "hwi-manifest.sig"
EXCLUDED_NAMES = {MANIFEST_NAME, SIGNATURE_NAME}
ENTRYPOINT = "hwi"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_manifest(
    bundle_dir: Path,
    target_platform: str,
    architecture: str,
    hwi_version: str = HWI_VERSION,
) -> Dict[str, Any]:
    if not bundle_dir.is_dir():
        raise ValueError(f"sidecar directory does not exist: {bundle_dir}")
    if not hwi_version:
        raise ValueError("HWI version must not be empty")
    entrypoint = bundle_dir / ENTRYPOINT
    if entrypoint.is_symlink() or not entrypoint.is_file():
        raise ValueError(f"sidecar executable is missing or unsafe: {entrypoint}")

    files: List[Dict[str, Any]] = []
    resolved_bundle = bundle_dir.resolve()
    paths = sorted(bundle_dir.rglob("*"), key=lambda path: path.relative_to(bundle_dir).as_posix())
    for path in paths:
        relative = path.relative_to(bundle_dir)
        relative_name = relative.as_posix()
        if path.is_symlink():
            target = path.readlink()
            if target.is_absolute():
                raise ValueError(f"sidecar symlink target must be relative: {relative_name}")
            try:
                resolved_target = path.resolve(strict=True)
            except (FileNotFoundError, RuntimeError) as error:
                raise ValueError(f"sidecar symlink target is invalid: {relative_name}") from error
            if not resolved_target.is_relative_to(resolved_bundle):
                raise ValueError(f"sidecar symlink escapes bundle: {relative_name}")
            files.append(
                {
                    "path": relative_name,
                    "target": target.as_posix(),
                    "type": "symlink",
                }
            )
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"unsupported sidecar entry: {relative_name}")
        if relative_name in EXCLUDED_NAMES:
            continue
        files.append(
            {
                "path": relative_name,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
                "type": "file",
            }
        )

    return {
        "architecture": architecture,
        "entrypoint": ENTRYPOINT,
        "files": files,
        "format": 1,
        "hwi_version": hwi_version,
        "platform": target_platform,
    }


def canonical_json(manifest: Dict[str, Any]) -> bytes:
    return (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument(
        "--platform",
        default={"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower()),
        dest="target_platform",
    )
    parser.add_argument("--architecture", default=platform.machine().lower())
    args = parser.parse_args()

    manifest = build_manifest(args.bundle_dir, args.target_platform, args.architecture)
    output_path = args.bundle_dir / MANIFEST_NAME
    output_path.write_bytes(canonical_json(manifest))
    print(output_path)


if __name__ == "__main__":
    main()
