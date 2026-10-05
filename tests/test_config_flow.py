"""Tests for the config and options flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pushover_next.const import (
    CONF_API_TOKEN,
    CONF_DEFAULT_EXPIRE,
    CONF_DEFAULT_RETRY,
    CONF_ENCRYPTION_KEY,
    CONF_USER_KEY,
    DOMAIN,
)
from custom_components.pushover_next.crypto import generate_key
from custom_components.pushover_next.exceptions import InvalidAuth

from pytest_homeassistant_custom_component.common import MockConfigEntry

_VALIDATE = "custom_components.pushover_next.config_flow._validate_credentials"
_DISCOVER_DEVICES = "custom_components.pushover_next.config_flow.async_discover_devices"
_DISCOVER_SOUNDS = "custom_components.pushover_next.config_flow.async_discover_sounds"


async def test_user_flow_success(hass):
    with patch(_VALIDATE, new=AsyncMock(return_value=None)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "My Pushover", CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"},
        )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "My Pushover"
    assert result2["data"] == {CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"}


async def test_user_flow_invalid_auth(hass):
    with patch(_VALIDATE, new=AsyncMock(side_effect=InvalidAuth("bad token"))):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "My Pushover", CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass):
    with patch(_VALIDATE, new=AsyncMock(side_effect=aiohttp.ClientConnectionError("boom"))):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "My Pushover", CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_duplicate_entry_aborts(hass):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="tok:user",
        data={CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"},
    ).add_to_hass(hass)

    with patch(_VALIDATE, new=AsyncMock(return_value=None)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "My Pushover", CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"},
        )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


def _mock_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="tok:user",
        data={CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"},
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def test_options_defaults_retry_must_be_less_than_expire(hass):
    entry = _mock_entry(hass)

    with (
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=[])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[])),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "defaults"}
        )
        result3 = await hass.config_entries.options.async_configure(
            result2["flow_id"],
            {
                "default_device": "",
                "default_priority": 0,
                "default_sound": "pushover",
                "default_ttl": 0,
                CONF_DEFAULT_RETRY: 120,
                CONF_DEFAULT_EXPIRE: 60,
            },
        )

    assert result3["type"] is FlowResultType.FORM
    assert result3["errors"] == {"base": "retry_not_less_than_expire"}


async def test_options_defaults_round_trip(hass):
    entry = _mock_entry(hass)

    with (
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=["phone"])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[{"value": "pushover", "label": "pushover"}])),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "defaults"}
        )
        result3 = await hass.config_entries.options.async_configure(
            result2["flow_id"],
            {
                "default_device": "phone",
                "default_priority": 1,
                "default_sound": "pushover",
                "default_ttl": 0,
                CONF_DEFAULT_RETRY: 60,
                CONF_DEFAULT_EXPIRE: 3600,
            },
        )

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["data"]["default_device"] == "phone"
    assert result3["data"]["default_priority"] == 1


async def test_options_encryption_rejects_invalid_key(hass):
    entry = _mock_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "encryption"}
    )
    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {CONF_ENCRYPTION_KEY: "not-a-valid-key"}
    )

    assert result3["type"] is FlowResultType.FORM
    assert result3["errors"] == {"base": "invalid_key_format"}
    # The invalid key must never have been persisted.
    assert CONF_ENCRYPTION_KEY not in entry.options


async def test_options_encryption_set_then_clear(hass):
    entry = _mock_entry(hass)
    key = generate_key()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "encryption"}
    )
    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {CONF_ENCRYPTION_KEY: key}
    )
    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["data"][CONF_ENCRYPTION_KEY] == key

    # Update the entry's options to what the flow just returned, as Home
    # Assistant itself would, then verify submitting blank clears the key.
    hass.config_entries.async_update_entry(entry, options=result3["data"])

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "encryption"}
    )
    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {CONF_ENCRYPTION_KEY: ""}
    )
    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_ENCRYPTION_KEY not in result3["data"]
