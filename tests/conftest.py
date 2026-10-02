"""Shared test setup.

QT_QPA_PLATFORM=offscreen must be set before any PyQt6 import happens,
since Qt reads it at platform-plugin init time — setting it here, at
the top of conftest.py, guarantees that regardless of test collection
order (Constitution rule 10: tests stay headless, no real display).
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

# Constitution rule 8 / Task 1.3: tests never touch the operator's real data.
# Snapshot the real home's config before redirecting $HOME, and fail any test
# that changes it. (stat only; the real file is never read or written.)
REAL_HOME = Path.home()
REAL_CONFIG = REAL_HOME / ".keyer-mac.json"
_FAKE_HOME = Path(tempfile.mkdtemp(prefix="keyer_mac_test_home_"))
os.environ["HOME"] = str(_FAKE_HOME)
os.environ.setdefault("KEYER_MAC_CONFIG_PATH", str(_FAKE_HOME / ".keyer-mac.json"))


def config_signature(path: Path):
    """(exists, mtime_ns, size) of a file, or (False, 0, 0)."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return (False, 0, 0)
    return (True, st.st_mtime_ns, st.st_size)


_REAL_SIGNATURE = config_signature(REAL_CONFIG)


@pytest.fixture(autouse=True)
def home_is_redirected_and_untouched():
    """Assert before and after every test: $HOME is the temp dir and the
    real ~/.keyer-mac.json is unchanged."""
    assert Path.home() == _FAKE_HOME, "HOME is not redirected to the test temp dir"
    assert os.path.expanduser("~/.keyer-mac.json").startswith(str(_FAKE_HOME))
    assert Path(os.environ["KEYER_MAC_CONFIG_PATH"]) != REAL_CONFIG
    yield
    assert config_signature(REAL_CONFIG) == _REAL_SIGNATURE, \
        "a test changed the real ~/.keyer-mac.json (rule 8)"


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Every test that builds a QWidget (WinKeyer, Settings) needs a
    QApplication to already exist — source relied on module-level
    bootstrap for this, which tests intentionally don't trigger."""
    app = QApplication.instance() or QApplication([])
    yield app
