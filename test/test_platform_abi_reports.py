#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest


CONTRIB = Path(__file__).parents[1] / "contrib"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CONTRIB / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


macos_module = load_module("macos_abi_report", "macos_abi_report.py")
windows_module = load_module("windows_abi_report", "windows_abi_report.py")


class PlatformAbiReportsTest(unittest.TestCase):
    def test_macos_load_command_versions_are_parsed_per_line(self):
        load_commands = """
Load command 10
      cmd LC_BUILD_VERSION
    minos 14.0
Load command 11
      cmd LC_VERSION_MIN_MACOSX
  version 11.0
"""
        self.assertEqual(
            macos_module.minimum_versions(load_commands),
            ["14.0", "11.0"],
        )

    def test_macos_ignores_non_deployment_versions(self):
        load_commands = """
Load command 1
      cmd LC_ID_DYLIB
  current version 1167.5.0
Load command 2
      cmd LC_BUILD_VERSION
    minos 14.0
"""
        self.assertEqual(macos_module.minimum_versions(load_commands), ["14.0"])

    def test_macos_validation_accepts_core_deployment_target(self):
        report = {
            "macho_files": [
                {
                    "architecture": "arm64",
                    "minimum_macos_versions": ["11.0", "14.0"],
                    "path": "hwi",
                }
            ],
            "maximum_minimum_macos": "14.0",
        }
        macos_module.validate_report(report, "arm64", "14.0")

    def test_macos_validation_rejects_newer_target(self):
        report = {
            "macho_files": [
                {
                    "architecture": "x86_64",
                    "minimum_macos_versions": ["15.0"],
                    "path": "hwi",
                }
            ],
            "maximum_minimum_macos": "15.0",
        }
        with self.assertRaisesRegex(ValueError, "exceeds 14.0"):
            macos_module.validate_report(report, "x86_64", "14.0")

    def test_pe_parser_records_machine_and_subsystem(self):
        data = bytearray(512)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", data, 0x84, 0x8664)
        struct.pack_into("<H", data, 0x98, 0x20B)
        struct.pack_into("<HH", data, 0x98 + 48, 6, 2)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            binary = root / "hwi.exe"
            binary.write_bytes(data)
            entry = windows_module.inspect_pe(binary, root)
        assert entry is not None
        self.assertEqual(entry["machine"], "x86_64")
        self.assertEqual(entry["subsystem_version"], "6.2")


if __name__ == "__main__":
    unittest.main()
