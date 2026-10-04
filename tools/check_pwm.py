"""Read actual timer and GPIO registers; never sends motor commands."""
import argparse
import json
from pathlib import Path
import re
import time
import serial

samples = []
errors = []
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=float, default=30)
args = parser.parse_args()
with serial.Serial('COM7', 115200, timeout=0.5) as port:
    end = time.monotonic() + args.seconds
    previous_pulse = None
    while time.monotonic() < end:
        line = port.readline().decode('ascii', errors='replace').strip()
        if not line.startswith('PWM '):
            continue
        r = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', line)}
        if len(r) != 11:
            errors.append('Incomplete register report: ' + line)
            continue
        checks = {
            'timer_clock': r['pclk'] == 16000000,
            'prescaler': r['psc'] == 0,
            'period': r['arr'] == 29999,
            'counter_running': r['cr1'] & 1 == 1,
            'up_counting': r['cr1'] & 0x70 == 0,
            'channel3_enabled_active_high': r['ccer'] & 0x300 == 0x100,
            'channel4_enabled_active_high': r['ccer'] & 0x3000 == 0x1000,
            'both_pwm1_outputs': r['ccmr2'] & 0x7373 == 0x6060,
            'pb10_af_mode': r['moder'] >> 20 & 3 == 2,
            'pb11_af_mode': r['moder'] >> 22 & 3 == 2,
            'pb10_af1': r['afr'] >> 8 & 15 == 1,
            'pb11_af1': r['afr'] >> 12 & 15 == 1,
            'matching_duty': r['ccr3'] == r['ccr4'] and r['ccr3'] in (0, 22500),
            'directions': r['odr'] & 15 == (6 if r['ccr3'] else 0),
        }
        failed = [name for name, passed in checks.items() if not passed]
        errors.extend(failed)
        r['duty3_percent'] = 100 * r['ccr3'] / (r['arr'] + 1)
        r['duty4_percent'] = 100 * r['ccr4'] / (r['arr'] + 1)
        samples.append(r)
        if previous_pulse != r['ccr3']:
            print(line, flush=True)
            print('Duty:', r['duty3_percent'], r['duty4_percent'], 'Failed:', failed, flush=True)
        previous_pulse = r['ccr3']
forward_seen = any(r['ccr3'] == 22500 for r in samples)
result = dict(samples=samples, errors=errors, forward_seen=forward_seen,
              final_neutral=bool(samples and samples[-1]['ccr3'] == 0),
              passed=bool(samples and forward_seen and not errors))
path = Path(__file__).resolve().parents[1] / 'build/button/pwm_check.json'
path.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'samples'}))
