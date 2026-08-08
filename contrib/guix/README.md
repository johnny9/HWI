# Reproducible HWI bundle builds

HWI owns the bundle artifacts. Bitcoin Core consumes a released archive only
after checking its pinned archive hash, canonical manifest, and maintainer
signature. Private release keys are deliberately absent from these builders.

`bundle-targets.json` is the target contract shared with CI. It lists every
target shipped by Bitcoin Core, the native or emulated execution environment,
and the ABI values that must be measured from the finished bundle. CI builds
each hosted target twice and accepts it only when the canonical archives are
byte-for-byte identical.

## Linux and Guix

The Guix package pins the complete package universe, obtains Python packages
from Guix rather than PyPI during the build, compiles the PyInstaller
bootloader from source, and creates the normalized unsigned archive. The
launcher is rewritten to the target's conventional ELF interpreter and an
`$ORIGIN/_internal` runpath before it is manifested. Its package graph is
rewritten to the same glibc 2.31 source and patches used by Bitcoin Core. The
runtime probe executes the installed launcher with that pinned glibc's store
loader, then restores the target's conventional loader before packaging. The
post-build checks enforce:

- the target machine and endianness;
- the target's standard ELF interpreter;
- a maximum `GLIBC_2.31` symbol requirement; and
- successful execution of `hwi --version` in the target environment.

CI bootstraps the pinned channel with GNU Guix 1.5.0 release binaries rather
than Ubuntu's older Guix package. Both supported bootstrap archives are pinned
by SHA256 and checked against their GNU release signatures before installation.
The bootstrap architecture is native to the runner; `guix time-machine` then
evaluates the package with the exact channel revision in `channels.scm`.

Run the native x86_64 build from a clean checkout with a working Guix daemon:

```sh
contrib/guix/build-bundle
```

Select another supported Guix system with its Bitcoin Core target triple:

```sh
HWI_TARGET=aarch64-linux-gnu contrib/guix/build-bundle
```

The supported Guix targets are `x86_64-linux-gnu`,
`arm-linux-gnueabihf`, `aarch64-linux-gnu`, and `riscv64-linux-gnu`.
PyInstaller is not a cross-compiler, so the selected target Python,
extensions, bootloader, collection pass, and runtime test must execute
natively or through binfmt/QEMU. The GitHub workflow uses native hosted
runners where available and QEMU-user on x86_64 for ARMv7 and RISC-V. The
emulated jobs require the kernel binfmt `F` flag, which keeps the static QEMU
interpreter available inside Guix's isolated build environment. The package
closure remains pinned, and two independent output archives still have to
match exactly.

To rebuild all inputs rather than accepting signed Guix substitutes:

```sh
HWI_GUIX_BUILD_FLAGS=--no-substitutes contrib/guix/build-bundle
```

The archive and its SHA256 file are written under `dist/guix`.

## Target status

| Bitcoin Core target | Builder used by HWI | CI execution environment |
|---|---|---|
| `x86_64-linux-gnu` | Guix, glibc 2.31 | Native GitHub x86_64 Linux |
| `arm-linux-gnueabihf` | Guix, glibc 2.31 | GitHub x86_64 Linux with QEMU-user ARM |
| `aarch64-linux-gnu` | Guix, glibc 2.31 | Native GitHub ARM64 Linux |
| `riscv64-linux-gnu` | Guix, glibc 2.31 | GitHub x86_64 Linux with QEMU-user RISC-V |
| `powerpc64-linux-gnu` | Native glibc 2.31 builder required | Blocked on a pinned big-endian ppc64 runner or QEMU image |
| `x86_64-w64-mingw32` | Native PyInstaller plus pinned libusb | Native GitHub Windows x64 |
| `x86_64-apple-darwin` | Native PyInstaller plus source-built libusb | Native GitHub Intel macOS |
| `arm64-apple-darwin` | Native PyInstaller plus source-built libusb | Native GitHub Apple-silicon macOS |

Big-endian POWER is not silently replaced with `powerpc64le-linux-gnu`.
Guix supports `powerpc64le-linux` but not Bitcoin Core's big-endian
`powerpc64-linux-gnu` target, and GitHub does not publish a ppc64 hosted
runner. That target remains in the machine-readable contract so a release
cannot accidentally claim complete Core coverage. Enabling it requires two
independent, pinned ppc64 environments that pass the same ELF and glibc 2.31
checks.

## macOS and Windows

The macOS jobs build both Intel and Apple-silicon archives. libusb is built at
a fixed source path with path remapping and without a Mach-O UUID, then every
Mach-O file is checked for the expected architecture and a deployment target
no newer than Core's macOS 14.0 floor. The unsigned tree is ad-hoc signed only
to make it runnable; official Developer ID signatures and notarization remain
a protected post-reproduction release step.

The Windows job uses pinned Python and libusb inputs, validates every PE file
as x86_64, executes the finished bundle, and packages it with the same
canonical manifest and archive code used on Unix.

Successful CI publishes one `hwi-<target>-<reproducer>` artifact per build and
a `hwi-bundle-bundles-<commit>` artifact containing one verified archive per
hosted target plus `SHA256SUMS`.
