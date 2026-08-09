# Reproducible Linux OCI bundle builds

Linux HWI bundles are built inside the multi-architecture Python 3.12.10
Bullseye image pinned in `contrib/bundle-targets.json` by its OCI index digest.
The image supplies an already-built glibc 2.31 and compatible Python runtime;
CI does not rebuild glibc, GCC, or the Linux userspace.

The remaining Debian tools and libusb runtime come from the immutable
`20250508T000000Z` Debian snapshot. HWI and PyInstaller dependencies remain
locked by `poetry.lock`. The completed bundle is rejected if any ELF file has
the wrong architecture, uses a nonstandard interpreter, or requires a glibc
symbol newer than 2.31.

## Hosted targets

| Bitcoin Core target | OCI execution environment |
|---|---|
| `x86_64-linux-gnu` | Native GitHub x86_64 runner, Python Bullseye amd64 image |
| `aarch64-linux-gnu` | Native GitHub ARM64 runner, Python Bullseye arm64 image |

PyInstaller is not a cross-compiler. ARMHF and RISC-V remain in the target
contract but are not advertised as hosted artifacts because no matching native
GitHub runners and pinned Python 3.12 Bullseye images are available. They must
not be replaced with slow QEMU jobs in release CI. Big-endian POWER likewise
requires a future native, digest-pinned environment.

## Local x86_64 build

Run the repository in the exact image recorded in `bundle-targets.json`, then
prepare its pinned Debian snapshot and build the archive:

```sh
docker run --rm \
  --volume "$PWD:/opt/hwi/src" \
  --workdir /opt/hwi/src \
  --env HWI_TARGET=x86_64-linux-gnu \
  docker.io/library/python@sha256:57ab68549579e5e7bdf485fd33792577b5f4c14336fdc9a9a5a9fb6af0af1776 \
  bash -c 'contrib/oci/install-build-dependencies && contrib/oci/build-bundle'
```

The normalized archive and ELF report are written under `dist/oci`. Official
signing remains a separate protected release step after two independently
produced archives compare byte-for-byte.
