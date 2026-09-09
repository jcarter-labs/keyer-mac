"""Shared test setup.

QT_QPA_PLATFORM=offscreen must be set before any PyQt6 import happens,
since Qt reads it at platform-plugin init time — setting it here, at
the top of conftest.py, guarantees that regardless of test collection
order (Constitution rule 10: tests stay headless, no real display).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Every test that builds a QWidget (WinKeyer, Settings) needs a
    QApplication to already exist — source relied on module-level
    bootstrap for this, which tests intentionally don't trigger."""
    app = QApplication.instance() or QApplication([])
    yield app
