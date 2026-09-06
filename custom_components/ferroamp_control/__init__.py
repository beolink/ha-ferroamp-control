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

from . import mqtt_control
from .const import DOMAIN
from .runtime import FerroampControlRuntime

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = FerroampControlRuntime.from_entry(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await _async_subscribe_answers(hass, entry, runtime)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


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
    return unload_ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
