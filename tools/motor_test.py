"""Spin the motors from the PC, no headband needed: forward at 75% PWM for a
few seconds, a pause, then forward at full power, while printing what the
board reports. Watch the wheels.

    python tools/motor_test.py                # 4 s at 75%, 4 s at full power
    python tools/motor_test.py --power full --seconds 6
Ctrl+C stops the motors.
"""

import argparse
import time

import serial
from serial.tools import list_ports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto", help="COM port, default the ST-LINK")
    parser.add_argument("--seconds", type=float, default=4, help="length of each burst")
    parser.add_argument("--power", choices=("normal", "full", "both"), default="both")
    args = parser.parse_args()
    port = args.port
    if port == "auto":
        found = [p.device for p in list_ports.comports() if p.vid == 0x0483]
        if not found:
            parser.error("no ST-LINK on USB; plug the board in or pass --port")
        port = found[0]
    link = serial.Serial(port, 115200, timeout=0.05)
    print(f"Board on {port}. The board prints its state on every change.")
    bursts = {"normal": [b"1"], "full": [b"2"], "both": [b"1", b"2"]}[args.power]
    text = b""

    def listen(seconds, command=b"0"):
        """Send `command` ten times a second for `seconds` and print replies."""
        nonlocal text
        end = time.monotonic() + seconds
        due = time.monotonic()
        while time.monotonic() < end:
            if time.monotonic() >= due:
                link.write(command)
                due += 0.1
            text += link.read(4096)
            *lines, text = text.split(b"\r\n")
            for line in lines:
                if line.startswith(b"SERIAL") or line.startswith(b"BUTTON"):
                    print("  board:", line.decode("ascii", "replace"))
            time.sleep(0.02)

    try:
        for command in bursts:
            label = "75% PWM" if command == b"1" else "FULL POWER"
            print(f"\nForward at {label} for {args.seconds:.0f} s ...")
            listen(args.seconds, command)
            print("Stop for 2 s ...")
            listen(2.0, b"0")
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        link.write(b"0")
        link.close()
    print("\nIf the board reported cmd=1 or cmd=2 but the wheels did not turn, the "
          "problem is after the Nucleo: L298N power, ENA/ENB jumpers, wiring or "
          "motor supply voltage.")


if __name__ == "__main__":
    main()
