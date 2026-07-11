"""Contract number entities EMS writes to:
``number.{prefix}_battery_power_setpoint`` (± W) and
``number.{prefix}_grid_power_limit`` (W, advisory peak cap)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
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
    async_add_entities([
        BatterySetpointNumber(runtime),
        GridLimitNumber(runtime),
    ])


class BatterySetpointNumber(RestoreEntity, NumberEntity):
    _attr_name = "Ferroamp battery power setpoint"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_native_step = 100.0
    _attr_has_entity_name = False

    def __init__(self, runtime: FerroampControlRuntime) -> None:
        self._rt = runtime
        self._attr_unique_id = f"{runtime.prefix}_battery_power_setpoint"
        self.entity_id = f"number.{runtime.prefix}_battery_power_setpoint"
        self._attr_native_min_value = -runtime.max_discharge_w
        self._attr_native_max_value = runtime.max_charge_w
        self._attr_device_info = device_info(runtime.entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self._rt.setpoint_w = float(last.state)
            except (TypeError, ValueError):
                self._rt.setpoint_w = 0.0

    @property
    def native_value(self) -> float:
        return self._rt.setpoint_w

    async def async_set_native_value(self, value: float) -> None:
        self._rt.setpoint_w = value
        self.async_write_ha_state()
        await self._rt.async_apply()


class GridLimitNumber(RestoreEntity, NumberEntity):
    _attr_name = "Ferroamp grid power limit"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 25000.0
    _attr_native_step = 100.0
    _attr_has_entity_name = False

    def __init__(self, runtime: FerroampControlRuntime) -> None:
        self._rt = runtime
        self._attr_unique_id = f"{runtime.prefix}_grid_power_limit"
        self.entity_id = f"number.{runtime.prefix}_grid_power_limit"
        self._attr_device_info = device_info(runtime.entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self._rt.grid_limit_w = float(last.state)
            except (TypeError, ValueError):
                self._rt.grid_limit_w = None

    @property
    def native_value(self) -> float | None:
        return self._rt.grid_limit_w

    async def async_set_native_value(self, value: float) -> None:
        # Advisory only: the basic ExtAPI has no direct grid-limit command, so
        # peak shaving is realised by EMS through the battery setpoint. We store
        # the value so it is visible and available to future transports.
        self._rt.grid_limit_w = value
        self.async_write_ha_state()
