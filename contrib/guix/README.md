# Reproducible HWI sidecar builds

The Guix package in this directory is the authoritative Linux x86_64 sidecar
builder. It pins the complete Guix package universe, obtains Python packages
from Guix rather than Poetry or PyPI during the build, compiles the PyInstaller
bootloader from source, creates the unsigned canonical HWI manifest, and emits
a normalized archive. The complete package graph is rewritten to Guix's pinned
glibc 2.35 variant so a rolling Guix libc cannot silently raise the runtime ABI
requirement.

Run it from a clean HWI checkout with a working Guix daemon:

```sh
contrib/guix/build-sidecar
```

To rebuild all inputs rather than accepting signed substitutes:

```sh
HWI_GUIX_BUILD_FLAGS=--no-substitutes contrib/guix/build-sidecar
```

The output and its SHA256 file are written under `dist/guix`. Private release
keys are deliberately absent from this build. Maintainers must reproduce the
unsigned archive before the protected release process authorizes its canonical
manifest and assembles the final release archive.

## Target status

| Bitcoin Core target | Sidecar builder | Native or emulated runtime needed |
|---|---|---|
| `x86_64-linux-gnu` | Implemented with Guix | x86_64 Linux |
| `arm-linux-gnueabihf` | Not implemented | ARMv7 Linux or full-system QEMU |
| `aarch64-linux-gnu` | Not implemented | ARM64 Linux or full-system QEMU |
| `riscv64-linux-gnu` | Not implemented | RISC-V Linux or full-system QEMU |
| `powerpc64-linux-gnu` | Not implemented | Big-endian POWER Linux or full-system QEMU |
| `x86_64-w64-mingw32` | Not implemented for the sidecar | Windows x64 or the existing Wine environment |
| `x86_64-apple-darwin` | Not implemented | Intel macOS or a complete universal2 environment |
| `arm64-apple-darwin` | Determinism CI only | Apple-silicon macOS |

PyInstaller is not a cross-compiler. Adding a Guix cross toolchain alone is not
enough for the non-native targets: the target Python interpreter, extension
modules, PyInstaller bootloader, collection pass, and runtime test must all be
executed in the corresponding target environment.

The macOS CI lane therefore checks deterministic native assembly separately.
Official Developer ID signatures and notarization are applied only after the
unsigned tree reproduces. Those Apple-authorized final bytes are verified by
signature and manifest rather than expected to reproduce bit-for-bit.
