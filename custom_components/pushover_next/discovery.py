"""Best-effort live lookups of an account's Pushover devices and sounds.

Shared by config_flow.py (to populate the options-flow dropdowns) and
__init__.py (to populate a live select menu for the device/sound fields of
the send_message service, since services.yaml itself can't know a
particular account's device names or an application's custom sound catalog
ahead of time). Every function here is best-effort: a failure must never
block config entry setup or service calls, only degrade a dropdown to free
text / a fallback list.
"""
from __future__ import annotations

import aiohttp

from .api import PushoverClient
from .const import FALLBACK_SOUNDS
from .exceptions import PushoverNextError

_TRANSIENT_ERRORS = (PushoverNextError, aiohttp.ClientError, TimeoutError)


async def async_discover_devices(client: PushoverClient) -> list[str]:
    """Return the device names Pushover knows about for this user or group key.

    For a plain user key, /users/validate.json lists that user's own
    devices. For a *group* key, the same call doesn't enumerate members, so
    we also try the /groups/ endpoint, which lists each member's device and
    succeeds only when the configured key is actually a group key.
    """
    device_names: list[str] = []

    try:
        validate_result = await client.validate_user()
    except _TRANSIENT_ERRORS:
        validate_result = {}
    device_names.extend(validate_result.get("devices", []))

    try:
        group_result = await client.get_group_info()
    except _TRANSIENT_ERRORS:
        group_result = {}
    for member in group_result.get("users", []):
        device = member.get("device")
        if device:
            device_names.append(device)

    # De-duplicate while preserving order.
    return list(dict.fromkeys(device_names))


async def async_discover_sounds(client: PushoverClient) -> list[dict[str, str]]:
    """Return the current Pushover sound catalog as select options.

    Falls back to the last known-good hardcoded list if the API call fails
    (e.g. offline), so callers still get something to show, just without
    descriptions.
    """
    try:
        sounds = await client.get_sounds()
    except _TRANSIENT_ERRORS:
        return [{"value": sound, "label": sound} for sound in FALLBACK_SOUNDS]

    return [{"value": key, "label": f"{key} — {description}"} for key, description in sounds.items()]
