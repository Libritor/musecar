"""How often does the car do what the wearer was asked to do?

Reads a tick log written by `muse_drive.py --test N` (cued trials: the
wearer is told "focus" or "relax", or "tilt left/right"; relax alternates
with the driving cues, which come in shuffled order, each cue lasting 12 to
20 s drawn at random, and every tick records the cue next to the command
the laptop sent and the board's reply) and reports:

  agreement   share of ticks, after a grace period following each cue, on
              which the command the BOARD acknowledged matched the cue (on a
              tick without a reply, the byte sent); with a trial-level
              bootstrap interval, per cue, and the same number for a car
              that ignores the wearer (constant forward, constant stop,
              and the cues reassigned to the trials: the chance level, over
              every distinct assignment when there are at most 200 000 of
              them, so six trials cannot give a p-value under 1/20, else
              1000 random ones)
  latency     seconds from each cue to the car first holding the matching
              command for a second; a trial succeeds if that happens within
              8 s and the command then matches on at least 70% of the
              settled ticks
  stability   unprompted command changes per minute once a trial has
              settled, i.e. how often the car flips on its own
  signal      how separable the index was between focus and relax cues
              (AUC over ticks), which says whether the limit is the EEG or
              the thresholds
  link        how often the board confirmed the command it was sent, and
              how often the headband data or the board were missing

    python tools/intent_report.py build/muse_run_<time>.csv
"""

import csv
import itertools
import json
import math
from pathlib import Path
import random
import re
import sys

import numpy as np

MAX_EXACT = 200_000   # enumerate every cue assignment up to this many (20 trials of 10 + 10 is 184 756)
ACK = re.compile(r"car cmd=(\d)")

GRACE_S = 5.0      # after a cue, time allowed before ticks count
HOLD_S = 1.0       # the command must hold this long to count as reached
SUCCESS_S = 8.0    # reached within this long = a successful trial
EXPECTED = {"focus": "1", "relax": "0", "left": "3", "right": "4", "straight": "1"}


def trials_of(rows):
    """Split the cued drive ticks into trials: (cue, [ticks]). The log
    labels cues "relax#4" so repeated cues stay separate trials."""
    trials = []
    label = None
    for row in rows:
        if row["phase"] != "drive" or not row.get("cue"):
            continue
        if row["cue"] != label:
            label = row["cue"]
            trials.append((label.split("#")[0], []))
        trials[-1][1].append(row)
    return trials


def board_cmd(row):
    """The command the board acknowledged on this tick, from its status
    line as the log stored it, or None when there was no reply."""
    m = ACK.search(row.get("car") or "")
    return m.group(1) if m else None


def command(row):
    """What the car was doing on this tick: the board's acknowledged
    command, else (no reply on that tick) the byte the laptop sent."""
    return board_cmd(row) or row.get("cmd") or ("1" if row.get("sent") == "1" else "0")


def matches(row, cue):
    cmd = command(row)
    if cue == "focus":  # any forward command counts, steering or not
        return cmd in ("1", "2", "3", "4")
    return cmd == EXPECTED[cue]


def analyse(trials):
    """Per-trial latency and settled ticks, then the summary numbers."""
    per_trial = []
    for cue, ticks in trials:
        t0 = float(ticks[0]["time"])
        times = np.array([float(r["time"]) - t0 for r in ticks])
        ok = np.array([matches(r, cue) for r in ticks])
        latency = None
        for i in range(len(ticks)):
            if ok[i] and ok[(times >= times[i]) & (times < times[i] + HOLD_S)].all():
                latency = float(times[i])
                break
        settled = times >= GRACE_S
        cmds = [command(r) for r in ticks]
        flips = sum(1 for i in range(1, len(ticks))
                    if settled[i] and cmds[i] != cmds[i - 1])
        agreement = float(ok[settled].mean()) if settled.any() else None
        per_trial.append(dict(
            cue=cue, seconds=round(float(times[-1]), 1), latency=latency,
            # Reached in time and then mostly kept: a car that merely passes
            # through the right state does not get credit.
            success=(latency is not None and latency <= SUCCESS_S and
                     agreement is not None and agreement >= 0.7),
            agreement=agreement,
            settled_ticks=int(settled.sum()), settled_ok=int(ok[settled].sum()),
            settled_unacked=int(sum(1 for i, r in enumerate(ticks)
                                    if settled[i] and board_cmd(r) is None)),
            flips=flips, settled_minutes=float(settled.sum()) / 600.0))
    return per_trial


