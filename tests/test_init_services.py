"""Tests for the pushover_next.* services registered in __init__.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.pushover_next.api import PushoverClient, PushoverResponse
from custom_components.pushover_next.const import (
    ATTR_ENCRYPT,
    ATTR_EXPIRE,
    ATTR_HTML,
    ATTR_MESSAGE,
    ATTR_MONOSPACE,
    ATTR_PRIORITY,
    ATTR_RETRY,
    ATTR_TAGS,
    ATTR_TITLE,
    CONF_API_TOKEN,
    CONF_ENCRYPTION_KEY,
    CONF_USER_KEY,
    DATA_CLIENTS,
    DEFAULT_ENCRYPTED_TITLE,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from custom_components.pushover_next.crypto import decrypt_field, generate_key

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _device_id_for_entry(hass, entry) -> str:
    """Return the id of the per-account device notify.py registers for entry."""
    device_registry = dr.async_get(hass)
    [device] = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    return device.id

_VALIDATE = "custom_components.pushover_next.api.PushoverClient.validate_user"
_DISCOVER_DEVICES = "custom_components.pushover_next.async_discover_devices"
_DISCOVER_SOUNDS = "custom_components.pushover_next.async_discover_sounds"


@pytest.fixture
async def entry(hass):
    """Set up a config entry with services registered, no encryption key."""
    with (
        patch(_VALIDATE, new=AsyncMock(return_value={})),
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=[])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[])),
    ):
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id="tok:user",
            data={CONF_API_TOKEN: "tok", CONF_USER_KEY: "user"},
            options={},
        )
        mock_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    yield mock_entry


def _mock_client(hass, entry) -> AsyncMock:
    """Replace the live client's send_message with a mock and return it."""
    client: PushoverClient = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    client.send_message = AsyncMock(return_value=PushoverResponse(status=1, request="r1"))
    return client.send_message


async def test_send_message_basic(hass, entry):
    mock_send = _mock_client(hass, entry)

    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_MESSAGE, {ATTR_MESSAGE: "hello"}, blocking=True
    )

    mock_send.assert_called_once()
    sent_message = mock_send.call_args[0][0]
    assert sent_message.message == "hello"
    assert sent_message.encrypted is False


async def test_send_message_too_long_rejected(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, SERVICE_SEND_MESSAGE, {ATTR_MESSAGE: "x" * 1025}, blocking=True
        )


async def test_send_message_invalid_priority_rejected(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "hi", ATTR_PRIORITY: 3},
            blocking=True,
        )


async def test_html_and_monospace_conflict(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "hi", ATTR_HTML: True, ATTR_MONOSPACE: True},
            blocking=True,
        )


async def test_emergency_without_retry_expire_rejected(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "hi", ATTR_PRIORITY: 2},
            blocking=True,
        )


async def test_emergency_retry_not_less_than_expire_rejected(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "hi", ATTR_PRIORITY: 2, ATTR_RETRY: 120, ATTR_EXPIRE: 60},
            blocking=True,
        )


async def test_emergency_with_valid_retry_expire_succeeds(hass, entry):
    mock_send = _mock_client(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "hi", ATTR_PRIORITY: 2, ATTR_RETRY: 60, ATTR_EXPIRE: 3600},
        blocking=True,
    )
    mock_send.assert_called_once()


async def test_encrypt_without_key_configured_rejected(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "secret", ATTR_ENCRYPT: True},
            blocking=True,
        )


async def test_encrypt_with_key_encrypts_message_and_title(hass, entry):
    key = generate_key()
    with (
        patch(_VALIDATE, new=AsyncMock(return_value={})),
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=[])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[])),
    ):
        hass.config_entries.async_update_entry(entry, options={CONF_ENCRYPTION_KEY: key})
        await hass.async_block_till_done()

    mock_send = _mock_client(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "secret", ATTR_TITLE: "My title", ATTR_ENCRYPT: True},
        blocking=True,
    )

    sent_message = mock_send.call_args[0][0]
    assert sent_message.encrypted is True
    assert decrypt_field(sent_message.message, key) == "secret"
    assert decrypt_field(sent_message.title, key) == "My title"


