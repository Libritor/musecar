"""Drive the car from a Muse headband: focused = forward, relaxed = stop.

Muse -> MuseLog app on the phone -> OSC over Wi-Fi -> this script -> USB
serial -> Motor_ControlSerial() on the board.

In MuseLog's OSC Streaming Settings set Target IP to this PC (its addresses
are printed at start) and port 5000, turn on Full-rate raw EEG, then Start
Streaming. The raw EEG of the default OSC format is preferred; MuseLog's own
band powers and the legacy format are fallbacks.

The arousal index is MuseLog's (beta + gamma) / (alpha + theta), or plain
beta / alpha: each is taken per electrode, then the median over the
electrodes that have contact. A short calibration (relaxed with eyes closed,
then focused) keeps whichever of the two separates the wearer's states
better and puts it on a 0..1 scale. The car goes forward above --go and
stops below --stop.

The script sends '1' or '0' ten times a second. It sends '0' while paused,
when the headband loses contact and when the stream stops, and the firmware
stops by itself if the commands stop arriving.

Keys: SPACE begin calibration, then pause/resume the car; R recalibrate;
Q quit. Prompts are spoken as well as printed (--quiet turns that off), and
every tick is logged to build/muse_run_<time>.csv.

    python tools/muse_drive.py                 # uses the ST-LINK COM port
    python tools/muse_drive.py --serial COM7
    python tools/muse_drive.py --serial none   # no car: watch the index only
    python tools/muse_drive.py --simulate      # no headband: bench-test the car
"""

import argparse
import collections
import csv
import ctypes
import json
import math
from pathlib import Path
import re
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time

import numpy as np
from pythonosc import osc_bundle, osc_message, udp_client
import serial
from serial.tools import list_ports

try:
    import msvcrt
    import winsound
except ImportError:  # not Windows: no keys, no beep
    msvcrt = winsound = None

CHANNELS = ("TP9", "AF7", "AF8", "TP10")
# MuseLog's band edges (backend_logic/A_preprocessing.py), for raw EEG.
BAND_HZ = {"theta": (4, 8), "alpha": (8, 13), "beta": (13, 30), "gamma": (30, 40)}
# In order of preference. MuseLog's band powers come second because live
# they were placeholders for some electrodes and seconds old for others.
SOURCES = ("raw", "bands", "legacy")
# muselog: (beta + gamma) / (alpha + theta).  beta-alpha: beta / alpha.
INDEXES = ("muselog", "beta-alpha")
STALE_S = 1.0     # data older than this does not move the car
TICK_S = 0.1      # command period; the firmware gives up after 0.5 s
SETTLE_S = 3.0    # start of each calibration phase that is not used
CALIBRATION = Path(__file__).resolve().parents[1] / "build/muse_calibration.json"


