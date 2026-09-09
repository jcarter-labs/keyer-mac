#!/usr/bin/env python3
"""Task 2 live diagnostic: proves the WinKeyer serial protocol against real
hardware before Task 3 ports the WinKeyer class around it. Administrative
commands only (host open/close, POTSET, pot-speed query) — never calls
send()/sendblended(), which would key a connected radio.

Protocol bytes and serial parameters are taken directly from
pywinkeyerserial/winkeyerserial/__main__.py (host_init, host_open,
host_close, potspeed) to prove the exact sequence this project will port.

Usage: python3 tools/winkeyer_diagnostic.py /dev/cu.usbserial-8340
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


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <serial-device>")
        return 2
    device = sys.argv[1]

    print(f"Opening {device} at 1200/8N2, DSR/DTR on...")
    port = open_port(device)
    if not port.is_open:
        print("FAIL: port did not open")
        return 1
    print("PASS: port open")

    try:
        print("\n-- host_open sequence --")
        print("host_close (0x00 0x03) — defensive reset, matches source's host_open()")
        port.write(b"\x00\x03")

        print("Waiting 1s for keyer reset...")
        time.sleep(1)

        print("host_open (0x00 0x02)")
        port.write(b"\x00\x02")
        time.sleep(0.5)
        version = port.read(255)
        if version == b"":
            print("FAIL: no version response — wrong port, or WinKeyer not responding")
            return 1
        print(f"PASS: version response = {version!r} (hex: {version.hex()})")

        print("\n-- POTSET (0x05 0x05 0x32 0x00): min=5 WPM, range=50 WPM (5-55) --")
        port.write(b"\x05\x05\x32\x00")
        time.sleep(0.2)

        print("Requesting pot speed (0x07)")
        port.write(b"\x07")
        time.sleep(0.3)
        pot_response = port.read(255)
        if pot_response == b"":
            print("FAIL: no pot-speed response")
            return 1
        raw = pot_response[0]
        is_pot_byte = (raw & 0xC0) == 0x80
        print(f"PASS: raw byte = 0x{raw:02x} ({raw:#010b})")
        if is_pot_byte:
            print(f"      decoded as pot-speed byte -> speed = {raw - 123} WPM")
        else:
            print("      NOTE: top 2 bits aren't '10' — not a pot-speed byte per source's "
                  "decode rule; device may lack a speed pot (source's own docstring warns "
                  "not all K1EL keyers have one)")

        print("\n-- host_close (0x00 0x03) — leave device in a clean state --")
        port.write(b"\x00\x03")
        time.sleep(0.1)

        print("\nRESULT: PASS — protocol round-trip proven against real hardware")
        return 0
    finally:
        port.close()
        print(f"\nClosed {device}")


if __name__ == "__main__":
    raise SystemExit(main())
