"""The master control gate.

While this switch is OFF (the default) the driver never publishes a command,
so EMS can drive the mode/setpoint entities harmlessly. Turning it ON lets the
current setpoint reach the hub; turning it OFF hands the battery back to the
hub's own logic (sends one ``auto`` if we had commanded it)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .device import device_info
from .runtime import FerroampControlRuntime


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: FerroampControlRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FerroampControlEnabledSwitch(runtime)])


class FerroampControlEnabledSwitch(RestoreEntity, SwitchEntity):
    _attr_name = "Ferroamp control enabled"
    _attr_icon = "mdi:transmission-tower-export"
    _attr_has_entity_name = False

    def __init__(self, runtime: FerroampControlRuntime) -> None:
        self._rt = runtime
        self._attr_unique_id = f"{runtime.entry_id}_control_enabled"
        self.entity_id = f"switch.{runtime.prefix}_control_enabled"
        self._attr_device_info = device_info(runtime.entry_id)
        self._is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # Default OFF; only restore an explicit ON.
        self._is_on = last is not None and last.state == "on"
        self._rt.control_enabled = self._is_on

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        self._is_on = True
        self._rt.control_enabled = True
        self.async_write_ha_state()
        await self._rt.async_apply()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self._rt.control_enabled = False
        self.async_write_ha_state()
        await self._rt.async_release()