def bootstrap(per_trial, n=2000, seed=1):
    rng = random.Random(seed)
    rows = [t for t in per_trial if t["settled_ticks"]]
    values = []
    for _ in range(n):
        sample = [rng.choice(rows) for _ in rows]
        values.append(sum(t["settled_ok"] for t in sample) /
                      max(1, sum(t["settled_ticks"] for t in sample)))
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def assignments(cues):
    """Every distinct way of assigning these cue labels to the trials."""
    counts = {k: cues.count(k) for k in sorted(set(cues))}
    n = len(cues)

    def rec(kinds, free, chosen):
        if not kinds:
            yield tuple(chosen[i] for i in range(n))
            return
        k = kinds[0]
        for picked in itertools.combinations(free, counts[k]):
            for i in picked:
                chosen[i] = k
            yield from rec(kinds[1:], [i for i in free if i not in picked], chosen)

    yield from rec(list(counts), list(range(n)), [None] * n)


def n_assignments(cues):
    counts = [cues.count(k) for k in set(cues)]
    total = math.factorial(len(cues))
    for c in counts:
        total //= math.factorial(c)
    return total


def shuffled_agreement(trials, n=1000, seed=2):
    """Agreement if the cues had been assigned to the trials differently:
    what a car that ignores the wearer scores by luck. Every distinct
    assignment when there are at most MAX_EXACT (the exact null; the real
    assignment is one of them, so the p-value's floor is 1 / their number),
    else n random shuffles. Returns (values, exact)."""
    cues = [cue for cue, _ in trials]
    kinds = sorted(set(cues))
    table, total = [], 0
    for _, ticks in trials:        # per trial, how many settled ticks each cue would match
        t0 = float(ticks[0]["time"])
        settled = [r for r in ticks if float(r["time"]) - t0 >= GRACE_S]
        table.append({k: sum(matches(r, k) for r in settled) for k in kinds})
        total += len(settled)

    def score(labels):
        return sum(table[i][lab] for i, lab in enumerate(labels)) / max(1, total)

    if n_assignments(cues) <= MAX_EXACT:
        return [score(lab) for lab in assignments(cues)], True
    rng = random.Random(seed)
    values = []
    for _ in range(n):
        rng.shuffle(cues)
        values.append(score(cues))
    return values, False


def auc(rows_a, rows_b, key="level"):
    a = np.array([float(r[key]) for r in rows_a if r.get(key)])
    b = np.array([float(r[key]) for r in rows_b if r.get(key)])
    if not len(a) or not len(b):
        return None
    return float((a[:, None] > b[None, :]).mean() + 0.5 * (a[:, None] == b[None, :]).mean())


