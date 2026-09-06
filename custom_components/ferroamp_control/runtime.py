"""Per-entry runtime + the gated actuation logic."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import mqtt_control
from .ack_tracker import KINDS, CommandTracker
from .const import (
    CMD_AUTO,
    CONF_BASE_TOPIC,
    CONF_MAX_CHARGE_W,
    CONF_MAX_DISCHARGE_W,
    CONF_PREFIX,
    DEFAULT_BASE_TOPIC,
    DEFAULT_MAX_W,
    DEFAULT_PREFIX,
    MODE_IDLE,
    MODE_SELF_CONSUMPTION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class FerroampControlRuntime:
    hass: HomeAssistant
    entry_id: str
    prefix: str
    base_topic: str
    max_charge_w: float
    max_discharge_w: float
    control_enabled: bool = False
    current_mode: str = MODE_SELF_CONSUMPTION
    setpoint_w: float = 0.0
    grid_limit_w: float | None = None
    _commanded: bool = False
    _last_cmd: tuple | None = None  # last (name, watts) actually published
    # Every command paired with the hub's ack / nak (F42); the status
    # sensor and the "following" binary sensor read it.
    tracker: CommandTracker = field(default_factory=CommandTracker)
    # Entities that want to know when the tracker changed.
    _listeners: list = field(default_factory=list)

    @classmethod
    def from_entry(cls, hass: HomeAssistant, entry: ConfigEntry) -> "FerroampControlRuntime":
        data = {**entry.data, **entry.options}
        return cls(
            hass=hass,
            entry_id=entry.entry_id,
            prefix=data.get(CONF_PREFIX, DEFAULT_PREFIX),
            base_topic=data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC),
            max_charge_w=float(data.get(CONF_MAX_CHARGE_W, DEFAULT_MAX_W)),
            max_discharge_w=float(data.get(CONF_MAX_DISCHARGE_W, DEFAULT_MAX_W)),
        )

    async def async_apply(self) -> None:
        """Send the command implied by the current mode + setpoint.

        Hard-gated: does nothing at all unless control is enabled. This is the
        single choke point through which every hardware command flows.
        """
        if not self.control_enabled:
            _LOGGER.debug("Ferroamp control disabled — command suppressed")
            return
        if self.current_mode == MODE_IDLE:
            name, watts = CMD_AUTO, None
        else:
            name, watts = mqtt_control.command_for(
                self.setpoint_w, self.max_charge_w, self.max_discharge_w
            )
        # Only publish when the command actually changes. EMS re-writes the
        # setpoint every tick; re-sending an unchanged command (especially
        # `auto`) can make the hub re-ramp its self-consumption and wastes a
        # transaction (risking a NAK against the next real command).
        if (name, watts) == self._last_cmd:
            return
        self._last_cmd = (name, watts)
        await self._send(name, watts)
        if name != CMD_AUTO:
            self._commanded = True

    async def async_release(self) -> None:
        """Hand the battery back to the hub's own logic. Called when control is
        switched off, but only if we had actually commanded it."""
        if self._commanded:
            await self._send(CMD_AUTO, None)
            self._commanded = False
        self._last_cmd = None  # force a fresh publish next time control resumes
        # Nothing to follow while control is off: the verdicts start over
        # when control resumes, so a NAK from last week never counts.
        self.tracker.reset()
        self._notify()

    async def _send(self, name: str, watts: int | None) -> None:
        payload = await mqtt_control.async_send(self.hass, self.base_topic, name, watts)
        self.tracker.sent(payload["transId"], name, payload["cmd"].get("arg"), time.time())
        self._notify()

    def handle_answer(self, kind: str, payload: str) -> None:
        """One message from ``<base_topic>/control/response`` or ``/result``."""
        if kind not in KINDS:
            return
        verdict = self.tracker.receive(kind, payload, time.time())
        if verdict is None:
            _LOGGER.debug("Ferroamp control %s not for us: %s", kind, payload)
        elif verdict == "nak":
            _LOGGER.warning("Ferroamp hub refused command %s (%s): %s",
                            (self.tracker.last_nak or {}).get("cmd"), kind,
                            (self.tracker.last_nak or {}).get("msg"))
        else:
            _LOGGER.debug("Ferroamp hub %s ack: %s", kind,
                          (self.tracker.last_ack or {}).get("msg"))
        self._notify()

    def add_listener(self, cb) -> "callable":
        self._listeners.append(cb)

        def _remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)
        return _remove

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()
