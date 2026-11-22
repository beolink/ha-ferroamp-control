"""Config + options flow for Ferroamp Control."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_BASE_TOPIC,
    CONF_MAX_CHARGE_W,
    CONF_MAX_DISCHARGE_W,
    CONF_PREFIX,
    DEFAULT_BASE_TOPIC,
    DEFAULT_MAX_W,
    DEFAULT_PREFIX,
    DOMAIN,
)
from .const import CONF_SEND_STATISTICS


# hassfest rejects URLs in strings.json, so the addresses travel as
# placeholders instead.
STATS_PLACEHOLDERS = {
    "endpoint": "stats.rnet.se",
    "endpoint_url": "https://stats.rnet.se",
    "privacy_url": "https://stats.rnet.se/integritet",
}


def _power(unit: str = "W") -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=100, max=50000, step=100,
                             mode=NumberSelectorMode.BOX, unit_of_measurement=unit)
    )


def _schema(cur: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_PREFIX, default=cur.get(CONF_PREFIX, DEFAULT_PREFIX)): str,
        vol.Required(CONF_BASE_TOPIC, default=cur.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)): str,
        vol.Required(CONF_MAX_CHARGE_W, default=cur.get(CONF_MAX_CHARGE_W, DEFAULT_MAX_W)): _power(),
        vol.Required(CONF_MAX_DISCHARGE_W, default=cur.get(CONF_MAX_DISCHARGE_W, DEFAULT_MAX_W)): _power(),
        vol.Optional(CONF_SEND_STATISTICS, default=cur.get(CONF_SEND_STATISTICS, True)): bool,
    })


class FerroampControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(f"{DOMAIN}_{user_input[CONF_PREFIX]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Ferroamp Control", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}),
                                    description_placeholders=STATS_PLACEHOLDERS)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FerroampControlOptionsFlow(config_entry)


class FerroampControlOptionsFlow(config_entries.OptionsFlow):
    """The entry's settings (Configure on the entry).

    The entry is kept as ``_entry``, never as ``config_entry``: Home
    Assistant 2024.11 made ``OptionsFlow.config_entry`` a property of its
    own, and from 2025.12 setting it raises AttributeError, so the flow
    did not open at all ("the configuration flow could not be loaded").
    Kept by the flow itself, it works on the older releases hacs.json
    allows too, where the property does not exist."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            was_on = {**self._entry.data, **self._entry.options}.get(
                CONF_SEND_STATISTICS, True)
            now_on = bool(user_input.get(CONF_SEND_STATISTICS, True))
            if was_on and not now_on:
                # Switching it off erases what has already been sent, rather
                # than merely going quiet. Imported here rather than at the top:
                # stats.py pulls in Home Assistant, and this module is imported
                # by tests that run without it.
                from .stats import async_forget_install

                await async_forget_install(self.hass, self._entry, DOMAIN)
            return self.async_create_entry(title="", data=user_input)
        cur = {**self._entry.data, **self._entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(cur),
                                    description_placeholders=STATS_PLACEHOLDERS)
