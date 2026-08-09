#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "contrib" / "linux_abi_report.py"
SPEC = importlib.util.spec_from_file_location("linux_abi_report", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
abi_module = importlib.util.module_from_spec(SPEC)
sys.modules["linux_abi_report"] = abi_module
SPEC.loader.exec_module(abi_module)


class Completed:
    def __init__(self, stdout):
        self.stdout = stdout


class LinuxAbiReportTest(unittest.TestCase):
    def test_inspection_records_core_elf_contract(self):
        outputs = {
            "--file-header": """
  Class:                             ELF64
  Data:                              2's complement, little endian
  Machine:                           Advanced Micro Devices X86-64
""",
            "--program-headers": "[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]",
            "--notes": "OS: Linux, ABI: 3.2.0",
            "--version-info": "Name: GLIBC_2.17\nName: GLIBC_2.31",
            "--dynamic": "(NEEDED) Shared library: [libc.so.6]",
        }

        def fake_run(command, **_kwargs):
            return Completed(outputs[command[1]])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            binary = root / "hwi"
            binary.write_bytes(b"elf")
            with patch.object(abi_module.subprocess, "run", side_effect=fake_run):
                entry = abi_module.inspect_elf(binary, root)

        self.assertEqual(entry["machine"], "x86_64")
        self.assertEqual(entry["endianness"], "little")
        self.assertEqual(entry["abi"], "3.2.0")
        self.assertEqual(entry["interpreter"], "/lib64/ld-linux-x86-64.so.2")
        self.assertEqual(entry["glibc_versions"], ["2.17", "2.31"])
        self.assertEqual(entry["needed"], ["libc.so.6"])

    def test_validation_accepts_bitcoin_core_baseline(self):
        report = {
            "elf_files": [
                {
                    "path": "hwi",
                    "machine": "riscv64",
                    "endianness": "little",
                    "interpreter": "/lib/ld-linux-riscv64-lp64d.so.1",
                }
            ],
            "maximum_glibc": "2.31",
        }
        abi_module.validate_report(
            report,
            "riscv64",
            "little",
            "/lib/ld-linux-riscv64-lp64d.so.1",
            "2.31",
        )

    def test_validation_rejects_wrong_architecture_and_newer_glibc(self):
        report = {
            "elf_files": [
                {
                    "path": "hwi",
                    "machine": "x86_64",
                    "endianness": "little",
                    "interpreter": "/lib64/ld-linux-x86-64.so.2",
                }
            ],
            "maximum_glibc": "2.35",
        }
        with self.assertRaisesRegex(ValueError, "machine x86_64 != aarch64"):
            abi_module.validate_report(
                report,
                "aarch64",
                "little",
                "/lib/ld-linux-aarch64.so.1",
                "2.31",
            )


if __name__ == "__main__":
    unittest.main()
