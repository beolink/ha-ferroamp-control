"""Ferroamp ExtAPI control over the local MQTT broker.

The Ferroamp EnergyHub (with the ExtAPI / EMS option enabled) accepts battery
control commands on ``<base_topic>/control/request`` as JSON:

    {"transId": "<uuid>", "cmd": {"name": "charge",    "arg": "3000"}}
    {"transId": "<uuid>", "cmd": {"name": "discharge", "arg": "3000"}}
    {"transId": "<uuid>", "cmd": {"name": "auto"}}

``charge`` / ``discharge`` take a power in watts; ``auto`` hands control back to
the hub's own self-consumption logic. ``arg`` is verified against your unit's
ExtAPI documentation — the base topic in particular can differ between hubs.

The hub answers on ``<base_topic>/control/response`` (receipt) and
``<base_topic>/control/result`` (outcome), each ``{"transId": ..., "status":
"ack"|"nak", "msg": ...}``; ``ack_tracker`` pairs them with what was sent.

Every publish is gated by the driver's "control enabled" switch upstream: this
module only builds and sends the payload when explicitly asked to.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from .const import CMD_AUTO, CMD_CHARGE, CMD_DISCHARGE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def build_payload(name: str, watts: int | None = None) -> dict:
    cmd: dict = {"name": name}
    if watts is not None:
        cmd["arg"] = str(int(max(0, watts)))
    return {"transId": str(uuid.uuid4()), "cmd": cmd}


def command_for(setpoint_w: float, max_charge_w: float, max_discharge_w: float) -> tuple[str, int | None]:
    """Translate a signed battery setpoint into a Ferroamp command.

    + = charge, − = discharge, 0 = hand back to the hub (auto).
    """
    if setpoint_w > 0:
        return CMD_CHARGE, int(min(setpoint_w, max_charge_w))
    if setpoint_w < 0:
        return CMD_DISCHARGE, int(min(-setpoint_w, max_discharge_w))
    return CMD_AUTO, None


def request_topic(base_topic: str) -> str:
    return f"{base_topic.rstrip('/')}/control/request"


def answer_topics(base_topic: str) -> dict[str, str]:
    """The two topics the hub answers a request on, by kind (see
    ack_tracker): ``response`` is the receipt, ``result`` the outcome."""
    base = base_topic.rstrip('/')
    return {"response": f"{base}/control/response", "result": f"{base}/control/result"}


async def async_send(hass: "HomeAssistant", base_topic: str, name: str,
                     watts: int | None = None) -> dict:
    """Publish one command; returns the payload sent (its ``transId`` is
    what the hub's answer will carry)."""
    from homeassistant.components import mqtt

    topic = request_topic(base_topic)
    payload = build_payload(name, watts)
    _LOGGER.info("Ferroamp control → %s %s (transId %s)", topic, payload["cmd"],
                 payload["transId"])
    await mqtt.async_publish(hass, topic, json.dumps(payload), qos=0, retain=False)
    return payload
