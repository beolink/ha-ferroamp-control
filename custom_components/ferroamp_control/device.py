"""Device grouping for the Ferroamp Control entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Ferroamp Control",
        manufacturer="beolink",
        model="Ferroamp EnergyHub (MQTT ExtAPI)",
    )
