"""``sensor.{prefix}_last_command`` — what the hub said to the last command.

Until 0.3.0 this sensor claimed ``sensor.{prefix}_control_status``, the id
the Ferroamp integration's own control-status sensor already holds, so it
ended up as ``..._control_status_2``; an existing entry is renamed once at
setup (see __init__.py).

State: ``idle`` (nothing sent since control came on), ``pending`` (sent, no
answer yet), ``ack`` or ``nak`` (the hub's verdict on the latest command).
Attributes carry the last command, the last ack, the last nak and the last
control/result, each with the hub's own message, so a refused command is
visible in the UI instead of only in a debug log (F42).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
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
    async_add_entities([FerroampControlStatusSensor(runtime)])


class FerroampControlStatusSensor(SensorEntity):
    _attr_name = "Ferroamp last command"
    _attr_icon = "mdi:message-reply-text-outline"
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, runtime: FerroampControlRuntime) -> None:
        self._rt = runtime
        self._attr_unique_id = f"{runtime.entry_id}_control_status"
        self.entity_id = f"sensor.{runtime.prefix}_last_command"
        self._attr_device_info = device_info(runtime.entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._rt.add_listener(self._changed))

    @callback
    def _changed(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return self._rt.tracker.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._rt.tracker.as_attributes()