def report(path, write=True):
    path = Path(path)
    rows = list(csv.DictReader(open(path, newline="")))
    trials = trials_of(rows)
    if len(trials) < 2:
        print(f"{path.name}: no cued trials in this log (run muse_drive.py --test N).")
        return None
    per_trial = analyse(trials)
    settled = [t for t in per_trial if t["settled_ticks"]]
    agreement = sum(t["settled_ok"] for t in settled) / max(1, sum(t["settled_ticks"] for t in settled))
    low, high = bootstrap(per_trial)
    chance, exact = shuffled_agreement(trials)
    beat = sum(1 for c in chance if c >= agreement - 1e-12)
    # exact: the real assignment is among the enumerated ones; random: the
    # add-one rule, so a Monte Carlo p never reads zero
    p_value = beat / len(chance) if exact else (beat + 1) / (len(chance) + 1)
    unacked = sum(t["settled_unacked"] for t in per_trial)
    by_cue = {}
    for cue in sorted({t["cue"] for t in per_trial}):
        ts = [t for t in per_trial if t["cue"] == cue]
        lat = [t["latency"] for t in ts if t["latency"] is not None]
        by_cue[cue] = dict(
            trials=len(ts),
            agreement=round(sum(t["settled_ok"] for t in ts) /
                            max(1, sum(t["settled_ticks"] for t in ts)), 3),
            success=round(sum(t["success"] for t in ts) / len(ts), 3),
            latency_median=round(float(np.median(lat)), 1) if lat else None,
            latency_max=round(max(lat), 1) if lat else None,
            not_reached=sum(t["latency"] is None for t in ts))
    constant = {}
    for name, cmd in (("always forward", "1"), ("always stopped", "0")):
        ok = total = 0
        for cue, ticks in trials:
            t0 = float(ticks[0]["time"])
            for r in ticks:
                if float(r["time"]) - t0 >= GRACE_S:
                    total += 1
                    ok += matches({"cmd": cmd, "sent": cmd}, cue)
        constant[name] = round(ok / max(1, total), 3)
    settled_rows = {}
    for cue, ticks in trials:
        t0 = float(ticks[0]["time"])
        settled_rows.setdefault(cue, []).extend(
            r for r in ticks if float(r["time"]) - t0 >= GRACE_S)
    signal = auc(settled_rows.get("focus", []), settled_rows.get("relax", []))
    drive_rows = [r for r in rows if r["phase"] == "drive"]
    acked = [r for r in drive_rows if r["car"].startswith("car cmd=")]
    ack_ok = sum(1 for r in acked if (r["car"] != "car cmd=0") == (r["sent"] == "1"))
    link = dict(
        board_confirming=round(len(acked) / max(1, len(drive_rows)), 3),
        confirmed_matching=round(ack_ok / max(1, len(acked)), 3),
        unplugged_ticks=sum(r["car"] == "CAR UNPLUGGED" for r in drive_rows),
        no_signal_ticks=sum(1 for r in drive_rows if not r["level"]))
    flips = sum(t["flips"] for t in per_trial)
    minutes = sum(t["settled_minutes"] for t in per_trial)
    result = dict(
        log=path.name, trials=len(per_trial),
        agreement=round(agreement, 3), agreement_ci95=[round(low, 3), round(high, 3)],
        chance_agreement=round(float(np.mean(chance)), 3),
        chance_p_value=round(p_value, 4), chance_exact=exact,
        chance_assignments=len(chance), scored_on="board reply",
        settled_ticks_without_reply=unacked, constant_controllers=constant,
        by_cue=by_cue,
        flips_per_minute=round(flips / minutes, 2) if minutes else None,
        signal_auc_focus_vs_relax=round(signal, 3) if signal is not None else None,
        link=link, per_trial=per_trial)

    print(f"\n=== {path.name}: {len(per_trial)} cued trials ===")
    print(f"The board's acknowledged command matched the cue on {100 * agreement:.0f}% of "
          f"settled ticks (95% CI {100 * low:.0f}-{100 * high:.0f}%; "
          f"{unacked} settled ticks had no reply and were scored on the byte sent).")
    print(f"A car ignoring you would score {100 * np.mean(chance):.0f}% by luck "
          f"(cues reassigned; p = {p_value:.3f}, "
          + (f"exact over all {len(chance)} assignments" if exact else f"{len(chance)} random shuffles")
          + f"), {100 * constant['always forward']:.0f}% "
          f"if always forward, {100 * constant['always stopped']:.0f}% if always stopped.")
    for cue, d in by_cue.items():
        lat = (f"median {d['latency_median']} s, slowest {d['latency_max']} s"
               if d["latency_median"] is not None else "never reached")
        print(f"  {cue:8s} {d['trials']} trials: agreement {100 * d['agreement']:.0f}%, "
              f"reached within {SUCCESS_S:.0f} s in {100 * d['success']:.0f}%, "
              f"latency {lat}, not reached {d['not_reached']}")
    if result["flips_per_minute"] is not None:
        print(f"Unprompted flips once settled: {result['flips_per_minute']} per minute.")
    if signal is not None:
        print(f"Index separability focus vs relax (AUC): {signal:.2f} "
              "(0.5 = none, 1.0 = perfect).")
    print(f"Board confirmed a command on {100 * link['board_confirming']:.0f}% of ticks, "
          f"matching what was sent on {100 * link['confirmed_matching']:.0f}% of those; "
          f"{link['unplugged_ticks']} ticks unplugged, {link['no_signal_ticks']} without headband data.")
    if write:
        out = path.with_name(path.stem + "_report.json")
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Written to {out}")
    return result


if __name__ == "__main__":
    for arg in sys.argv[1:] or [""]:
        if not arg:
            sys.exit(__doc__)
        report(arg)
