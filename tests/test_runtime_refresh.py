"""A standing charge or discharge goes out again (0.3.6).

The hub drops an ExtAPI command without a word when a slot of its own
portal schedule begins, or when its settings change: no NAK, the verdict
stays "ack". The driver published only when the command changed, so the
hub ran on its own logic for hours while the setpoint said "hold". A
charge or discharge that has stood REFRESH_S now goes out again: with the
next write when the setpoint is being written (EMS writes every tick),
from the driver's own timer when nothing writes. Never ``auto``, never on
top of an open transaction, and a NAK keeps its own handling (0.2.1).
"""

import asyncio
import json
import sys
import types

# runtime.py imports Home Assistant for type names only; stub the two modules.
for name, attrs in (("homeassistant", {}),
                    ("homeassistant.config_entries", {"ConfigEntry": object}),
                    ("homeassistant.core", {"HomeAssistant": object})):
    mod = sys.modules.setdefault(name, types.ModuleType(name))
    for key, value in attrs.items():
        setattr(mod, key, value)

from custom_components.ferroamp_control import mqtt_control  # noqa: E402
from custom_components.ferroamp_control import runtime as runtime_mod  # noqa: E402
from custom_components.ferroamp_control.ack_tracker import (  # noqa: E402
    KIND_RESPONSE,
    KIND_RESULT,
    PENDING_TTL_S,
)
from custom_components.ferroamp_control.const import REFRESH_OFFSET_S, REFRESH_S  # noqa: E402
from custom_components.ferroamp_control.runtime import FerroampControlRuntime  # noqa: E402

run = asyncio.run


class _Clock:
    """Both of the runtime's clocks, by hand: the wall clock the tracker
    stamps with and the monotonic one the refresh measures with."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now


class _Timers:
    """Home Assistant's call_later, by hand: time passes when the test says."""

    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self._armed: list[dict] = []

    def call_later(self, hass, delay, action):
        timer = {"due": self.clock.now + delay, "action": action, "live": True}
        self._armed.append(timer)

        def cancel() -> None:
            timer["live"] = False
        return cancel

    @property
    def live(self) -> list[dict]:
        return [t for t in self._armed if t["live"]]

    def advance(self, seconds: float) -> None:
        """Let ``seconds`` pass, firing every timer that falls due, in order."""
        end = self.clock.now + seconds
        while True:
            due = sorted((t for t in self.live if t["due"] <= end), key=lambda t: t["due"])
            if not due:
                break
            timer = due[0]
            timer["live"] = False
            self.clock.now = max(self.clock.now, timer["due"])
            run(timer["action"](None))
        self.clock.now = end


def _runtime(monkeypatch, **kw):
    clock = _Clock()
    timers = _Timers(clock)
    sent = []

    async def fake_send(hass, base_topic, name, watts=None):
        payload = mqtt_control.build_payload(name, watts)
        payload["transId"] = f"t{len(sent) + 1}"
        sent.append((name, watts))
        return payload

    monkeypatch.setattr(mqtt_control, "async_send", fake_send)
    monkeypatch.setattr(runtime_mod, "time", clock)
    monkeypatch.setattr(runtime_mod, "_call_later", timers.call_later)
    args = dict(hass=object(), entry_id="e1", prefix="ferroamp", base_topic="extapi",
                max_charge_w=5000.0, max_discharge_w=5000.0, control_enabled=True)
    args.update(kw)
    return FerroampControlRuntime(**args), sent, timers


def _answer(trans_id, status, msg):
    return json.dumps({"transId": trans_id, "status": status, "msg": msg})


def _hub_takes(rt, n):
    """The hub's receipt and, ten seconds on in real life, its result."""
    rt.handle_answer(KIND_RESPONSE, _answer(f"t{n}", "ack", "sending cmd to ESOs"))
    rt.handle_answer(KIND_RESULT, _answer(f"t{n}", "ack", "all ESOs have changed setting"))


def _write(rt, watts):
    """EMS's number.set_value: the setpoint, then async_apply."""
    rt.setpoint_w = watts
    run(rt.async_apply())


