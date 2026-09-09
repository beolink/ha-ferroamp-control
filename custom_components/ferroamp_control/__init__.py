"""Ferroamp Control — a writable control driver for the Ferroamp EnergyHub.

Implements the EMS inverter contract's control surface (mode / battery power
setpoint / grid limit) and actuates the hub over the local MQTT ExtAPI.

Safety model: a per-entry "control enabled" switch defaults OFF, so installing
and configuring the driver sends nothing to the hardware. EMS can wire itself
to these entities while staying in read-only mode; only when both the switch is
on and EMS is out of read-only does a command actually reach the battery.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration

from . import mqtt_control
from .const import DOMAIN
from .runtime import FerroampControlRuntime
from .stats import async_setup_stats, async_stop_stats
from .stats_extra import ErrorCounter, build_extra

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


_FAILURES: dict[str, ErrorCounter] = {}


def _stats_extra_for(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """The driver's part of the anonymous daily report.

    Resolved when the report is built, not when it is armed, so a set-up that
    did not finish (the broker or the hub away) still reports the driver as
    installed. Reads the runtime it already has and never the hub. What goes
    in it: stats_extra.py, and why: https://stats.rnet.se/integritet
    """
    runtime = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    failures = _FAILURES.setdefault(entry.entry_id, ErrorCounter())
    if runtime is None:
        config = {**entry.data, **entry.options}
        return build_extra(
            control_enabled=False,
            grid_limit_w=config.get("grid_limit_w"),
            max_charge_w=config.get("max_charge_w"),
            max_discharge_w=config.get("max_discharge_w"),
            commanded=False,
            naks=0,
        )
    return build_extra(
        control_enabled=bool(runtime.control_enabled),
        grid_limit_w=runtime.grid_limit_w,
        max_charge_w=runtime.max_charge_w,
        max_discharge_w=runtime.max_discharge_w,
        commanded=bool(getattr(runtime, "_commanded", False)),
        naks=failures.delta(int(getattr(runtime.tracker, "naks", 0))),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Armed before anything that can raise, and stopped only from
    # async_unload_entry: Home Assistant runs an entry's on-unload callbacks
    # after every failed set-up attempt, so a reporter tied to them goes quiet
    # exactly while the hub or the broker is away.
    try:
        integration = await async_get_integration(hass, DOMAIN)
        await async_setup_stats(
            hass, entry, DOMAIN, str(integration.version),
            extra=lambda: _stats_extra_for(hass, entry),
        )
    except Exception:  # noqa: BLE001 - statistics must never break a set-up
        _LOGGER.debug("Could not arm the statistics reporter", exc_info=True)

    runtime = FerroampControlRuntime.from_entry(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    _rename_verdict_sensor(hass, entry, runtime)
    await _async_subscribe_answers(hass, entry, runtime)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _rename_verdict_sensor(hass: HomeAssistant, entry: ConfigEntry,
                           runtime: FerroampControlRuntime) -> None:
    """0.3.1: the verdict sensor used to claim sensor.{prefix}_control_status,
    the id the Ferroamp integration's own control-status sensor already has,
    so it became ..._control_status_2. It is sensor.{prefix}_last_command
    now; a registry entry under the old id is renamed once."""
    try:
        from homeassistant.helpers import entity_registry as er
        registry = er.async_get(hass)
        current = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_control_status")
        wanted = f"sensor.{runtime.prefix}_last_command"
        if current and current != wanted and registry.async_get(wanted) is None:
            registry.async_update_entity(current, new_entity_id=wanted)
            _LOGGER.info("Renamed %s to %s", current, wanted)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Verdict sensor rename skipped: %s", err)


async def _async_subscribe_answers(hass: HomeAssistant, entry: ConfigEntry,
                                   runtime: FerroampControlRuntime) -> None:
    """Listen for the hub's ack / nak on control/response and control/result
    so every command is paired with its receipt (F42). A broker that is not
    up yet must not fail the entry: the driver still commands, it just
    cannot report the verdict."""
    from homeassistant.components import mqtt

    for kind, topic in mqtt_control.answer_topics(runtime.base_topic).items():

        @callback
        def _on_message(msg, kind=kind) -> None:
            runtime.handle_answer(kind, msg.payload)

        try:
            unsub = await mqtt.async_subscribe(hass, topic, _on_message, qos=0)
        except Exception as err:  # noqa: BLE001 — HomeAssistantError when MQTT is not ready
            _LOGGER.warning("Could not subscribe to %s (%s); the hub's answers "
                            "will not be shown until the entry is reloaded", topic, err)
            continue
        entry.async_on_unload(unsub)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # Only here, never from an on-unload callback: those also run when a
        # set-up attempt fails, and the report has to survive that.
        await async_stop_stats(hass, entry, DOMAIN)
    return unload_ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
