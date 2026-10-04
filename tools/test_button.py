"""Read button/PWM register feedback without sending motor commands."""
import argparse
import json
from pathlib import Path
import re
import time
import serial

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', default='COM7')
parser.add_argument('--seconds', type=float, default=30)
args = parser.parse_args()
records = []
errors = []
seen_forward = False
seen_release = False
with serial.Serial(args.port, 115200, timeout=0.5) as port:
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        line = port.readline().decode('ascii', errors='replace').strip()
        match = re.fullmatch(r'BUTTON raw=(\d) cmd=(\d) ccr3=(\d+) ccr4=(\d+)', line)
        if not match:
            continue
        raw, command, left, right = map(int, match.groups())
        records.append(dict(raw=raw, command=command, ccr3=left, ccr4=right))
        if not records[:-1] or command != records[-2]['command']:
            print(line, flush=True)
        expected = 22500 if command == 1 else 0
        if command not in (0, 1) or left != expected or right != expected:
            errors.append(line)
        if command == 1:
            seen_forward = True
        elif seen_forward:
            seen_release = True
result = dict(records=records, errors=errors, saw_forward=seen_forward,
              saw_release_after_forward=seen_release,
              final_neutral=bool(records and records[-1]['command'] == 0),
              passed=bool(seen_release and not errors and records[-1]['command'] == 0))
output = Path(__file__).resolve().parents[1] / 'build/button/button_test.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'records'}), flush=True)
