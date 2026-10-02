"""Stage 2.5 entry: `python3 -m keyer_mac.bare` shows the bare window.

With KEYER_MAC_BARE_AUTOQUIT=1 it prints every status line as it appears and
exits once the scan resolves (used by tools/live_bare_window.py).
"""

import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from keyer_mac.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    autoquit = os.environ.get("KEYER_MAC_BARE_AUTOQUIT") == "1"
    shown = 0

    def watch():
        nonlocal shown
        while shown < len(win.lines):
            print(win.lines[shown], flush=True)
            shown += 1
        if autoquit and win.result:
            win.shutdown()
            app.quit()

    poll = QTimer()
    poll.timeout.connect(watch)
    poll.start(50)
    win.show()
    win.start_scan()
    if autoquit:
        QTimer.singleShot(20000, lambda: (win.shutdown(), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
