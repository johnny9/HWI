#!/usr/bin/env bash
# Build the headless HWI bundle for the current Linux or macOS target.

export LC_ALL=C
export PYTHONHASHSEED=0
export PYTHONNOUSERSITE=1
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1546300800}"

set -euo pipefail

if [[ -z "${HWI_LIBUSB_PATH:-}" ]]; then
    echo "HWI_LIBUSB_PATH must name the target libusb shared library" >&2
    exit 1
fi

case "$(uname -s)" in
    Linux|Darwin) ;;
    *)
        echo "The HWI bundle PoC currently supports Linux and macOS" >&2
        exit 1
        ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-${project_dir}/build/pyinstaller-cache}"
cd "${project_dir}"

poetry install --sync
poetry run pyinstaller --clean --noconfirm hwi-bundle.spec
poetry run python contrib/generate_bundle_manifest.py dist/hwi

echo "Unsigned bundle created at ${project_dir}/dist/hwi"
