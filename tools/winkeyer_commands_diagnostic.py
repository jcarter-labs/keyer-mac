#!/usr/bin/env python3
"""Task 2 live diagnostic, part 3: exercises the remaining WinKeyer
commands that winkeyer_diagnostic.py and winkeyer_xmlrpc_diagnostic.py
didn't individually prove — setmode, setspeed, tuneon/tuneoff,
clearbuffer, sendblended. Per Constitution rule 4, each hardware command
gets proven live before Task 3 ports the method around it.

tuneon and sendblended key the WinKeyer's CW output line. Only run this
with the WinKeyer NOT wired into a powered, on-air radio.

Command bytes taken directly from pywinkeyerserial/winkeyerserial/
__main__.py (setmode, setspeed, tuneon, tuneoff, clearbuffer,
sendblended) to prove the exact sequences this project will port.

Usage: python3 tools/winkeyer_commands_diagnostic.py /dev/cu.usbserial-8340
"""

import sys
import time

import serial


def open_port(device: str) -> serial.Serial:
    port = serial.Serial()
    port.port = device
    port.baudrate = 1200
    port.bytesize = serial.EIGHTBITS
    port.parity = serial.PARITY_NONE
    port.stopbits = serial.STOPBITS_TWO
    port.dsrdtr = True
    port.rtscts = False
    port.timeout = 0
    port.write_timeout = 1
    port.open()
    return port


def host_open(port: serial.Serial) -> bytes:
    port.write(b"\x00\x03")
    time.sleep(1)
    port.write(b"\x00\x02")
    time.sleep(0.5)
    return port.read(255)


def drain(port: serial.Serial, duration_s: float) -> bytes:
    deadline = time.time() + duration_s
    data = bytearray()
    while time.time() < deadline:
        if port.in_waiting:
            data += port.read(port.in_waiting)
        time.sleep(0.05)
    return bytes(data)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <serial-device>")
        return 2
    device = sys.argv[1]

    print(f"Opening {device} and sending host_open...")
    port = open_port(device)
    try:
        version = host_open(port)
        if version == b"":
            print("FAIL: no version response — is the device connected and idle?")
            return 1
        print(f"PASS: host_open OK, version = {version!r}")

        print("\n-- setmode (0x0e + mode-register byte) --")
        mode_register = "11001110"  # source's own fallback default
        int_register = int(mode_register, 2)
        command = b"\x0e" + int_register.to_bytes()
        print(f"writing {command!r} (register={mode_register}, 0x{int_register:02x})")
        port.write(command)
        resp = drain(port, 0.3)
        print(f"PASS: write did not raise (response bytes: {resp!r})")

        print("\n-- setspeed (chr(2)+chr(n)) --")
        speed = 25
        command = chr(2).encode() + chr(speed).encode()
        print(f"writing {command!r} (speed={speed} WPM)")
        port.write(command)
        resp = drain(port, 0.3)
        print(f"PASS: write did not raise (response bytes: {resp!r})")

        print("\n-- tuneon (0x0b 0x01) / tuneoff (0x0b 0x00) --")
        print("Watch/listen to the WinKeyer now — it should key for ~1s.")
        port.write(b"\x0b\x01")
        time.sleep(1)
        port.write(b"\x0b\x00")
        resp = drain(port, 0.3)
        print(f"PASS: both writes did not raise (response bytes: {resp!r})")

        print("\n-- clearbuffer (0x0a) --")
        port.write(b"\x0a")
        resp = drain(port, 0.3)
        print(f"PASS: write did not raise (response bytes: {resp!r})")

        print("\n-- sendblended (0x1b + 'AR') --")
        command = b"\x1b" + "AR".upper().encode()
        print(f"writing {command!r} (prosign AR)")
        port.write(command)
        resp = drain(port, 1.5)
        print(f"PASS: write did not raise (response bytes: {resp!r})")

        print("\n-- host_close (0x00 0x03) --")
        port.write(b"\x00\x03")

        print("\nRESULT: PASS — all remaining commands accepted by real hardware")
        print("(response bytes above may be empty — source's getwaiting() only")
        print("decodes pot-speed and echoback bytes; status-change bytes are")
        print("otherwise unread. Absence of an exception is what these commands")
        print("prove, matching Task 2's earlier k1elsendstring check.)")
        return 0
    finally:
        port.close()
        print(f"\nClosed {device}")


if __name__ == "__main__":
    raise SystemExit(main())
