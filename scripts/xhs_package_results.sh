#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="${RUN_ID:-${1:?usage: RUN_ID=... DEVICE_ID=... scripts/xhs_package_results.sh}}"
DEVICE_ID="${DEVICE_ID:-${2:-A}}"
RUN_ROOT="${RUN_ROOT:-runs/xhs_core_events}"
OUT_DIR="${OUT_DIR:-dist/device_results}"
DEVICE_SLUG="$(echo "$DEVICE_ID" | tr '[:upper:]' '[:lower:]' | sed 's/^device_//')"
SOURCE_DIR="$RUN_ROOT/$RUN_ID/device_$DEVICE_SLUG"

if [ ! -d "$SOURCE_DIR" ]; then
  echo "Missing device output directory: $SOURCE_DIR"
  exit 2
fi

mkdir -p "$OUT_DIR"
ARCHIVE="$OUT_DIR/${RUN_ID}_device_${DEVICE_SLUG}_results_$(date +%Y%m%d_%H%M%S).zip"

python3 - <<PY
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

source = Path("$SOURCE_DIR")
archive = Path("$ARCHIVE")
with ZipFile(archive, "w", ZIP_DEFLATED) as zf:
    for path in source.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(source.parent))
print(archive.resolve())
PY
