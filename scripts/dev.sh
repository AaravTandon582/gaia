#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Use the installed Node 22 when the default shell still points at an older node.
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)' 2>/dev/null; then
  if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
    source "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
    nvm use 22
  else
    echo "Node 22 is required. Install it, then rerun ./scripts/dev.sh"
    exit 1
  fi
fi
venv_dir="${GAIA_VENV_DIR:-.venv}"
if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install -q -r backend/requirements-dev.txt
(cd frontend && npm install --no-fund --no-audit)

"$venv_dir/bin/python" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
(cd frontend && exec node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3000) &
web_pid=$!
cleanup() {
  kill "$api_pid" "$web_pid" 2>/dev/null || true
  wait "$api_pid" "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
printf '\nGAIA demo: http://127.0.0.1:3000/dashboard\nSelect Amazon Basin to scan. Ctrl-C stops both servers.\n\n'
# Exit the pair if either service fails, rather than leaving an orphan server.
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do sleep 1; done
exit 1
