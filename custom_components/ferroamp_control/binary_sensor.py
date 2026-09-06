"""``binary_sensor.{prefix}_following`` — does the hub follow the command?

On when the hub acknowledged the latest command, off when it refused it
(NAK), unknown until it has answered. EMS reads this entity (its inverter
contract names it as optional) and raises the Repairs issue
``inverter_not_following`` after two ticks of NAK, instead of comparing
battery power with the plan, which in auto always differs (F42).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import device_info
from .runtime import FerroampControlRuntime


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: FerroampControlRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FerroampFollowingBinarySensor(runtime)])


class FerroampFollowingBinarySensor(BinarySensorEntity):
    _attr_name = "Ferroamp hub following command"
    _attr_icon = "mdi:check-network-outline"
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, runtime: FerroampControlRuntime) -> None:
        self._rt = runtime
        self._attr_unique_id = f"{runtime.entry_id}_following"
        self.entity_id = f"binary_sensor.{runtime.prefix}_following"
        self._attr_device_info = device_info(runtime.entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._rt.add_listener(self._changed))

    @callback
    def _changed(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        return self._rt.tracker.following

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tracker = self._rt.tracker
        return {
            "last_command": tracker.last_command,
            "last_nak": (tracker.last_nak or {}).get("msg"),
            "last_ack": (tracker.last_ack or {}).get("msg"),
        }
