"""Ferroamp Control — a writable control driver for the Ferroamp EnergyHub.

Implements the EMS inverter contract's control surface (mode / battery power
setpoint / grid limit) and actuates the hub over the local MQTT ExtAPI.

Safety model: a per-entry "control enabled" switch defaults OFF, so installing
and configuring the driver sends nothing to the hardware. EMS can wire itself
to these entities while staying in read-only mode; only when both the switch is
on and EMS is out of read-only does a command actually reach the battery.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .runtime import FerroampControlRuntime

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SELECT, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = FerroampControlRuntime.from_entry(
        hass, entry
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
