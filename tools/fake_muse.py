"""Stand in for MuseLog: send made-up band powers so the PC-to-car chain can
be tested without a headband.

Alternates relaxed (strong alpha) and focused (strong beta) in MuseLog's
default OSC format, starting relaxed. Start muse_drive.py first: it begins
calibrating when these packets arrive, and the default --period then lines
up with its relax and focus phases.
"""

import argparse
import random
import time

from pythonosc.udp_client import SimpleUDPClient

# Bels per band: (relaxed, focused).
LEVELS = {"delta": (0.9, 0.9), "theta": (0.5, 0.4), "alpha": (1.0, 0.3),
          "beta": (0.2, 0.7), "gamma": (-0.3, 0.1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--period", type=float, default=21,
                        help="seconds in each state (default 21)")
    parser.add_argument("--seconds", type=float, default=0,
                        help="stop after this long; 0 = until Ctrl+C")
    args = parser.parse_args()
    client = SimpleUDPClient(args.ip, args.port)
    start = time.monotonic()
    state = None
    while not args.seconds or time.monotonic() - start < args.seconds:
        focused = int((time.monotonic() - start) // args.period) % 2
        if focused != state:
            state = focused
            print("focused" if focused else "relaxed", flush=True)
        for band, levels in LEVELS.items():
            client.send_message(
                f"/muse/elements/{band}_absolute",
                [levels[focused] + random.gauss(0, 0.05) for _ in range(4)])
        client.send_message("/muse/elements/horseshoe", [1, 1, 1, 1])
        time.sleep(0.1)


if __name__ == "__main__":
    main()
