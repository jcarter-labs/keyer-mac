"""Masterplan 3.5 (early): all six methods route as signals; calls while
disconnected are dropped with a note; a port conflict does not abort."""

import socket
import xmlrpc.client

import pytest

from keyer_mac.bridge import Bridge


@pytest.fixture
def bridge(qtbot):
    state = {"connected": True}
    b = Bridge(host="127.0.0.1", port=0, is_connected=lambda: state["connected"])
    assert b.start()
    b.state = state
    yield b
    b.stop()


def proxy(b):
    return xmlrpc.client.ServerProxy(f"http://127.0.0.1:{b.port}", allow_none=True)


def test_each_method_emits_its_signal(bridge, qtbot):
    p = proxy(bridge)
    with qtbot.waitSignal(bridge.send_string, timeout=1000) as s:
        assert p.k1elsendstring("CQ TEST") is True
    assert s.args == ["CQ TEST"]
    with qtbot.waitSignal(bridge.send_blended, timeout=1000) as s:
        p.sendblended("AR")
    assert s.args == ["AR"]
    with qtbot.waitSignal(bridge.set_speed, timeout=1000) as s:
        p.setspeed(24)
    assert s.args == [24]
    with qtbot.waitSignal(bridge.tune_on, timeout=1000):
        p.tuneon()
    with qtbot.waitSignal(bridge.tune_off, timeout=1000):
        p.tuneoff()
    with qtbot.waitSignal(bridge.clear_buffer, timeout=1000):
        p.clearbuffer()


@pytest.mark.parametrize("bad", [5, 7, 36, 35, 0, "20", 20.0])
def test_setspeed_rejects_anything_but_even_6_to_34(bridge, bad):
    with pytest.raises(xmlrpc.client.Fault):
        proxy(bridge).setspeed(bad)


def test_calls_while_disconnected_are_dropped_with_a_note(bridge, qtbot):
    bridge.state["connected"] = False
    with qtbot.waitSignal(bridge.note, timeout=1000) as n:
        assert proxy(bridge).k1elsendstring("X") is True
    assert "dropped" in n.args[0] and "disconnected" in n.args[0]
    with qtbot.assertNotEmitted(bridge.send_string, wait=100):
        proxy(bridge).k1elsendstring("X")


def test_port_in_use_does_not_abort(qtbot):
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    try:
        b = Bridge(host="127.0.0.1", port=blocker.getsockname()[1])
        with qtbot.waitSignal(b.note, timeout=1000) as n:
            assert b.start() is False
        assert "unavailable" in n.args[0]
    finally:
        blocker.close()
