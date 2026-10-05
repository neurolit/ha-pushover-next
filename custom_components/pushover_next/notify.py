"""Basic notify entity for Pushover Next.

Home Assistant's notify entity platform only supports a plain message and
title. Everything else this integration can do (priority, sound, tags,
attachments, TTL, emergency retry/expire, cancel-by-tag, encryption, ...)
is exposed through the ``pushover_next.send_message`` service instead,
since NotifyEntity has no mechanism for passing that extra data through.
This entity exists so simple `notify.send_message` targeting/automations
keep working, using this account's configured defaults - it intentionally
does NOT support encryption; do not try to add it here, add it to the
`pushover_next.send_message` service instead.
"""
from __future__ import annotations

import logging

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PushoverClient, PushoverMessage
from .const import (
    CONF_DEFAULT_DEVICE,
    CONF_DEFAULT_SOUND,
    CONF_DEFAULT_TTL,
    DATA_CLIENTS,
    DOMAIN,
)
from .exceptions import PushoverNextError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Pushover Next notify entity for a config entry."""
    client = hass.data[DOMAIN][DATA_CLIENTS][entry.entry_id]
    async_add_entities([PushoverNextNotifyEntity(entry, client)])


class PushoverNextNotifyEntity(NotifyEntity):
    """Send a plain message using this account's configured defaults."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry, client: PushoverClient) -> None:
        """Bind this entity to a config entry and its Pushover client."""
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Pushover",
            "entry_type": "service",
        }

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a message with this account's default device/sound/ttl."""
        options = self._entry.options
        device = options.get(CONF_DEFAULT_DEVICE)
        pushover_message = PushoverMessage(
            message=message,
            title=title,
            device=[device] if device else None,
            sound=options.get(CONF_DEFAULT_SOUND),
            ttl=options.get(CONF_DEFAULT_TTL) or None,
        )
        try:
            await self._client.send_message(pushover_message)
        except PushoverNextError as err:
            raise HomeAssistantError(str(err)) from err
