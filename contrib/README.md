# Assorted tools

## `build_bin.sh`

Creates a virtualenv with the locked dependencies using Poetry. Then uses pyinstaller to create a standalone binary for the OS type currently running.

## Reproducible HWI bundles

`build_bundle.sh` builds the Linux or macOS bundle intended to be installed
alongside Bitcoin Core. Unlike the standalone release build, this produces a
headless PyInstaller `onedir` bundle and a canonical manifest covering every
runtime file, the HWI version, target tuple, and entry point. The manifest is
unsigned; signing belongs to the application release process so that private
release keys never enter the HWI build.

Set `HWI_LIBUSB_PATH` to the target libusb shared library and run:

```sh
HWI_LIBUSB_PATH=/path/to/libusb-1.0.so.0 contrib/build_bundle.sh
```

On macOS, use the path to `libusb-1.0.dylib`. Native Windows CI invokes the
same PyInstaller specification with a pinned `libusb-1.0.dll`. The resulting
unsigned bundle is written to `dist/hwi`.

`package_bundle.py` validates that the bundle still matches its canonical
manifest and packages it with normalized ordering, ownership, permissions,
timestamps, and gzip metadata while preserving PyInstaller symlinks:

```sh
SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)" \
  poetry run python contrib/package_bundle.py \
    dist/hwi dist/hwi-bundle.tar.gz
```

The authoritative Guix builder, Bitcoin Core target contract, hosted CI
coverage, and big-endian POWER exception are documented in `guix/README.md`.

## `build_dist.sh`

Creates a virtualenv with the locked dependencies using Poetry. Then uses Poetry to produce deterministic builds of the wheel and sdist for upload to PyPi

`faketime` needs to be installed

## `build_wine.sh`

Sets up Wine with Python and everything needed to build Windows binaries. Creates a virtualenv with the locked dependencies using Poetry. Then uses pyinstaller to create a standalone Windows binary.

`wine` needs to be installed

## `generate_setup.sh`

Builds the source distribution and extracts the setup.py from it.

## `build.Dockerfile`

A Dockerfile for setting up the deterministic build environment.

# Other files

## `reproducible-python.diff`

A path for python in order to do a deterministic build of Python for the deterministically built binaries.

## `pyinstaller-hooks/hook-hwilib.devices.py`

Pyinstaller hook so that the device drivers are actually included. Due to how the imports work, we need this hook.
