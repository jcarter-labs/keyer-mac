"""Masterplan 3.1: defaults, round-trip, key 6 ignored, bad JSON kept as .bad.
Every path is under tmp_path (rule 8)."""

import json

import pytest

from keyer_mac import config


def test_missing_file_gives_defaults(tmp_path):
    cfg = config.load(tmp_path / "nope.json")
    assert cfg == config.defaults()
    assert cfg["speed"] == 20 and cfg["mode_register"] == "11001110"
    assert [cfg[k] for k in "12345"] == [""] * 5


def test_round_trip(tmp_path):
    p = tmp_path / "c.json"
    cfg = config.defaults()
    cfg.update(device="/dev/cu.usbserial-1", speed=24, mode_register="11011110")
    cfg.update({"1": "CQ TEST", "5": "73"})
    config.save(cfg, p)
    assert config.load(p) == cfg
    assert not (tmp_path / "c.json.tmp").exists()


def test_key_6_and_unknown_keys_are_ignored_then_dropped_on_save(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"device": "d", "1": "A", "6": "OLD", "junk": 1, "mode_register": "11011110"}))
    cfg = config.load(p)
    assert cfg["1"] == "A" and "6" not in cfg and "junk" not in cfg
    config.save(cfg, p)
    saved = json.loads(p.read_text())
    assert "6" not in saved and "junk" not in saved


def test_old_v1_0_file_without_speed_gets_default_speed(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"device": "/dev/x", "1": "hi", "6": "", "mode_register": "11011110"}))
    cfg = config.load(p)
    assert cfg["speed"] == 20 and cfg["1"] == "hi" and cfg["mode_register"] == "11011110"


@pytest.mark.parametrize("bad_speed", [5, 7, 35, 36, 0, "20", 20.0, None, True])
def test_invalid_speed_falls_back_to_20(tmp_path, bad_speed):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"speed": bad_speed}))
    assert config.load(p)["speed"] == 20


@pytest.mark.parametrize("bad_mode", ["", "1100111", "110011101", "1100110x", 5, None])
def test_invalid_mode_register_falls_back(tmp_path, bad_mode):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"mode_register": bad_mode}))
    assert config.load(p)["mode_register"] == "11001110"


def test_bad_json_becomes_dot_bad_plus_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json")
    assert config.load(p) == config.defaults()
    assert (tmp_path / "c.json.bad").read_text() == "{not json"


def test_env_override_and_default_path(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "x.json"))
    assert config.config_path() == tmp_path / "x.json"
    monkeypatch.delenv("KEYER_MAC_CONFIG_PATH")
    assert "keyer_mac_test_home_" in str(config.config_path())   # HOME is redirected (rule 8)


def test_mode_register_int():
    assert config.mode_register_int(config.defaults()) == 0b11001110