def test_the_timer_sends_a_standing_hold_again_when_nothing_writes(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, 100.0)                          # EMS's hold token
    _hub_takes(rt, 1)
    given_at = rt.tracker.last_command["at"]
    # Nothing writes: REFRESH_S plus the offset after the write, then
    # every REFRESH_S.
    timers.advance(REFRESH_S + REFRESH_OFFSET_S - 1)
    assert sent == [("charge", 100)]
    timers.advance(1)
    assert sent == [("charge", 100)] * 2
    # The verdict stands through the refresh; the command still dates
    # from when it was given.
    assert rt.tracker.following is True and rt.tracker.status == "ack"
    assert rt.tracker.last_command["at"] == given_at
    assert rt.tracker.last_command["trans_id"] == "t2"
    assert rt.tracker.last_command["refreshed_at"] == given_at + REFRESH_S + REFRESH_OFFSET_S
    _hub_takes(rt, 2)
    timers.advance(REFRESH_S)
    assert sent == [("charge", 100)] * 3
    # The daily report's numbers are untouched.
    assert rt.tracker.naks == 0 and rt._commanded is True


def test_a_write_after_refresh_s_sends_the_same_discharge_again(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, -2500.0)
    _hub_takes(rt, 1)
    timers.advance(REFRESH_S - REFRESH_OFFSET_S - 1)
    _write(rt, -2500.0)                        # too soon: deduped as before
    assert sent == [("discharge", 2500)]
    timers.advance(1)
    _write(rt, -2500.0)                        # stood long enough
    assert sent == [("discharge", 2500)] * 2
    _hub_takes(rt, 2)
    # EMS writing every five minutes, a moment early or late: each write
    # is the refresh, and the timer, started over by every write, never
    # fires on its own.
    for step in (REFRESH_S - 1, REFRESH_S + 1, REFRESH_S, REFRESH_S - 2):
        before = len(sent)
        timers.advance(step)
        assert len(sent) == before             # the timer kept quiet
        _write(rt, -2500.0)
        assert len(sent) == before + 1         # the write was the refresh
        _hub_takes(rt, len(sent))
    assert sent == [("discharge", 2500)] * 6


def test_auto_is_never_sent_again(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, 3000.0)
    _hub_takes(rt, 1)
    timers.advance(100)
    _write(rt, 0.0)                            # back to the hub's own logic
    _hub_takes(rt, 2)
    assert sent == [("charge", 3000), ("auto", None)]
    assert timers.live == []                   # the charge's timer is gone
    for _ in range(12):
        timers.advance(REFRESH_S)
        _write(rt, 0.0)
    timers.advance(3600)
    assert sent == [("charge", 3000), ("auto", None)]


