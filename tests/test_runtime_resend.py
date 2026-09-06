"""A NAK'd command is sent again on the next write (0.2.1).

async_apply dedupes on the last command published so that EMS's re-write
of an unchanged setpoint every tick does not make the hub re-ramp. After a
NAK that dedupe kept the hub on the OLD command: the setpoint was the same,
so nothing was published again, and EMS could raise inverter_not_following
but never repair it. Now a NAK on the latest command forgets the dedupe
key, and the dedupe never applies while the tracker says "not following".
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
from custom_components.ferroamp_control.ack_tracker import KIND_RESPONSE  # noqa: E402
from custom_components.ferroamp_control.runtime import FerroampControlRuntime  # noqa: E402


def _runtime(monkeypatch):
    sent = []

    async def fake_send(hass, base_topic, name, watts=None):
        payload = mqtt_control.build_payload(name, watts)
        payload["transId"] = f"t{len(sent) + 1}"
        sent.append((name, watts))
        return payload

    monkeypatch.setattr(mqtt_control, "async_send", fake_send)
    rt = FerroampControlRuntime(hass=object(), entry_id="e1", prefix="ferroamp",
                                base_topic="extapi", max_charge_w=5000.0,
                                max_discharge_w=5000.0, control_enabled=True)
    return rt, sent


def _answer(trans_id, status, msg):
    return json.dumps({"transId": trans_id, "status": status, "msg": msg})


def test_a_nak_makes_the_same_setpoint_publish_again(monkeypatch):
    rt, sent = _runtime(monkeypatch)
    run = asyncio.run
    rt.setpoint_w = 100.0                      # EMS's hold token
    run(rt.async_apply())
    assert sent == [("charge", 100)]
    # The hub refuses it (the previous command is still being applied).
    rt.handle_answer(KIND_RESPONSE, _answer("t1", "nak", "transaction in progress"))
    assert rt.tracker.following is False
    # EMS writes the same 100 W next tick: it must go out again.
    run(rt.async_apply())
    assert sent == [("charge", 100), ("charge", 100)]
    # The hub takes it: the tick after that is deduped as before.
    rt.handle_answer(KIND_RESPONSE, _answer("t2", "ack", "sending cmd to ESOs"))
    run(rt.async_apply())
    assert sent == [("charge", 100), ("charge", 100)]


def test_an_acked_command_is_still_deduped_and_a_nak_on_an_old_one_is_not_a_resend(monkeypatch):
    rt, sent = _runtime(monkeypatch)
    run = asyncio.run
    rt.setpoint_w = 3000.0
    run(rt.async_apply())
    rt.handle_answer(KIND_RESPONSE, _answer("t1", "ack", "sending cmd to ESOs"))
    run(rt.async_apply())
    run(rt.async_apply())
    assert sent == [("charge", 3000)]
    # A new command; the late NAK of the OLD one changes nothing.
    rt.setpoint_w = 0.0
    run(rt.async_apply())
    assert sent == [("charge", 3000), ("auto", None)]
    rt.handle_answer(KIND_RESPONSE, _answer("t1", "nak", "PowerLimitsInvalid"))
    assert rt.tracker.following is None       # t2 is pending, no verdict
    run(rt.async_apply())
    assert sent == [("charge", 3000), ("auto", None)]
