#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "contrib" / "generate_bundle_manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_bundle_manifest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
manifest_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_module)


class BundleManifestTest(unittest.TestCase):
    def test_manifest_is_canonical_and_complete(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = Path(temporary_directory)
            (bundle / "_internal").mkdir()
            (bundle / "hwi").write_bytes(b"executable")
            (bundle / "_internal" / "module.pyz").write_bytes(b"module")

            manifest = manifest_module.build_manifest(bundle, "linux", "x86_64")
            encoded = manifest_module.canonical_json(manifest)

            self.assertEqual(encoded, manifest_module.canonical_json(json.loads(encoded)))
            self.assertEqual(
                [entry["path"] for entry in manifest["files"]],
                ["_internal/module.pyz", "hwi"],
            )
            self.assertEqual(manifest["entrypoint"], "hwi")
            self.assertEqual(manifest["hwi_version"], "3.2.0")

            (bundle / manifest_module.MANIFEST_NAME).write_bytes(encoded)
            (bundle / manifest_module.SIGNATURE_NAME).write_text("signature\n")
            regenerated = manifest_module.build_manifest(bundle, "linux", "x86_64")
            self.assertEqual(manifest, regenerated)

    def test_internal_symlink_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = Path(temporary_directory)
            (bundle / "hwi").write_bytes(b"executable")
            (bundle / "alias").symlink_to("hwi")

            manifest = manifest_module.build_manifest(bundle, "linux", "x86_64")
            alias = next(entry for entry in manifest["files"] if entry["path"] == "alias")
            self.assertEqual(alias, {"path": "alias", "target": "hwi", "type": "symlink"})

    def test_escaping_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            bundle = temporary_path / "bundle"
            bundle.mkdir()
            (bundle / "hwi").write_bytes(b"executable")
            (temporary_path / "outside").write_bytes(b"outside")
            (bundle / "alias").symlink_to("../outside")

            with self.assertRaisesRegex(ValueError, "escapes bundle"):
                manifest_module.build_manifest(bundle, "linux", "x86_64")

    def test_absolute_and_broken_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = Path(temporary_directory)
            (bundle / "hwi").write_bytes(b"executable")
            (bundle / "absolute").symlink_to("/tmp/outside")
            with self.assertRaisesRegex(ValueError, "must be relative"):
                manifest_module.build_manifest(bundle, "linux", "x86_64")

            (bundle / "absolute").unlink()
            (bundle / "broken").symlink_to("missing")
            with self.assertRaisesRegex(ValueError, "is invalid"):
                manifest_module.build_manifest(bundle, "linux", "x86_64")

    def test_entrypoint_must_be_a_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = Path(temporary_directory)
            (bundle / "target").write_bytes(b"executable")
            (bundle / "hwi").symlink_to("target")
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                manifest_module.build_manifest(bundle, "linux", "x86_64")

    def test_empty_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = Path(temporary_directory)
            (bundle / "hwi").write_bytes(b"executable")
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                manifest_module.build_manifest(bundle, "linux", "x86_64", "")

    def test_windows_uses_exe_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = Path(temporary_directory)
            (bundle / "hwi.exe").write_bytes(b"executable")
            manifest = manifest_module.build_manifest(bundle, "windows", "x86_64")
            self.assertEqual(manifest["entrypoint"], "hwi.exe")


if __name__ == "__main__":
    unittest.main()