def test_a_refresh_waits_while_the_hub_is_still_applying_a_command(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    # An interval inside the hub's answer window, the only way the guard
    # is reached: at REFRESH_S a command's transaction is long closed.
    monkeypatch.setattr(runtime_mod, "REFRESH_S", 20.0)
    monkeypatch.setattr(runtime_mod, "REFRESH_OFFSET_S", 5.0)
    _write(rt, 100.0)
    rt.handle_answer(KIND_RESPONSE, _answer("t1", "ack", "sending cmd to ESOs"))
    timers.advance(16)
    _write(rt, 100.0)                          # due, but the result has not come
    timers.advance(25)                         # and the timer skips it too
    assert sent == [("charge", 100)]
    rt.handle_answer(KIND_RESULT, _answer("t1", "ack", "all ESOs have changed setting"))
    timers.advance(20)                         # the timer's next turn
    assert sent == [("charge", 100)] * 2


def test_a_hub_that_never_answers_still_gets_its_refresh(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, 100.0)                          # no answer ever (no subscription)
    timers.advance(PENDING_TTL_S + 1)
    assert rt.tracker.status == "pending"
    timers.advance(REFRESH_S + REFRESH_OFFSET_S)
    assert sent == [("charge", 100)] * 2
    assert rt.tracker.following is None


def test_a_nak_still_forces_a_resend_and_the_timer_leaves_it_to_the_write(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, 100.0)
    rt.handle_answer(KIND_RESPONSE, _answer("t1", "nak", "transaction in progress"))
    timers.advance(5)
    _write(rt, 100.0)                          # at once, not REFRESH_S later
    assert sent == [("charge", 100)] * 2
    _hub_takes(rt, 2)
    # The hub refuses a refresh: forgotten, and the next write sends it.
    timers.advance(REFRESH_S + REFRESH_OFFSET_S)
    assert sent == [("charge", 100)] * 3
    rt.handle_answer(KIND_RESPONSE, _answer("t3", "nak", "transaction in progress"))
    assert rt.tracker.following is False and rt.tracker.naks == 2
    timers.advance(3 * REFRESH_S)              # nothing stands: the timer stops
    assert sent == [("charge", 100)] * 3 and timers.live == []
    _write(rt, 100.0)
    assert sent == [("charge", 100)] * 4


def test_a_refresh_the_broker_refuses_is_tried_again_on_the_next_turn(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, 100.0)
    _hub_takes(rt, 1)
    real_send = mqtt_control.async_send

    async def broker_away(*args, **kw):
        raise RuntimeError("MQTT is not connected")

    monkeypatch.setattr(mqtt_control, "async_send", broker_away)
    timers.advance(REFRESH_S + REFRESH_OFFSET_S)  # no caller to raise to
    assert sent == [("charge", 100)] and len(timers.live) == 1
    monkeypatch.setattr(mqtt_control, "async_send", real_send)
    timers.advance(REFRESH_S)
    assert sent == [("charge", 100)] * 2


def test_control_off_and_an_unload_stop_the_timer(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, 5000.0)
    _hub_takes(rt, 1)
    assert len(timers.live) == 1
    rt.control_enabled = False                 # the switch's turn_off
    run(rt.async_release())
    assert sent == [("charge", 5000), ("auto", None)] and timers.live == []
    timers.advance(3600)
    _write(rt, 5000.0)                         # control off: nothing at all
    assert sent == [("charge", 5000), ("auto", None)] and timers.live == []
    # Control back on: a fresh publish, and the timer with it.
    rt.control_enabled = True
    run(rt.async_apply())
    assert sent[-1] == ("charge", 5000) and len(timers.live) == 1
    rt.close()                                 # the entry unloaded
    timers.advance(3600)
    assert len(sent) == 3


def _stalled_broker(monkeypatch, sent):
    """async_send that waits for the broker's answer until the test lets
    it, as Home Assistant's publish waits for the message id (up to ten
    seconds with a broker that stalls)."""
    gate = asyncio.Event()

    async def slow_send(hass, base_topic, name, watts=None):
        payload = mqtt_control.build_payload(name, watts)
        payload["transId"] = f"t{len(sent) + 1}"
        sent.append((name, watts))
        await gate.wait()
        return payload

    monkeypatch.setattr(mqtt_control, "async_send", slow_send)
    return gate


def test_an_unload_during_a_writes_publish_leaves_no_timer(monkeypatch):
    """The entry reloads while EMS's charge 5000 is still being published:
    the write used to arm the timer once the publish returned, after the
    unload had stopped it, and the unloaded runtime sent charge 5000 every
    five minutes beside the new one, whatever the new one was told."""
    rt, sent, timers = _runtime(monkeypatch)
    gate = _stalled_broker(monkeypatch, sent)

    async def scenario():
        rt.setpoint_w = 5000.0
        write = asyncio.ensure_future(rt.async_apply())
        await asyncio.sleep(0)
        rt.close()                             # the entry unloads
        gate.set()                             # the broker answers
        await write

    run(scenario())
    assert sent == [("charge", 5000)] and timers.live == []
    timers.advance(3600)
    assert sent == [("charge", 5000)]


def test_an_unload_during_the_timers_refresh_leaves_no_timer(monkeypatch):
    rt, sent, timers = _runtime(monkeypatch)
    _write(rt, 5000.0)
    _hub_takes(rt, 1)
    gate = _stalled_broker(monkeypatch, sent)

    async def scenario():
        # The timer falls due, and its refresh is being published.
        timer, = timers.live
        timer["live"] = False
        timers.clock.now = timer["due"]
        refresh = asyncio.ensure_future(timer["action"](None))
        await asyncio.sleep(0)
        rt.close()
        gate.set()
        await refresh

    run(scenario())
    assert sent == [("charge", 5000)] * 2 and timers.live == []
    timers.advance(3600)
    assert len(sent) == 2


def test_a_restart_starts_the_timer_fresh(monkeypatch):
    # Control and the setpoint restored from the last state: nothing goes
    # out, and nothing is timed, until the first write.
    rt, sent, timers = _runtime(monkeypatch, setpoint_w=100.0)
    assert timers.live == []
    timers.advance(3600)
    assert sent == []
    _write(rt, 100.0)
    assert sent == [("charge", 100)]
    timers.advance(REFRESH_S + REFRESH_OFFSET_S)
    assert sent == [("charge", 100)] * 2
