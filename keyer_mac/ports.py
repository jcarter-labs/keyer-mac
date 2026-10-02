"""Serial-port discovery and selection (masterplan Tech, module 2).

Pure functions over pyserial-style port objects (anything with `.device`,
`.vid`, `.pid`), so they are unit-testable on fake lists. No I/O here:
`list_ports()` is the one thin wrapper over pyserial's `comports()`.

Rules (Spec feature 1):
- Only ports with USB ID 1a86:7523 (the WK-mini's WCH CH340) are ever
  auto-probed; other ports are listed but never touched, so unrelated serial
  devices are not disturbed.
- Virtual ports (no USB vendor id: cu.debug-console, cu.Bluetooth-Incoming-
  Port, paired Bluetooth audio) are never auto-selected or saved.
- macOS names the port by USB location, so a saved name is only a first guess.
"""

from __future__ import annotations

WK_VID = 0x1A86
WK_PID = 0x7523


def list_ports(include_links: bool = True):
    from serial.tools.list_ports import comports

    return list(comports(include_links=include_links))


def is_virtual(port) -> bool:
    return getattr(port, "vid", None) is None


def is_winkeyer_candidate(port) -> bool:
    return getattr(port, "vid", None) == WK_VID and getattr(port, "pid", None) == WK_PID


def probe_order(ports, saved: str | None = None, manual: str | None = None) -> list[str]:
    """Devices to try, best first, without duplicates.

    manual (picked/typed by the user) first, even if virtual: the user asked.
    saved next, only if it is currently present and not virtual.
    Then every WK-mini candidate, in the order given.
    """
    present = {p.device: p for p in ports}
    order: list[str] = []

    def add(device):
        if device and device not in order:
            order.append(device)

    if manual:
        add(manual)
    if saved and saved in present and not is_virtual(present[saved]):
        add(saved)
    for p in ports:
        if is_winkeyer_candidate(p):
            add(p.device)
    return order


def should_save(device: str, ports) -> bool:
    """A device may be saved as `device` only if it is a present, non-virtual port.
    (The caller also saves only after a successful handshake.)"""
    for p in ports:
        if p.device == device:
            return not is_virtual(p)
    return False
