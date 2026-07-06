#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DEVICE_ID="${DEVICE_ID:-${1:-A}}"
ACCOUNT_ID="${ACCOUNT_ID:-${2:-account_${DEVICE_ID}}}"
STAGE="${STAGE:-${3:-recon}}"
RUN_ID="${RUN_ID:-main_$(date +%Y%m%d)}"
MANIFEST="${MANIFEST:-configs/xhs_core_events_manifest.csv}"
RUN_ROOT="${RUN_ROOT:-runs/xhs_core_events}"

if [ "$STAGE" = "full-recon-comments" ]; then
  COMMENTS_PER_NOTE="${COMMENTS_PER_NOTE:-10000}"
  SLEEP_BETWEEN_KEYWORDS="${SLEEP_BETWEEN_KEYWORDS:-1200}"
  MAX_CONCURRENCY="${MAX_CONCURRENCY:-1}"
fi

COMMON_ARGS=(
  --manifest "$MANIFEST"
  --run-root "$RUN_ROOT"
  --run-id "$RUN_ID"
  --device-id "$DEVICE_ID"
  --account-id "$ACCOUNT_ID"
  --stage "$STAGE"
  --max-concurrency "${MAX_CONCURRENCY:-1}"
  --stop-on-captcha
  --no-stop-on-error
)

if [ -n "${EVENT_IDS:-}" ]; then
  COMMON_ARGS+=(--event-ids "$EVENT_IDS")
fi
if [ -n "${GROUPS:-}" ]; then
  COMMON_ARGS+=(--groups "$GROUPS")
fi
if [ -n "${MAX_EVENTS:-}" ]; then
  COMMON_ARGS+=(--max-events "$MAX_EVENTS")
fi
if [ -n "${MAX_KEYWORDS:-}" ]; then
  COMMON_ARGS+=(--max-keywords "$MAX_KEYWORDS")
fi
if [ -n "${NOTES_PER_KEYWORD:-}" ]; then
  COMMON_ARGS+=(--notes-per-keyword "$NOTES_PER_KEYWORD")
fi
if [ -n "${COMMENTS_PER_NOTE:-}" ]; then
  COMMON_ARGS+=(--comments-per-note "$COMMENTS_PER_NOTE")
fi
if [ -n "${SLEEP_BETWEEN_KEYWORDS:-}" ]; then
  COMMON_ARGS+=(--sleep-between-keywords "$SLEEP_BETWEEN_KEYWORDS")
fi
if [ -n "${SLEEP_BETWEEN_BATCHES:-}" ]; then
  COMMON_ARGS+=(--sleep-between-batches "$SLEEP_BETWEEN_BATCHES")
fi
if [ -n "${NOTES_PER_BATCH:-}" ]; then
  COMMON_ARGS+=(--notes-per-batch "$NOTES_PER_BATCH")
fi
if [ -n "${MAX_BATCHES:-}" ]; then
  COMMON_ARGS+=(--max-batches "$MAX_BATCHES")
fi
if [ -n "${SELECTED_NOTES_FILE:-}" ]; then
  COMMON_ARGS+=(--selected-notes-file "$SELECTED_NOTES_FILE")
fi
if [ -n "${SELECTED_PHASE_IDS:-}" ]; then
  COMMON_ARGS+=(--selected-phase-ids "$SELECTED_PHASE_IDS")
fi
if [ -n "${SELECTED_NOTES_PER_PHASE:-}" ]; then
  COMMON_ARGS+=(--selected-notes-per-phase "$SELECTED_NOTES_PER_PHASE")
fi
if [ -n "${AUTHOR_POST_LIMIT:-}" ]; then
  COMMON_ARGS+=(--author-post-limit "$AUTHOR_POST_LIMIT")
fi
if [ -n "${DRY_RUN:-}" ] && [ "$DRY_RUN" != "0" ]; then
  COMMON_ARGS+=(--dry-run)
fi

echo "Run ID: $RUN_ID"
echo "Device: $DEVICE_ID | Account: $ACCOUNT_ID | Stage: $STAGE"
echo "Manifest: $MANIFEST"
echo "Run root: $RUN_ROOT"
if [ -n "${EVENT_IDS:-}" ]; then
  echo "Event filter: $EVENT_IDS"
fi
if [ -n "${GROUPS:-}" ]; then
  echo "Group filter: $GROUPS"
fi
python3 xhs_distributed_runner.py "${COMMON_ARGS[@]}"