class MuseStream(threading.Thread):
    """Receives MuseLog OSC and keeps the newest values of each kind."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.lock = threading.Lock()
        self.bands = {}       # name -> (time, Bels per electrode)
        self.legacy = None    # (time, [delta, theta, alpha, beta] in Bels)
        self.contact = None   # (time, horseshoe per electrode: 1 good, 4 none)
        self.raw = collections.deque(maxlen=1024)  # (time, microvolts)
        self.raw_rate = None  # 256, or 64 when MuseLog sends every 4th sample
        self.first_packet = self.last_packet = None

    def run(self):
        while True:
            try:
                data, _ = self.sock.recvfrom(4096)
            except OSError:  # Windows reports stray ICMP errors here
                continue
            now = time.monotonic()
            try:
                if osc_bundle.OscBundle.dgram_is_bundle(data):
                    messages = [m for m in osc_bundle.OscBundle(data)
                                if isinstance(m, osc_message.OscMessage)]
                else:
                    messages = [osc_message.OscMessage(data)]
            except (osc_bundle.ParseError, osc_message.ParseError):
                continue
            with self.lock:
                self.first_packet = self.first_packet or now
                self.last_packet = now
                for message in messages:
                    self._store(message.address, list(message.params), now)

    def _store(self, address, values, now):
        if len(values) < 4:
            return
        name = address.rsplit("/", 1)[-1]
        if address.startswith("/muse/elements/") and name.endswith("_absolute"):
            self.bands[name[:-len("_absolute")]] = (now, values[:4])
        elif address == "/muse/elements/horseshoe":
            self.contact = (now, values[:4])
        elif address in ("/muse/eeg", "/eeg"):
            self.raw.append((now, values[:4]))
        elif address == "/person1/eeg":
            self.legacy = (now, values[:4])

    def horseshoe(self, now):
        """Contact per electrode, or None if the app is not reporting it."""
        with self.lock:
            contact = self.contact
        return contact[1] if contact and now - contact[0] < 5.0 else None

    def index(self, source, now):
        """log10 of each ratio in INDEXES; None without fresh usable data."""
        with self.lock:
            power = self._power(source, now)
        if power is None:
            return None
        # Gamma may be a zero placeholder; the other three must be real power.
        usable = np.isfinite(power["gamma"])
        for band in ("theta", "alpha", "beta"):
            usable &= np.isfinite(power[band]) & (power[band] > 0)
        contact = self.horseshoe(now)
        if contact and len(usable) == 4:
            usable &= np.array(contact) <= 2
        if not usable.any():
            return None
        power = {band: p[usable] for band, p in power.items()}
        ratios = {"muselog": ((power["beta"] + power["gamma"]) /
                              (power["alpha"] + power["theta"])),
                  "beta-alpha": power["beta"] / power["alpha"]}
        # Per electrode, then the median: a mean of powers is swamped by one
        # noisy electrode.
        return {name: float(np.median(np.log10(ratio)))
                for name, ratio in ratios.items()}

    def _power(self, source, now):
        """Linear band powers per electrode from one kind of message."""
        with np.errstate(over="ignore", invalid="ignore"):
            if source == "bands":
                if any(band not in self.bands or
                       now - self.bands[band][0] > STALE_S for band in BAND_HZ):
                    return None
                bels = np.array([self.bands[band][1] for band in BAND_HZ],
                                float)
                # MuseLog sends exactly 0 in every band for an electrode
                # the headband has no band powers for; that is not data.
                bels[:, np.all(bels == 0, axis=0)] = np.nan
                return dict(zip(BAND_HZ, 10.0 ** bels))
            if source == "legacy":  # one average over the electrodes, no gamma
                if not self.legacy or now - self.legacy[0] > STALE_S:
                    return None
                _, theta, alpha, beta = self.legacy[1]
                return {"theta": 10.0 ** np.array([theta], float),
                        "alpha": 10.0 ** np.array([alpha], float),
                        "beta": 10.0 ** np.array([beta], float),
                        "gamma": np.zeros(1)}
        samples = list(self.raw)
        if (not samples or now - samples[-1][0] > STALE_S or
                samples[-1][0] - samples[0][0] < 2.0):
            return None
        # MuseLog sends 256 Hz, or every 4th sample unless "full rate" is on.
        rate = 256 if sum(now - t <= 2.0 for t, _ in samples) > 256 else 64
        self.raw_rate = rate
        count = 2 * rate
        if len(samples) < count or now - samples[-count][0] > 3.0:
            return None
        window = np.array([values for _, values in samples[-count:]], float)
        window -= window.mean(axis=0)
        spectrum = np.abs(np.fft.rfft(window * np.hanning(count)[:, None],
                                      axis=0)) ** 2
        hz = np.fft.rfftfreq(count, 1.0 / rate)
        power = {band: spectrum[(hz >= low) & (hz < high)].sum(axis=0)
                 for band, (low, high) in BAND_HZ.items()}
        if rate == 64:  # gamma lies above what 64 Hz can represent
            power["gamma"] = np.zeros(4)
        return power


class Car:
    """The board's serial link: "auto" (the ST-LINK, whenever it is plugged
    in), a COM port or pyserial URL, or None for no car at all."""

    def __init__(self, port):
        self.port = port
        self.link = None
        self.device = None
        if port:
            try:
                self.open()
                print(f"Car: {self.device}.")
            except serial.SerialException:
                print("Car: not plugged in yet; it is picked up when the "
                      "board's ST-LINK USB appears.")
        self.retry_at = 0.0
        self.forward = b"1"  # b"2" for full power
        self.text = b""
        self.report = None  # (time, "SERIAL" or "BUTTON", cmd) from the board

    def open(self):
        device = self.port
        if device == "auto":
            found = [p.device for p in list_ports.comports() if p.vid == 0x0483]
            if not found:
                raise serial.SerialException("no ST-LINK on USB")
            device = found[0]
        self.link = serial.serial_for_url(device, baudrate=115200, timeout=0,
                                          write_timeout=0.5)
        self.device = device

    def send(self, forward, now):
        """Send one command and take in the status lines the board printed.
        False while the cable is out; the port is retried once a second."""
        if not self.port:
            return True
        try:
            if not self.link:
                if now < self.retry_at:
                    return False
                self.retry_at = now + 1.0
                self.open()
            self.link.write(self.forward if forward else b"0")
            self.text += self.link.read(4096)
        except serial.SerialException:
            if self.link:
                try:
                    self.link.close()
                except serial.SerialException:
                    pass
            self.link = self.report = None
            return False
        *lines, self.text = self.text.split(b"\n")
        for line in lines:
            match = re.match(rb"(SERIAL|BUTTON) \w+=\d cmd=(\d)", line.strip())
            if match:
                self.report = (now, match[1].decode(), int(match[2]))
        return True

    def status(self, now):
        if not self.port:
            return "no car"
        if not self.link:
            return "CAR UNPLUGGED"
        if not self.report or now - self.report[0] > 3.0:
            return "car silent"
        if self.report[1] == "BUTTON":
            return "board ignores serial: flash build/serial/Car_Demo.hex"
        return f"car cmd={self.report[2]}"

    def close(self):
        if self.link:
            self.link.write(b"0")
            self.link.close()
            self.link = None


simulation = {"state": "relaxed"}  # what --simulate sends: relaxed or focused


def simulate_headband(port):
    """Send made-up MuseLog band powers to our own port, following
    simulation["state"], so the whole chain can run without a headband."""
    bels = {"delta": (0.9, 0.9), "theta": (0.5, 0.4), "alpha": (1.0, 0.3),
            "beta": (0.2, 0.7), "gamma": (-0.3, 0.1)}  # (relaxed, focused)
    client = udp_client.SimpleUDPClient("127.0.0.1", port)
    rng = np.random.default_rng()
    while True:
        focused = simulation["state"] == "focused"
        for band, levels in bels.items():
            client.send_message(f"/muse/elements/{band}_absolute",
                                list(levels[focused] + rng.normal(0, 0.05, 4)))
        client.send_message("/muse/elements/horseshoe", [1, 1, 1, 1])
        time.sleep(TICK_S)


def local_ips():
    try:
        found = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except socket.gaierror:
        return "unknown"
    ips = sorted({info[4][0] for info in found} - {"127.0.0.1"})
    return ", ".join(ips) or "unknown"


last_key_time = 0.0


def key():
    """One pending keypress, lower case, or '' (Windows console only). A
    held key auto-repeats, so everything else waiting is dropped and keys
    within 0.7 s of the last accepted one are ignored."""
    global last_key_time
    if not (msvcrt and msvcrt.kbhit()):
        return ""
    pressed = msvcrt.getwch()
    if pressed in "\x00\xe0":  # arrow or function key: drop its code too
        msvcrt.getwch()
        pressed = ""
    while msvcrt.kbhit():
        msvcrt.getwch()
    now = time.monotonic()
    if now - last_key_time < 0.7:
        return ""
    last_key_time = now
    return pressed.lower()


def beep():
    if winsound:
        winsound.Beep(880, 300)
    else:
        print("\a", end="", flush=True)


speech = True  # cleared by --quiet


def say(text):
    """Print the text and, on Windows, also speak it: the wearer has their
    eyes closed for half of the calibration."""
    note(text)
    if speech and sys.platform == "win32":
        script = ("Add-Type -AssemblyName System.Speech; (New-Object "
                  "System.Speech.Synthesis.SpeechSynthesizer).Speak('"
                  + text.replace("'", "''") + "')")
        subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                         creationflags=subprocess.CREATE_NO_WINDOW)


last_shown = 0.0
status_line_open = False  # the console cursor sits on a status line


def show(text):
    """Status on one console line; once a second when output is a file."""
    global last_shown, status_line_open
    if sys.stdout.isatty():
        width = shutil.get_terminal_size().columns - 1
        print("\r" + text[:width].ljust(width), end="", flush=True)
        status_line_open = True
    elif time.monotonic() - last_shown >= 1.0:
        last_shown = time.monotonic()
        print(text, flush=True)


def note(text):
    """A message on its own line, below any status line."""
    global status_line_open
    if status_line_open:
        print()
        status_line_open = False
    print(text, flush=True)


run_log = None  # csv.writer when --log is given


def record(phase, stream, now, ratios, *driving):
    """One --log row: what the headband gave and what the car was told."""
    if run_log:
        values = [f"{10 ** ratios[name]:.4f}" if ratios else ""
                  for name in INDEXES]
        run_log.writerow([f"{time.time():.2f}", phase, *values,
                          *(stream.horseshoe(now) or [""] * 4),
                          *(driving or [""] * 4)])


def contact_text(stream, now):
    if not stream.last_packet or now - stream.last_packet > 2.0:
        return "NO DATA FROM MUSELOG (is it streaming?)"
    contact = stream.horseshoe(now)
    if not contact:
        return ""
    return "contact " + " ".join(f"{name}:{int(value)}"
                                 for name, value in zip(CHANNELS, contact))


def wait_for_signal(stream, wanted, car):
    """Wait until the stream carries a usable index; returns its source."""
    sources = SOURCES if wanted == "auto" else (wanted,)
    recent = {source: collections.deque(maxlen=round(2.0 / TICK_S))
              for source in sources}
    last_good = dict.fromkeys(sources)
    hinted = False
    started = time.monotonic()
    while True:
        now = time.monotonic()
        if key() == "q":
            return None
        car.send(False, now)
        for source in sources:
            recent[source].append(stream.index(source, now) is not None)
            if recent[source][-1]:
                last_good[source] = now
        for position, source in enumerate(sources):
            # The phone delivers in bursts, so "mostly usable for 2 s" counts.
            steady = (len(recent[source]) == recent[source].maxlen and
                      sum(recent[source]) >= 0.75 * recent[source].maxlen)
            # A fallback counts only once every better source has given
            # nothing for 8 s.
            better_dead = all(
                now - (last_good[better] or stream.first_packet or now) > 8.0
                for better in sources[:position])
            if steady and better_dead:
                note(f"Signal found ({source}).")
                if source == "raw" and stream.raw_rate == 64:
                    note("Raw EEG is arriving at 64 Hz, which has no gamma "
                         "band: turn on Full-rate raw EEG in MuseLog's OSC "
                         "settings.")
                return source
        if stream.first_packet:
            show("MuseLog is streaming; waiting for electrode contact.  " +
                 contact_text(stream, now))
        else:
            show("Waiting for MuseLog packets...")
            if not hinted and now - started > 8:
                hinted = True
                note("Nothing yet. Check: phone and PC on the same Wi-Fi, "
                     "Target IP is this PC, the port matches, Start "
                     "Streaming is pressed.")
        time.sleep(TICK_S)


def wait_for_space(stream, car):
    """Hold the car idle until SPACE (True) or Q (False)."""
    if not msvcrt:
        return True
    say("Press space to begin the calibration.")
    while (pressed := key()) != " ":
        if pressed == "q":
            return False
        now = time.monotonic()
        car.send(False, now)
        show(f"{contact_text(stream, now)}  {car.status(now)}")
        time.sleep(TICK_S)
    return True


def collect(stream, source, seconds, car, label):
    """The index over one calibration phase, with the car held idle."""
    values = []
    simulation["state"] = "focused" if label == "focus" else "relaxed"
    end = time.monotonic() + seconds
    while (now := time.monotonic()) < end:
        if key() == "q":
            return None
        car.send(False, now)
        value = stream.index(source, now)
        if value is not None and end - now <= seconds - SETTLE_S:
            values.append(value)
        record(label, stream, now, value)
        show(f"{label}: {end - now:3.0f} s left   {contact_text(stream, now)}"
             f"  {car.status(now)}")
        time.sleep(TICK_S)
    return values


def calibrate(stream, source, car, args):
    """Relaxed and focused levels of the index that separates them best
    (or of --index); None if quit, {} if unusable."""
    seconds = args.calib_seconds
    note(f"\nCalibration, two parts of {seconds:.0f} s. Sit still; keep your "
         "jaw and forehead loose.")
    note("  1. RELAX: eyes closed, breathe slowly, until the beep.")
    note("  2. FOCUS: eyes open, look at the car and count down from 300 in "
         "sevens, until the second beep.")
    if not args.armed and not wait_for_space(stream, car):
        return None
    say("1 of 2. Close your eyes and relax.")
    relaxed = collect(stream, source, seconds, car, "relax")
    if relaxed is None:
        return None
    beep()
    say("\n2 of 2. Open your eyes and focus. Count down from 300 in sevens.")
    focused = collect(stream, source, seconds, car, "focus")
    simulation["state"] = "relaxed"  # so a simulated run starts at rest
    if focused is None:
        return None
    beep()
    enough = (seconds - SETTLE_S) / TICK_S / 2
    if len(relaxed) < enough or len(focused) < enough:
        say("Too little usable signal during the calibration. Check the "
            "electrode contact.")
        return {}
    chosen = choose_index(relaxed, focused, args.index)
    if not chosen:
        say("Calibration failed: focused did not come out above relaxed.")
        return {}
    verdict = ("Calibration done, but the two states overlap a lot; press R "
               "to try again." if chosen["separation"] < 1.5
               else "Calibration done.")
    say(verdict + (" The car is live." if args.armed
                   else " Press space to let the car move."))
    return dict(chosen, source=source)


def choose_index(relaxed, focused, wanted):
    """Levels of the index that best separates the two sets of samples."""
    best = None
    for name in INDEXES if wanted == "auto" else (wanted,):
        low = statistics.median(v[name] for v in relaxed)
        high = statistics.median(v[name] for v in focused)
        spread = 1.4826 * max(
            statistics.median(abs(v[name] - low) for v in relaxed),
            statistics.median(abs(v[name] - high) for v in focused))
        separation = (high - low) / max(spread, 1e-9)
        note(f"  {name:10s} relaxed {10 ** low:.2f}  focused {10 ** high:.2f}"
             f"  separation {separation:.1f}")
        if best is None or separation > best[0]:
            best = (separation, name, low, high)
    separation, name, low, high = best
    if separation <= 0:
        return {}
    note(f"Using {name}.")
    return {"index": name, "relaxed": low, "focused": high,
            "separation": round(separation, 2)}


def drive(stream, calibration, car, args):
    """Run the car from the index; returns the key that ended it (r or q)."""
    armed = args.armed
    forward = False
    smooth = None
    last_valid = 0.0
    weight = 1.0 if args.smooth <= 0 else 1 - math.exp(-TICK_S / args.smooth)
    low, high = calibration["relaxed"], calibration["focused"]
    note("SPACE = start/pause the car   R = recalibrate   Q = quit")
    meter = ""
    tick = started = time.monotonic()
    while True:
        now = time.monotonic()
        if args.simulate:  # 10 s stopped, 10 s forward, and so on
            simulation["state"] = ("focused" if int((now - started) // 10) % 2
                                   else "relaxed")
        pressed = key()
        if pressed == " ":
            armed = not armed
            say("Car is live. Focus to drive, relax to stop." if armed
                else "Paused.")
        elif pressed in ("r", "q", "\x1b"):
            car.send(False, now)
            return "r" if pressed == "r" else "q"
        ratios = stream.index(calibration["source"], now)
        level = ""
        if ratios is None:
            # The phone delivers in bursts: ride through gaps under 0.5 s.
            if now - last_valid > 0.5:
                forward = False
                meter = "no usable signal from the headband"
            if now - last_valid > 2.0:
                smooth = None
        else:
            value = ratios[calibration["index"]]
            last_valid = now
            smooth = value if smooth is None else smooth + weight * (value - smooth)
            level = (smooth - low) / (high - low)
            if level >= args.go:
                forward = True
            elif level <= args.stop:
                forward = False
            filled = round(20 * min(max(level, 0.0), 1.0))
            meter = (f"arousal {level:5.2f} |{'#' * filled}{'.' * (20 - filled)}| "
                     f"{'FORWARD' if forward else 'stop   '}")
        moving = armed and forward
        if not car.send(moving, now):
            # Cable out: the car must not start by itself when it returns.
            armed = args.armed
        record("drive", stream, now, ratios, round(level, 3) if ratios else "",
               int(armed), int(moving), car.status(now))
        show(f"[{'ARMED ' if armed else 'PAUSED'}] {meter}  "
             f"{contact_text(stream, now)}  {car.status(now)}")
        tick += TICK_S
        time.sleep(max(0.0, tick - time.monotonic()))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--osc-port", type=int, default=5000,
                        help="UDP port MuseLog streams to (default 5000)")
    parser.add_argument("--serial", default="auto",
                        help="COM port of the board, 'auto' for the ST-LINK, "
                             "or 'none' to run without the car")
    parser.add_argument("--source", choices=("auto",) + SOURCES, default="auto",
                        help="raw: band powers computed here from /muse/eeg; "
                             "bands: MuseLog's band powers; legacy: "
                             "/person1/eeg (no gamma)")
    parser.add_argument("--index", choices=("auto",) + INDEXES, default="auto",
                        help="muselog: (beta+gamma)/(alpha+theta); beta-alpha: "
                             "beta/alpha; auto: whichever calibration "
                             "separates better")
    parser.add_argument("--calib-seconds", type=float, default=15,
                        help="length of each calibration phase (default 15)")
    parser.add_argument("--reuse", action="store_true",
                        help="skip calibration and use the last one saved")
    parser.add_argument("--go", type=float, default=0.6,
                        help="go forward at this level, 0 relaxed .. 1 focused")
    parser.add_argument("--stop", type=float, default=0.4,
                        help="stop at this level")
    parser.add_argument("--smooth", type=float, default=1.0,
                        help="smoothing time constant in seconds (default 1)")
    parser.add_argument("--armed", action="store_true",
                        help="never wait for SPACE: calibrate at once and "
                             "let the car move")
    parser.add_argument("--log", default="auto",
                        help="CSV with one row per tick; default "
                             "build/muse_run_<time>.csv, 'none' for no log")
    parser.add_argument("--quiet", action="store_true",
                        help="do not speak the prompts")
    parser.add_argument("--power", choices=("normal", "full"), default="normal",
                        help="forward at 75%% PWM (normal) or full power")
    parser.add_argument("--simulate", action="store_true",
                        help="no headband: made-up data calibrates, then "
                             "drives the car forward for 10 s and stops it "
                             "for 10 s, in turn (implies --armed)")
    args = parser.parse_args()
    if args.simulate:
        args.armed = True
        if args.source == "auto":
            args.source = "bands"
    global run_log, speech
    speech = not args.quiet
    if args.log != "none":
        path = Path(args.log)
        if args.log == "auto":
            path = (CALIBRATION.parent /
                    time.strftime("muse_run_%Y%m%d_%H%M%S.csv"))
        path.parent.mkdir(parents=True, exist_ok=True)
        run_log = csv.writer(open(path, "w", newline="", buffering=1))
        run_log.writerow(["time", "phase", *INDEXES, *CHANNELS, "level",
                          "armed", "sent", "car"])
        print(f"Logging every tick to {path}")
    if not args.stop < args.go:
        parser.error("--stop must be below --go")
    if args.calib_seconds < 2 * SETTLE_S:
        parser.error(f"--calib-seconds must be at least {2 * SETTLE_S:.0f}")

    if sys.platform == "win32":
        # Nobody touches the keyboard while driving. Without this Windows
        # sleeps on its idle timer, the commands stop and so does the car.
        # ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)

    car = Car(None if args.serial == "none" else args.serial)
    car.forward = b"2" if args.power == "full" else b"1"
    stream = MuseStream(args.osc_port)
    stream.start()
    if args.simulate:
        threading.Thread(target=simulate_headband, args=(args.osc_port,),
                         daemon=True).start()
        say("Simulated headband. After a mock calibration the car moves "
            "forward for ten seconds and stops for ten seconds, in turn. "
            "Press Q to quit.")
    print(f"Listening for MuseLog on UDP {args.osc_port}; in its OSC settings "
          f"set Target IP to one of: {local_ips()}")
    try:
        source = wait_for_signal(stream, args.source, car)
        calibration = None
        if source and args.reuse and CALIBRATION.is_file():
            saved = json.loads(CALIBRATION.read_text(encoding="utf-8"))
            if (saved.get("source") == source and saved.get("index") in
                    (INDEXES if args.index == "auto" else (args.index,))):
                calibration = saved
                note(f"Using the saved calibration ({saved['index']}).")
        while source:
            if not calibration:
                calibration = calibrate(stream, source, car, args)
                if calibration is None:
                    break
                if not calibration:
                    note("Calibrating again. Q quits.")
                    continue
                CALIBRATION.parent.mkdir(parents=True, exist_ok=True)
                CALIBRATION.write_text(json.dumps(calibration, indent=2),
                                       encoding="utf-8")
            if drive(stream, calibration, car, args) == "q":
                break
            calibration = None
    except KeyboardInterrupt:
        pass
    finally:
        try:
            car.close()
        except serial.SerialException:
            pass
    note("Stopped.")


if __name__ == "__main__":
    main()
