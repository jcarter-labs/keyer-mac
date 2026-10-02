"""Task 1.3 (Constitution rule 8): $HOME is redirected for the whole suite,
and a test that touches the real home config fails.

The failing case runs in a throwaway pytest subprocess whose "real" home is
a temp directory, so nothing here can touch the operator's actual files."""

import os
import subprocess
import sys
from pathlib import Path

CONFTEST = Path(__file__).with_name("conftest.py")


def test_home_is_the_temp_dir():
    assert "keyer_mac_test_home_" in str(Path.home())
    assert os.path.expanduser("~/.keyer-mac.json").startswith(str(Path.home()))


def _run_inner(tmp_path: Path, body: str):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "conftest.py").write_text(CONFTEST.read_text())
    (proj / "test_inner.py").write_text(body)
    fake_real_home = tmp_path / "realhome"
    fake_real_home.mkdir()
    env = dict(os.environ, HOME=str(fake_real_home), ORIG_HOME=str(fake_real_home))
    env.pop("KEYER_MAC_CONFIG_PATH", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(proj)],
        capture_output=True, text=True, env=env, cwd=proj,
    )


def test_touching_the_real_home_config_fails(tmp_path):
    body = (
        "import os\n"
        "def test_bad():\n"
        "    open(os.environ['ORIG_HOME'] + '/.keyer-mac.json', 'w').write('x')\n"
    )
    r = _run_inner(tmp_path, body)
    assert r.returncode != 0, r.stdout
    assert "real ~/.keyer-mac.json" in r.stdout


def test_a_clean_test_passes(tmp_path):
    r = _run_inner(tmp_path, "def test_ok():\n    assert True\n")
    assert r.returncode == 0, r.stdout
