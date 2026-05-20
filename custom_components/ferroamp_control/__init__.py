"""Ferroamp Control — phase 2 scaffold.

This integration will provide writable control of a Ferroamp Energy Hub
(modes, battery setpoint, grid power limit) over Modbus TCP, implementing
the EMS inverter contract.

Phase 1 of the EMS project uses a built-in mock inverter. Real Ferroamp
control is intentionally deferred until the contract is stable.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "ferroamp_control"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    raise NotImplementedError(
        "ferroamp_control is a phase-2 scaffold and has no runtime yet. "
        "Use the bundled mock inverter in ha-ems for development."
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
