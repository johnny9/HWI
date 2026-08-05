#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

import importlib.util
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest


CONTRIB = Path(__file__).parents[1] / "contrib"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


manifest_module = load_module(
    "generate_sidecar_manifest",
    CONTRIB / "generate_sidecar_manifest.py",
)
package_module = load_module("package_sidecar", CONTRIB / "package_sidecar.py")


class SidecarArchiveTest(unittest.TestCase):
    def make_bundle(self, directory: Path) -> Path:
        bundle = directory / "bundle"
        (bundle / "_internal").mkdir(parents=True)
        (bundle / "hwi").write_bytes(b"executable")
        (bundle / "hwi").chmod(0o755)
        (bundle / "_internal" / "module.pyz").write_bytes(b"module")
        (bundle / "module-link").symlink_to("_internal/module.pyz")
        manifest = manifest_module.build_manifest(bundle, "linux", "x86_64")
        (bundle / manifest_module.MANIFEST_NAME).write_bytes(
            manifest_module.canonical_json(manifest)
        )
        return bundle

    def test_archive_is_reproducible_and_normalized(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bundle = self.make_bundle(root)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            epoch = 1_546_300_800

            package_module.package_bundle(bundle, first, epoch)
            for index, path in enumerate(bundle.rglob("*"), start=1):
                if not path.is_symlink():
                    os.utime(path, (epoch + index, epoch + index))
            package_module.package_bundle(bundle, second, epoch)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as archive:
                members = archive.getmembers()
                self.assertEqual(
                    [member.name for member in members],
                    [
                        "hwi",
                        "hwi/_internal",
                        "hwi/_internal/module.pyz",
                        "hwi/hwi",
                        "hwi/hwi-manifest.json",
                        "hwi/module-link",
                    ],
                )
                self.assertTrue(all(member.uid == 0 and member.gid == 0 for member in members))
                self.assertTrue(all(member.mtime == epoch for member in members))
                self.assertEqual(archive.getmember("hwi/hwi").mode, 0o755)
                self.assertEqual(archive.getmember("hwi/_internal/module.pyz").mode, 0o644)
                self.assertTrue(archive.getmember("hwi/module-link").issym())
                self.assertEqual(archive.getmember("hwi/module-link").linkname, "_internal/module.pyz")

    def test_manifest_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bundle = self.make_bundle(root)
            (bundle / "_internal" / "module.pyz").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "do not match"):
                package_module.package_bundle(bundle, root / "out.tar.gz", 0)

    def test_non_executable_entrypoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bundle = self.make_bundle(root)
            (bundle / "hwi").chmod(0o644)
            with self.assertRaisesRegex(ValueError, "not executable"):
                package_module.package_bundle(bundle, root / "out.tar.gz", 0)


if __name__ == "__main__":
    unittest.main()
