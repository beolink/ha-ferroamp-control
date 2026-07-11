"""``select.{prefix}_mode`` — the contract mode selector EMS writes to."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, INVERTER_MODES, MODE_SELF_CONSUMPTION
from .device import device_info
from .runtime import FerroampControlRuntime


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: FerroampControlRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FerroampModeSelect(runtime)])


class FerroampModeSelect(RestoreEntity, SelectEntity):
    _attr_name = "Ferroamp mode"
    _attr_icon = "mdi:battery-charging-medium"
    _attr_options = INVERTER_MODES
    _attr_has_entity_name = False

    def __init__(self, runtime: FerroampControlRuntime) -> None:
        self._rt = runtime
        self._attr_unique_id = f"{runtime.prefix}_mode"
        self.entity_id = f"select.{runtime.prefix}_mode"
        self._attr_device_info = device_info(runtime.entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in INVERTER_MODES:
            self._rt.current_mode = last.state

    @property
    def current_option(self) -> str:
        return self._rt.current_mode or MODE_SELF_CONSUMPTION

    async def async_select_option(self, option: str) -> None:
        self._rt.current_mode = option
        self.async_write_ha_state()
        await self._rt.async_apply()
