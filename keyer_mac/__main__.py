"""keyer-mac entry point: `python3 -m keyer_mac`.

KEYER_MAC_AUTOQUIT=1 prints each status line as it appears and exits once the
scan resolves (used by tools/live_smoke.py). KEYER_MAC_BRIDGE_HOST overrides the
XMLRPC bind address (default 0.0.0.0; tools use 127.0.0.1 to avoid a firewall prompt).
"""

import logging
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from keyer_mac.ui import MainWindow


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    app = QApplication(sys.argv)
    win = MainWindow(start_bridge=True, bridge_host=os.environ.get("KEYER_MAC_BRIDGE_HOST", "0.0.0.0"))
    autoquit = os.environ.get("KEYER_MAC_AUTOQUIT") == "1"
    shown = 0

    def watch():
        nonlocal shown
        while shown < len(win.lines):
            print(win.lines[shown], flush=True)
            shown += 1
        if autoquit and win.result:
            win.shutdown()
            app.quit()

    if autoquit:
        poll = QTimer()
        poll.timeout.connect(watch)
        poll.start(50)
        QTimer.singleShot(25000, lambda: (win.shutdown(), app.quit()))
    win.show()
    win.start_scan()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
