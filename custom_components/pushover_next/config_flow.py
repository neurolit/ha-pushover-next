"""Config and options flow for Pushover Next."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import PushoverClient
from .const import (
    CONF_API_TOKEN,
    CONF_DEFAULT_DEVICE,
    CONF_DEFAULT_EXPIRE,
    CONF_DEFAULT_PRIORITY,
    CONF_DEFAULT_RETRY,
    CONF_DEFAULT_SOUND,
    CONF_DEFAULT_TTL,
    CONF_ENCRYPTION_KEY,
    CONF_USER_KEY,
    DOMAIN,
    MAX_EXPIRE_SECONDS,
    MAX_RETRY_SECONDS,
    MIN_RETRY_SECONDS,
)
from .crypto import self_test
from .discovery import async_discover_devices, async_discover_sounds
from .exceptions import CannotConnect, InvalidAuth, PushoverNextError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Pushover"): TextSelector(),
        vol.Required(CONF_API_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(CONF_USER_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


async def _validate_credentials(hass: Any, api_token: str, user_key: str) -> None:
    session = async_get_clientsession(hass)
    client = PushoverClient(session, api_token, user_key)
    await client.validate_user()


class PushoverNextConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle creation of a Pushover Next config entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect the application token and user/group key, then validate them."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_API_TOKEN]}:{user_input[CONF_USER_KEY]}")
            self._abort_if_unique_id_configured()

            try:
                await _validate_credentials(
                    self.hass, user_input[CONF_API_TOKEN], user_input[CONF_USER_KEY]
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, CannotConnect, TimeoutError):
                errors["base"] = "cannot_connect"
            except PushoverNextError:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_API_TOKEN: user_input[CONF_API_TOKEN],
                        CONF_USER_KEY: user_input[CONF_USER_KEY],
                    },
                )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PushoverNextOptionsFlow:
        """Get the options flow for this handler."""
        return PushoverNextOptionsFlow()


class PushoverNextOptionsFlow(config_entries.OptionsFlow):
    """Manage sending defaults and the account's single encryption key."""

    def _client(self) -> PushoverClient:
        session = async_get_clientsession(self.hass)
        return PushoverClient(
            session,
            self.config_entry.data[CONF_API_TOKEN],
            self.config_entry.data[CONF_USER_KEY],
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Offer the menu of things that can be configured."""
        return self.async_show_menu(step_id="init", menu_options=["defaults", "encryption"])

    async def async_step_defaults(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Set the defaults used when a service call doesn't override them."""
        current = self.config_entry.options

        client = self._client()
        live_devices = await async_discover_devices(client)
        sound_options = await async_discover_sounds(client)

        device_names = list(dict.fromkeys(["", *live_devices]))

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEFAULT_DEVICE, default=current.get(CONF_DEFAULT_DEVICE, "")
                ): SelectSelector(SelectSelectorConfig(options=device_names, custom_value=True)),
                vol.Optional(
                    CONF_DEFAULT_PRIORITY, default=current.get(CONF_DEFAULT_PRIORITY, 0)
                ): NumberSelector(
                    NumberSelectorConfig(min=-2, max=2, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_DEFAULT_SOUND, default=current.get(CONF_DEFAULT_SOUND, "pushover")
                ): SelectSelector(SelectSelectorConfig(options=sound_options, custom_value=True)),
                vol.Optional(
                    CONF_DEFAULT_TTL, default=current.get(CONF_DEFAULT_TTL, 0)
                ): NumberSelector(
                    NumberSelectorConfig(min=0, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_DEFAULT_RETRY, default=current.get(CONF_DEFAULT_RETRY, 60)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_RETRY_SECONDS,
                        max=MAX_RETRY_SECONDS,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_DEFAULT_EXPIRE, default=current.get(CONF_DEFAULT_EXPIRE, 3600)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_RETRY_SECONDS,
                        max=MAX_EXPIRE_SECONDS,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        if user_input is not None:
            if user_input[CONF_DEFAULT_RETRY] >= user_input[CONF_DEFAULT_EXPIRE]:
                return self.async_show_form(
                    step_id="defaults",
                    data_schema=schema,
                    errors={"base": "retry_not_less_than_expire"},
                )
            new_options = dict(current)
            new_options.update(user_input)
            if not new_options.get(CONF_DEFAULT_DEVICE):
                new_options.pop(CONF_DEFAULT_DEVICE, None)
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(step_id="defaults", data_schema=schema)

    async def async_step_encryption(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Set or clear the account's single end-to-end encryption key.

        There is one key per account (not per device): all of this user's
        devices are expected to share the same secret, so a single
        ``encrypt: true`` send can target any or all of them without having
        to track which device has which key.
        """
        errors: dict[str, str] = {}
        current_key = self.config_entry.options.get(CONF_ENCRYPTION_KEY, "")

        schema = vol.Schema(
            {
                vol.Optional(CONF_ENCRYPTION_KEY, default=current_key): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

        if user_input is not None:
            key_hex = user_input[CONF_ENCRYPTION_KEY].strip()
            new_options = dict(self.config_entry.options)

            if not key_hex:
                new_options.pop(CONF_ENCRYPTION_KEY, None)
                return self.async_create_entry(title="", data=new_options)

            if not self_test(key_hex):
                errors["base"] = "invalid_key_format"
            else:
                new_options[CONF_ENCRYPTION_KEY] = key_hex
                return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(step_id="encryption", data_schema=schema, errors=errors)
