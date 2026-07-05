#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="${RUN_ID:-${1:?usage: RUN_ID=... MANIFEST=... RUN_ROOT=... scripts/xhs_merge_received.sh}}"
MANIFEST="${MANIFEST:-configs/xhs_core_events_manifest.csv}"
RUN_ROOT="${RUN_ROOT:-runs/xhs_core_events}"
REPRESENTATIVE_NOTES_PER_PHASE="${REPRESENTATIVE_NOTES_PER_PHASE:-120}"
OUTPUT_DIR="${OUTPUT_DIR:-$RUN_ROOT/$RUN_ID/merged}"

python3 xhs_unified_export.py \
  --run-dir "$RUN_ROOT/$RUN_ID" \
  --manifest "$MANIFEST" \
  --output-dir "$OUTPUT_DIR" \
  --representative-notes-per-phase "$REPRESENTATIVE_NOTES_PER_PHASE"

echo "Merged output: $OUTPUT_DIR"
