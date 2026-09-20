#!/usr/bin/env python3
"""Run host tests and all nine base-protocol real Unix-socket scenarios."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, check=True)
for scenario in ('base-handshake', 'golden-writing-session', 'typed-rejections', 'fatal-fault',
                 'reconnect-resumed', 'reconnect-lost-state', 'sequence-exhaustion',
                 'invalid-server-inputs', 'markdown-hard-line-breaks'):
    subprocess.run([sys.executable, str(ROOT / 'vendor/protocol/runner/conformance.py'),
                    'socket', '--scenario', scenario, '--client', sys.executable,
                    str(ROOT / 'tests/socket_adapter.py')], cwd=ROOT, check=True)