async def test_encrypt_without_title_uses_placeholder(hass, entry):
    key = generate_key()
    with (
        patch(_VALIDATE, new=AsyncMock(return_value={})),
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=[])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[])),
    ):
        hass.config_entries.async_update_entry(entry, options={CONF_ENCRYPTION_KEY: key})
        await hass.async_block_till_done()

    mock_send = _mock_client(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "secret", ATTR_ENCRYPT: True},
        blocking=True,
    )

    sent_message = mock_send.call_args[0][0]
    assert decrypt_field(sent_message.title, key) == DEFAULT_ENCRYPTED_TITLE


async def test_encrypt_device_field_left_untouched(hass, entry):
    """device is orthogonal to encryption - omitted or a list, it passes through as-is."""
    key = generate_key()
    with (
        patch(_VALIDATE, new=AsyncMock(return_value={})),
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=[])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[])),
    ):
        hass.config_entries.async_update_entry(entry, options={CONF_ENCRYPTION_KEY: key})
        await hass.async_block_till_done()

    mock_send = _mock_client(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "secret", ATTR_ENCRYPT: True, "device": ["phone", "desktop"]},
        blocking=True,
    )

    sent_message = mock_send.call_args[0][0]
    assert sent_message.device == ["phone", "desktop"]


async def test_tags_total_length_limit(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "hi", ATTR_TAGS: ["x" * 201]},
            blocking=True,
        )


async def test_send_message_with_device_id_resolves_entry(hass, entry):
    mock_send = _mock_client(hass, entry)
    device_id = _device_id_for_entry(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "hello", "device_id": device_id},
        blocking=True,
    )

    mock_send.assert_called_once()


async def test_send_message_with_unknown_device_id_rejected(hass, entry):
    _mock_client(hass, entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "hi", "device_id": "not-a-real-device"},
            blocking=True,
        )


async def test_idempotent_service_registration_with_two_entries(hass):
    with (
        patch(_VALIDATE, new=AsyncMock(return_value={})),
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=[])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[])),
    ):
        entry1 = MockConfigEntry(
            domain=DOMAIN, unique_id="tok1:user1", data={CONF_API_TOKEN: "tok1", CONF_USER_KEY: "user1"}
        )
        entry1.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry1.entry_id)
        await hass.async_block_till_done()

        entry2 = MockConfigEntry(
            domain=DOMAIN, unique_id="tok2:user2", data={CONF_API_TOKEN: "tok2", CONF_USER_KEY: "user2"}
        )
        entry2.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE)

    # Ambiguous call without config_entry_id must be rejected...
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, SERVICE_SEND_MESSAGE, {ATTR_MESSAGE: "hi"}, blocking=True
        )

    # ...but is fine once a specific entry is named.
    client1: PushoverClient = hass.data[DOMAIN][DATA_CLIENTS][entry1.entry_id]
    client1.send_message = AsyncMock(return_value=PushoverResponse(status=1, request="r1"))
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "hi", "config_entry_id": entry1.entry_id},
        blocking=True,
    )
    client1.send_message.assert_called_once()

    # ...and device_id alone is just as good at disambiguating.
    client1.send_message.reset_mock()
    device_id1 = _device_id_for_entry(hass, entry1)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_MESSAGE: "hi", "device_id": device_id1},
        blocking=True,
    )
    client1.send_message.assert_called_once()


async def test_device_id_and_mismatched_config_entry_id_rejected(hass):
    with (
        patch(_VALIDATE, new=AsyncMock(return_value={})),
        patch(_DISCOVER_DEVICES, new=AsyncMock(return_value=[])),
        patch(_DISCOVER_SOUNDS, new=AsyncMock(return_value=[])),
    ):
        entry1 = MockConfigEntry(
            domain=DOMAIN, unique_id="tok1:user1", data={CONF_API_TOKEN: "tok1", CONF_USER_KEY: "user1"}
        )
        entry1.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry1.entry_id)
        await hass.async_block_till_done()

        entry2 = MockConfigEntry(
            domain=DOMAIN, unique_id="tok2:user2", data={CONF_API_TOKEN: "tok2", CONF_USER_KEY: "user2"}
        )
        entry2.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()

    device_id1 = _device_id_for_entry(hass, entry1)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_MESSAGE: "hi", "device_id": device_id1, "config_entry_id": entry2.entry_id},
            blocking=True,
        )
