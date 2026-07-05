#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it first: https://docs.astral.sh/uv/"
  exit 2
fi

if [ ! -d "MediaCrawler" ]; then
  echo "MediaCrawler directory is missing. Use the full project package."
  exit 2
fi

echo "[1/3] Sync MediaCrawler Python environment"
(
  cd MediaCrawler
  UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.org/simple}" uv sync
)

echo "[2/3] Compile local helper scripts"
python3 -m py_compile xhs_distributed_runner.py xhs_unified_export.py xhs_author_probe.py scripts/xhs_device_status.py

echo "[3/3] Setup done"
cat <<'MSG'

Next:
1. Start Chrome with remote debugging on port 9222, or use MediaCrawler qrcode login.
2. Log in to Xiaohongshu in that browser.
3. Run a dry-run first, for example:

   DEVICE_ID=A ACCOUNT_ID=account_a STAGE=recon DRY_RUN=1 scripts/xhs_device_run.sh

MSG
