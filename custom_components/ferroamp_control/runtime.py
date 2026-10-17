"""Per-entry runtime + the gated actuation logic."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
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
    REFRESH_OFFSET_S,
    REFRESH_S,
)

_LOGGER = logging.getLogger(__name__)


def _call_later(hass: HomeAssistant, delay: float, action) -> Callable[[], None]:
    """Home Assistant's one-shot timer; returns its cancel. Imported here,
    like mqtt in mqtt_control, so the tests run without Home Assistant."""
    from homeassistant.helpers.event import async_call_later

    return async_call_later(hass, delay, action)


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
    _last_sent_at: float | None = None  # time.monotonic() of the last publish
    _refresh_cancel: Callable[[], None] | None = None  # stops the refresh timer (0.3.6)
    _closed: bool = False  # the entry unloaded: nothing stands, no timer arms (0.3.6)
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
        #
        # Unless the hub refused the last attempt: a NAK ("transaction in
        # progress" against the previous command) left _last_cmd set, so
        # EMS's re-write of the same setpoint on the next tick was deduped
        # away and the hub ran on the OLD command until the plan changed
        # its setpoint, hours in a hold period, with EMS's
        # inverter_not_following issue raised and no way to clear it. A
        # NAK'd command is forgotten in handle_answer and, belt and braces,
        # never deduped against while the tracker says "not following"
        # (0.2.1; EMS's self-healing on a NAK needs this release).
        #
        # Or unless a charge or discharge has stood long enough to go out
        # again (0.3.6, _refresh_due): then this write is its refresh.
        if (name, watts) == self._last_cmd and self.tracker.following is not False:
            if self._refresh_due():
                await self._send(name, watts, refresh=True)
        else:
            self._last_cmd = (name, watts)
            await self._send(name, watts)
            if name != CMD_AUTO:
                self._commanded = True
        # Whatever this write published, the timer counts from it.
        self._arm_refresh(REFRESH_S + REFRESH_OFFSET_S)

    async def async_release(self) -> None:
        """Hand the battery back to the hub's own logic. Called when control is
        switched off, but only if we had actually commanded it."""
        self.cancel_refresh()
        if self._commanded:
            await self._send(CMD_AUTO, None)
            self._commanded = False
        self._last_cmd = None  # force a fresh publish next time control resumes
        # Nothing to follow while control is off: the verdicts start over
        # when control resumes, so a NAK from last week never counts.
        self.tracker.reset()
        self._notify()

    def _standing(self) -> tuple | None:
        """The charge or discharge that stands, or None: control off, the
        entry unloaded, nothing published since control came on (or since
        a NAK), or ``auto``."""
        if (self._closed or not self.control_enabled or self._last_cmd is None
                or self._last_cmd[0] == CMD_AUTO):
            return None
        return self._last_cmd

    def _refresh_due(self) -> bool:
        """Should the standing command go out again, unchanged? (0.3.6)

        The hub drops an ExtAPI command without a word when a slot of its
        own portal schedule begins, or when its settings change: no NAK,
        the verdict stays "ack", and the battery runs on the hub's own
        logic. Publishing only on a change, the driver then kept it there
        for hours while the setpoint said "hold"; the same command sent
        again takes the battery back within half a minute. So a charge or
        discharge that has stood REFRESH_S since it last went out goes out
        again, which bounds any such takeover to about one interval.

        A write counts from REFRESH_S less REFRESH_OFFSET_S on: EMS writes
        on every tick, five minutes apart by default, and its writes land
        a moment either side of that, so each tick refreshes rather than
        every other one.

        Never ``auto``: re-sending it makes the hub re-ramp, and auto is
        the hub's own logic anyway. Never after a NAK: the command is
        forgotten then (handle_answer) and the next write sends it, as
        before. And never while a transaction is still open (sent, no
        result yet): the hub would refuse it, and a refresh must not storm
        the hub with NAKs.
        """
        if self._standing() is None or self.tracker.following is False:
            return False
        if (self._last_sent_at is not None
                and time.monotonic() - self._last_sent_at < REFRESH_S - REFRESH_OFFSET_S):
            return False
        return not self.tracker.busy(time.time())

    def _arm_refresh(self, delay: float) -> None:
        """Start the refresh timer over, or stop it when nothing stands.

        A refresh rides on a write when one comes. The timer is for when
        nothing writes (EMS stopped without a release, a setpoint set by
        hand, EMS ticking less often than every REFRESH_S), and it must
        keep out of the writer's way: the hub needs about ten seconds to
        apply a command and refuses one that arrives meanwhile
        ("transaction in progress"), so a refresh just ahead of the
        writer's next, changed command would cost that command a tick.
        EMS's writes come a whole number of minutes apart; the timer fires
        REFRESH_S plus REFRESH_OFFSET_S after the last write and then
        every REFRESH_S, half a minute off every one of them, and a write
        in between starts it over.
        """
        self.cancel_refresh()
        if self._standing() is not None:
            self._refresh_cancel = _call_later(self.hass, delay, self._async_refresh_timer)

    def cancel_refresh(self) -> None:
        """Stop the refresh timer: control off, the entry unloaded."""
        if self._refresh_cancel is not None:
            self._refresh_cancel()
            self._refresh_cancel = None

    def close(self) -> None:
        """The entry unloaded: stop the timer for good.

        An unload can land while a publish is still awaited (EMS's write,
        or the timer's own refresh; with a broker that stalls, up to ten
        seconds), and the write re-arms the timer once its publish
        returns. Stopping the timer alone left that one running on the
        unloaded runtime, sending its stale command every REFRESH_S beside
        the new runtime's for as long as Home Assistant ran. A closed
        runtime has nothing standing, so it neither arms a timer nor
        refreshes."""
        self._closed = True
        self.cancel_refresh()

    async def _async_refresh_timer(self, _now=None) -> None:
        """Nothing has written for a while: refresh from here."""
        self._refresh_cancel = None
        if self._refresh_due():
            name, watts = self._last_cmd
            try:
                await self._send(name, watts, refresh=True)
            except Exception as err:  # noqa: BLE001 - no caller to raise to; the next turn tries
                _LOGGER.debug("Ferroamp control: refresh not sent: %s", err)
        self._arm_refresh(REFRESH_S)

    async def _send(self, name: str, watts: int | None, *, refresh: bool = False) -> None:
        if refresh:
            _LOGGER.debug("Ferroamp control: %s %s stands, sending it again", name, watts)
        payload = await mqtt_control.async_send(self.hass, self.base_topic, name, watts)
        self._last_sent_at = time.monotonic()
        self.tracker.sent(payload["transId"], name, payload["cmd"].get("arg"), time.time(),
                          refresh=refresh)
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
            if self.tracker.following is False:
                # The latest command did not take: the next async_apply
                # must publish again even if the setpoint is unchanged.
                self._last_cmd = None
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
