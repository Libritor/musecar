"""Stand-in for the board, for testing the bridge without the car: a TCP
server speaking the firmware's serial protocol. Point the bridge at it with
--serial socket://127.0.0.1:7777.

Like Motor_ControlSerial: ASCII 0-4 set the command, 500 ms without one
goes idle and back to BUTTON reports, status lines once a second and on
every change. Prints each command change with a time stamp.

    python tools/fake_board.py            # port 7777, until Ctrl+C
    python tools/fake_board.py 7777 60    # port, seconds
"""

import socket
import sys
import time

DUTY = {0: (0, 0), 1: (22500, 22500), 2: (30000, 30000), 3: (7500, 22500),
        4: (22500, 7500)}


def serve(port, seconds):
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    print(f"fake board listening on socket://127.0.0.1:{port}", flush=True)
    start = time.monotonic()
    while not seconds or time.monotonic() - start < seconds:
        server.settimeout(1.0)
        try:
            link, _ = server.accept()
        except socket.timeout:
            continue
        link.setblocking(False)
        t0 = time.monotonic()
        print(f"{t0 - start:7.2f} connected", flush=True)
        command, active, last_byte, last_report = 0, False, 0.0, 0.0
        while not seconds or time.monotonic() - start < seconds:
            now = time.monotonic()
            try:
                data = link.recv(4096)
                if not data:
                    print(f"{now - start:7.2f} peer closed", flush=True)
                    break
            except BlockingIOError:
                data = b""
            except ConnectionError:
                print(f"{now - start:7.2f} peer reset", flush=True)
                break
            new = command
            for byte in data:
                if 48 <= byte <= 52:
                    new, active, last_byte = byte - 48, True, now
            if active and now - last_byte > 0.5:
                active, new = False, 0
                print(f"{now - start:7.2f} timeout -> idle", flush=True)
            if new != command:
                command = new
                print(f"{now - start:7.2f} cmd={command}", flush=True)
                last_report = 0.0
            if now - last_report >= 1.0:
                last_report = now
                left, right = DUTY[command]
                kind = f"SERIAL sig={command}" if active else "BUTTON raw=0"
                try:
                    link.send(f"{kind} cmd={command} ccr3={left} ccr4={right}\r\n"
                              f"PWM pclk=16000000 psc=0 arr=29999 ccr3={left} "
                              f"ccr4={right} cr1=1 ccer=4352 ccmr2=26728 "
                              f"moder=10486357 afr=4352 odr={6 if command else 0}\r\n"
                              .encode())
                except OSError:
                    pass
            time.sleep(0.002)
        link.close()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 7777,
          float(sys.argv[2]) if len(sys.argv) > 2 else 0)
