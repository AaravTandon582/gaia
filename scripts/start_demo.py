"""Start missing production demo services without stopping existing processes."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / '.release-build' / 'services'
LOGS.mkdir(parents=True, exist_ok=True)


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(.5)
        return connection.connect_ex(('127.0.0.1', port)) == 0


def healthy(url, kind):
    try:
        with urlopen(url, timeout=2) as response:
            body = response.read().decode()
        if kind == 'backend':
            result = json.loads(body)
            return result.get('status') == 'ok' and result.get('scouts') == 4
        return 'GAIA' in body
    except (OSError, ValueError):
        return False


def ensure(name, port, url, command, cwd):
    if listening(port):
        if not healthy(url, name):
            raise SystemExit(f'Port {port} is occupied by an unexpected or unhealthy service. No process was stopped.')
        print(f'Reusing healthy GAIA {name} on port {port}.')
        return
    logfile = LOGS / f'{name}.log'
    with logfile.open('ab') as output:
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True, env=os.environ.copy())
    (LOGS / f'{name}.pid').write_text(str(process.pid))
    for _ in range(60):
        if process.poll() is not None:
            raise SystemExit(f'{name} exited. Read {logfile}')
        if healthy(url, name):
            print(f'Started {name} (PID {process.pid}). Logs: {logfile}')
            return
        time.sleep(.5)
    raise SystemExit(f'{name} has not become ready. Read {logfile}')


if __name__ == '__main__':
    ensure('backend', 8000, 'http://127.0.0.1:8000/health',
           [sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000'], ROOT)
    ensure('frontend', 3000, 'http://127.0.0.1:3000/dashboard',
           [shutil.which('node'), 'node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3000'], ROOT / 'frontend')
    print('GAIA is ready: http://127.0.0.1:3000/dashboard')
