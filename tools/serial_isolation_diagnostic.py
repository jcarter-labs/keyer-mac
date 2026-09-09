#!/usr/bin/env python3
"""Isolates why host_open() sees no version response from the WK-mini
(troubleshooting-transcript.md turns 19-30, deviation-log.md #8's
"Unverified" section). winkeyer_diagnostic.py already proves the protocol
sequence on a single successful trial; this script instead attacks the
specific hypotheses raised in that unresolved section, each as its own
stage so a failure points at one variable, not a bundle:

  1. Port inventory        - exactly one usbserial device present? (rules
                              out "wrong port" / a stray second adapter)
  2. Contention check       - is anything already holding the port?
  3. Soak test (N trials)   - open/host_open/read, repeated back-to-back.
                              Distinguishes "always fails" (points at DTR
                              reset or the device itself) from
                              "intermittent" (points at USB power
                              management / timing) - the operator's own
                              observation ("100% now, used to be
                              intermittent") is the key discriminator.
  4. DTR strategy sweep     - on a fresh open, try three DTR handling
                              variants back-to-back and report which (if
                              any) gets a response. Isolates cause #1.
  5. Multi-read probe       - instead of one read(255) after a fixed
                              sleep, poll read(255) up to 20x/50ms and
                              report which poll (if any) catches bytes.
                              Targets the documented pyserial-on-macOS
                              "dropped initial read" bug (GitHub
                              pyserial/pyserial#410) as an alternative to
                              "settle time too short" for cause #3.

Deliberately does not touch send()/sendblended()/tuneon (would key a
connected radio) - same boundary as the existing tools/ diagnostics.

Usage: python3 tools/serial_isolation_diagnostic.py /dev/cu.usbserial-8340 [--trials N]
"""

import argparse
import subprocess
import sys
import time
from glob import glob

import serial


def port_inventory(expected_device: str) -> bool:
    print("-- Stage 1: port inventory --")
    candidates = sorted(glob("/dev/cu.usbserial*"))
    print(f"  found: {candidates or '(none)'}")
    if expected_device not in candidates:
        print(f"  FAIL: {expected_device} not present")
        return False
    if len(candidates) > 1:
        print("  WARN: more than one usbserial device present - "
              "verify you're targeting the right one")
    else:
        print("  PASS: exactly one usbserial device, matches target")
    return True


def contention_check(device: str) -> bool:
    print("-- Stage 2: contention check --")
    try:
        out = subprocess.run(["lsof", device], capture_output=True, text=True, timeout=5)
    except FileNotFoundError:
        print("  SKIP: lsof not available")
        return True
    holders = [line for line in out.stdout.splitlines()[1:] if line.strip()]
    if holders:
        print(f"  FAIL: port already held:\n    " + "\n    ".join(holders))
        return False
    print("  PASS: nothing else holds the port")
    return True


def open_port(device: str, dtr_mode: str = "code_default") -> serial.Serial:
    """dtr_mode mirrors host_init()'s params except for the DTR handling,
    which the sweep in stage 4 varies deliberately."""
    port = serial.Serial()
    port.port = device
    port.baudrate = 1200
    port.bytesize = serial.EIGHTBITS
    port.parity = serial.PARITY_NONE
    port.stopbits = serial.STOPBITS_TWO
    port.rtscts = False
    port.timeout = 0
    port.write_timeout = 1
    if dtr_mode == "code_default":
        port.dsrdtr = True
    else:
        port.dsrdtr = False
    port.open()
    if dtr_mode == "explicit_pulse":
        port.dtr = False
        time.sleep(0.3)
        port.dtr = True
    return port


def multi_read_probe(port: serial.Serial, attempts: int = 20, interval_s: float = 0.05) -> tuple:
    """Polls instead of a single fixed-delay read(255). Returns
    (bytes_or_None, which_attempt_1_indexed_or_None)."""
    for i in range(1, attempts + 1):
        data = port.read(255)
        if data:
            return data, i
        time.sleep(interval_s)
    return b"", None


def one_trial(device: str, dtr_mode: str, label: str) -> bool:
    print(f"  [{label}] opening with dtr_mode={dtr_mode}...")
    try:
        port = open_port(device, dtr_mode)
    except serial.SerialException as err:
        print(f"  [{label}] FAIL: could not open port: {err}")
        return False
    try:
        port.write(b"\x00\x03")  # host_close, defensive reset (matches host_open())
        time.sleep(1)
        port.write(b"\x00\x02")  # host_open
        data, which_attempt = multi_read_probe(port)
        if not data:
            print(f"  [{label}] FAIL: no response after 20 polls (1.0s total)")
            return False
        print(f"  [{label}] PASS: response={data!r} on poll #{which_attempt} "
              f"(~{which_attempt * 0.05:.2f}s after write)")
        port.write(b"\x00\x03")  # leave device closed/clean
        return True
    finally:
        port.close()


def soak_test(device: str, trials: int) -> None:
    print(f"-- Stage 3: soak test ({trials} trials, code_default DTR handling) --")
    results = []
    for n in range(1, trials + 1):
        results.append(one_trial(device, "code_default", f"trial {n}/{trials}"))
        time.sleep(0.5)
    passed = sum(results)
    print(f"  RESULT: {passed}/{trials} passed")
    if passed == 0:
        print("  -> consistent 100% failure: points at DTR reset or the device "
              "itself, not USB power management timing")
    elif passed == trials:
        print("  -> consistent 100% success: the earlier failure may have been "
              "transient (cold power-on) or specific to the app's timer/Qt "
              "context rather than the serial layer")
    else:
        print("  -> intermittent: points at USB power management / timing, "
              "not a hard fault")


def dtr_sweep(device: str) -> None:
    print("-- Stage 4: DTR strategy sweep --")
    variants = [
        ("code_default", "dsrdtr=True (current host_init() behavior)"),
        ("no_dtr", "dsrdtr=False, no explicit toggle"),
        ("explicit_pulse", "dsrdtr=False, explicit dtr low->high pulse before writing"),
    ]
    for mode, desc in variants:
        print(f"  variant: {desc}")
        one_trial(device, mode, mode)
        time.sleep(0.5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("device")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()

    if not port_inventory(args.device):
        return 1
    if not contention_check(args.device):
        return 1

    soak_test(args.device, args.trials)
    dtr_sweep(args.device)

    print("\n-- Manual stages not automatable from here --")
    print("  Stage 6 (adapter/driver loopback): jumper TX to RX at the "
          "adapter's connector (no WinKeyer attached), then re-run this "
          "script - if it now gets responses, they're just this script's "
          "own writes echoing back, confirming the adapter+macOS driver "
          "path works and the fault is downstream at the WinKeyer.")
    print("  Stage 7 (WK-mini alive check): unplug USB, key the paddle "
          "directly. Per K1EL docs, standalone mode works without a host "
          "connection. Also watch the WK-mini's status LED on power-up - "
          "troubleshooting-transcript.md turn 20 noted 'no LED blinking "
          "inside wkmini', which was never followed up and would indicate "
          "the keyer itself isn't booting, independent of USB/timing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
