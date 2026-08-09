# -*- mode: python ; coding: utf-8 -*-
"""Headless, one-directory HWI bundle for embedding in another application."""

import os
import platform


libusb_path = os.environ.get("HWI_LIBUSB_PATH")
if not libusb_path:
    raise RuntimeError("HWI_LIBUSB_PATH must name the target libusb shared library")
if not os.path.isfile(libusb_path):
    raise RuntimeError(f"HWI_LIBUSB_PATH does not exist: {libusb_path}")
if platform.system() not in {"Linux", "Darwin", "Windows"}:
    raise RuntimeError("The HWI bundle supports Linux, macOS, and Windows")

datas = []
if platform.system() == "Linux":
    datas.append(("hwilib/udev", "hwilib/udev"))
strip_binaries = platform.system() != "Windows"

a = Analysis(
    ["hwi.py"],
    binaries=[(libusb_path, ".")],
    datas=datas,
    hiddenimports=[],
    hookspath=["contrib/pyinstaller-hooks/"],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hwi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=strip_binaries,
    upx=False,
    console=True,
)

bundle = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=strip_binaries,
    upx=False,
    name="hwi",
)
