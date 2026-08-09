#!/usr/bin/env python3
# Copyright (c) 2026 The HWI developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
"""Validate the ELF architecture and GLIBC requirements of a bundle tree."""

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List


GLIBC_PATTERN = re.compile(r"GLIBC_(\d+(?:\.\d+)+)")
NEEDED_PATTERN = re.compile(r"\(NEEDED\).*\[(.+)]")
MACHINE_PATTERN = re.compile(r"^\s*Machine:\s*(.+?)\s*$", re.MULTILINE)
INTERPRETER_PATTERN = re.compile(r"Requesting program interpreter:\s*([^]]+)")
ABI_PATTERN = re.compile(r"OS:\s*Linux,\s*ABI:\s*(\d+(?:\.\d+)+)")

READELF_MACHINES = {
    "AArch64": "aarch64",
    "Advanced Micro Devices X86-64": "x86_64",
    "ARM": "arm",
    "PowerPC64": "powerpc64",
    "RISC-V": "riscv64",
}


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def is_elf(path: Path) -> bool:
    result = subprocess.run(
        ["file", "-b", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return "ELF" in result.stdout


def inspect_elf(path: Path, root: Path) -> Dict[str, Any]:
    header = subprocess.run(
        ["readelf", "--file-header", "--wide", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    program_headers = subprocess.run(
        ["readelf", "--program-headers", "--wide", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    notes = subprocess.run(
        ["readelf", "--notes", "--wide", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    versions = subprocess.run(
        ["readelf", "--version-info", "--wide", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    dynamic = subprocess.run(
        ["readelf", "--dynamic", "--wide", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    machine_match = MACHINE_PATTERN.search(header)
    if machine_match is None or machine_match.group(1) not in READELF_MACHINES:
        raise RuntimeError(f"unsupported ELF machine in {path}")
    if "little endian" in header:
        endianness = "little"
    elif "big endian" in header:
        endianness = "big"
    else:
        raise RuntimeError(f"unknown ELF endianness in {path}")
    interpreter_match = INTERPRETER_PATTERN.search(program_headers)
    abi_match = ABI_PATTERN.search(notes)
    glibc = sorted(set(GLIBC_PATTERN.findall(versions)), key=version_key)
    needed = sorted(set(NEEDED_PATTERN.findall(dynamic)))
    return {
        "abi": abi_match.group(1) if abi_match else None,
        "endianness": endianness,
        "glibc_versions": glibc,
        "interpreter": interpreter_match.group(1) if interpreter_match else None,
        "machine": READELF_MACHINES[machine_match.group(1)],
        "needed": needed,
        "path": path.relative_to(root).as_posix(),
    }


def build_report(root: Path) -> Dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"artifact tree does not exist: {root}")
    entries: List[Dict[str, Any]] = []
    all_versions = set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or not is_elf(path):
            continue
        entry = inspect_elf(path, root)
        entries.append(entry)
        all_versions.update(entry["glibc_versions"])
    if not entries:
        raise RuntimeError("artifact tree contains no ELF files")
    ordered_versions = sorted(all_versions, key=version_key)
    return {
        "elf_files": entries,
        "format": 2,
        "maximum_glibc": ordered_versions[-1] if ordered_versions else None,
    }


def validate_report(
    report: Dict[str, Any],
    expected_machine: str,
    expected_endianness: str,
    expected_interpreter: str,
    maximum_glibc: str,
) -> None:
    errors = []
    interpreters = []
    for entry in report["elf_files"]:
        if entry["machine"] != expected_machine:
            errors.append(
                f"{entry['path']}: machine {entry['machine']} != {expected_machine}"
            )
        if entry["endianness"] != expected_endianness:
            errors.append(
                f"{entry['path']}: endianness {entry['endianness']} != "
                f"{expected_endianness}"
            )
        if entry["interpreter"] is not None:
            interpreters.append(entry["interpreter"])
            if entry["interpreter"] != expected_interpreter:
                errors.append(
                    f"{entry['path']}: interpreter {entry['interpreter']} != "
                    f"{expected_interpreter}"
                )

    if not interpreters:
        errors.append("artifact tree contains no dynamically linked ELF executable")
    actual_glibc = report["maximum_glibc"]
    if actual_glibc is None:
        errors.append("artifact tree has no GLIBC symbol requirements")
    elif version_key(actual_glibc) > version_key(maximum_glibc):
        errors.append(f"maximum GLIBC {actual_glibc} exceeds {maximum_glibc}")

    if errors:
        raise ValueError("\n".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-machine", required=True)
    parser.add_argument(
        "--expected-endianness",
        choices=("big", "little"),
        required=True,
    )
    parser.add_argument("--expected-interpreter", required=True)
    parser.add_argument("--maximum-glibc", default="2.31")
    args = parser.parse_args()

    report = build_report(args.root)
    validate_report(
        report,
        args.expected_machine,
        args.expected_endianness,
        args.expected_interpreter,
        args.maximum_glibc,
    )
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    print(
        f"validated {args.expected_machine} {args.expected_endianness}-endian ELF, "
        f"maximum GLIBC requirement: {report['maximum_glibc']}"
    )


if __name__ == "__main__":
    main()
