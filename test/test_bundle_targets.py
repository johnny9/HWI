#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).parents[1] / "contrib" / "bundle_targets.py"
SPEC = importlib.util.spec_from_file_location("bundle_targets", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
targets_module = importlib.util.module_from_spec(SPEC)
sys.modules["bundle_targets"] = targets_module
SPEC.loader.exec_module(targets_module)


class BundleTargetsTest(unittest.TestCase):
    def test_target_file_covers_bitcoin_core(self):
        targets = targets_module.load_targets()
        self.assertEqual(
            {target["triple"] for target in targets},
            targets_module.CORE_TARGETS,
        )

    def test_all_linux_targets_enforce_glibc_2_31(self):
        targets = targets_module.load_targets()
        linux = [target for target in targets if target["platform"] == "linux"]
        self.assertEqual(len(linux), 5)
        self.assertTrue(all(target["glibc_maximum"] == "2.31" for target in linux))

    def test_hosted_matrix_has_independent_reproducers(self):
        targets = targets_module.load_targets()
        matrix = targets_module.build_matrix(targets, "macos", ("a", "b"))
        rows = matrix["include"]
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["reproducer"] for row in rows}, {"a", "b"})

    def test_oci_targets_are_native_and_digest_pinned(self):
        targets = targets_module.load_targets()
        oci = [target for target in targets if target["group"] == "linux-oci"]
        self.assertEqual(
            {target["triple"]: target["runner"] for target in oci},
            {
                "x86_64-linux-gnu": "ubuntu-22.04",
                "aarch64-linux-gnu": "ubuntu-22.04-arm",
            },
        )
        self.assertTrue(all(target["builder"] == "oci" for target in oci))
        self.assertTrue(
            all(
                targets_module.OCI_DIGEST_PATTERN.fullmatch(target["oci_image"])
                for target in oci
            )
        )

    def test_emulated_linux_targets_are_not_claimed_as_hosted(self):
        targets = targets_module.load_targets()
        unavailable = {
            target["triple"]
            for target in targets
            if target["group"] == "linux-unavailable"
        }
        self.assertEqual(
            unavailable,
            {"arm-linux-gnueabihf", "riscv64-linux-gnu"},
        )
        self.assertTrue(
            all(
                not target["hosted"]
                for target in targets
                if target["triple"] in unavailable
            )
        )


if __name__ == "__main__":
    unittest.main()
