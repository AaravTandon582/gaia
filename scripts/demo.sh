#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)' 2>/dev/null; then
  if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
    source "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
    nvm use 22
  else
    echo 'Node 22.12+ is required. See README.md.'
    exit 1
  fi
fi
venv_dir="${GAIA_VENV_DIR:-.venv}"
if [[ ! -x "$venv_dir/bin/python" || ! -f frontend/.next/BUILD_ID ]]; then
  echo 'Install the dependencies and build the frontend first. See README.md.'
  exit 1
fi
exec "$venv_dir/bin/python" scripts/start_demo.py
