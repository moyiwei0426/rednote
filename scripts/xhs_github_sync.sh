#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_URL="${REMOTE_URL:-${1:-}}"
BRANCH="${BRANCH:-main}"
COMMIT_MSG="${COMMIT_MSG:-Add XHS distributed collection kit and data export workflow}"

if [ -n "$REMOTE_URL" ]; then
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REMOTE_URL"
  else
    git remote add origin "$REMOTE_URL"
  fi
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  cat <<'MSG'
No git remote named origin is configured.

Create a private GitHub repository, then run:

  REMOTE_URL=git@github.com:<owner>/<repo>.git scripts/xhs_github_sync.sh

or:

  REMOTE_URL=https://github.com/<owner>/<repo>.git scripts/xhs_github_sync.sh
MSG
  exit 2
fi

git add \
  .gitignore \
  XHS_DISTRIBUTED_COLLECTION_PACKAGE.md \
  XHS_GAOKAO_BASELINE_PLAN.md \
  XHS_OTHER_DEVICE_RUNBOOK.md \
  xhs_core_event_collection_plan.md \
  xhs_distributed_runner.py \
  xhs_unified_export.py \
  xhs_author_probe.py \
  run_xhs_device.sh \
  scripts \
  tools \
  configs \
  github_data

if git diff --cached --quiet; then
  echo "Nothing staged; repository is already up to date."
else
  git commit -m "$COMMIT_MSG"
fi

git branch -M "$BRANCH"
git push -u origin "$BRANCH"
