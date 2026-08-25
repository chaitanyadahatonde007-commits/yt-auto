#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

if [ ! -f vendor/espeak-ng/espeak-ng.wasm ]; then
  echo "Installing local voice runtime…"
  mkdir -p vendor/espeak-ng /tmp/channelforge-espeak
  npm pack espeak-ng --pack-destination /tmp/channelforge-espeak >/dev/null
  tar -xzf /tmp/channelforge-espeak/espeak-ng-*.tgz -C /tmp/channelforge-espeak
  cp /tmp/channelforge-espeak/package/dist/espeak-ng.js /tmp/channelforge-espeak/package/dist/espeak-ng.wasm vendor/espeak-ng/
fi

export PYTHONUNBUFFERED=1
HOST="${YT_AUTO_HOST:-0.0.0.0}"
PORT="${YT_AUTO_PORT:-8000}"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
