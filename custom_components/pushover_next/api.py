"""Thin async client for the parts of the Pushover API this integration uses."""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .const import (
    API_CANCEL_BY_TAG_URL,
    API_CANCEL_RECEIPT_URL,
    API_GROUP_URL,
    API_MESSAGES_URL,
    API_RECEIPT_URL,
    API_SOUNDS_URL,
    API_VALIDATE_URL,
    MAX_ATTACHMENT_BYTES,
)
from .exceptions import ApiError, CannotConnect, InvalidAuth, RateLimitError

_LOGGER = logging.getLogger(__name__)


@dataclass
class PushoverMessage:
    """A fully-specified Pushover message request.

    Every field maps directly to a Pushover Messages API parameter. Only
    ``message`` is required; everything else is omitted from the request
    when left as ``None``.
    """

    message: str
    title: str | None = None
    priority: int | None = None
    sound: str | None = None
    url: str | None = None
    url_title: str | None = None
    device: list[str] | None = None
    timestamp: int | None = None
    html: bool | None = None
    monospace: bool | None = None
    ttl: int | None = None
    tags: list[str] | None = None
    callback: str | None = None
    retry: int | None = None
    expire: int | None = None
    attachment: bytes | None = None
    attachment_filename: str = "attachment"
    attachment_base64: str | None = None
    attachment_type: str | None = None
    encrypted: bool = False

    def to_form_fields(self) -> dict[str, str]:
        """Build the plain (non-file) form fields for this message."""
        fields: dict[str, str] = {"message": self.message}

        if self.title is not None:
            fields["title"] = self.title
        if self.priority is not None:
            fields["priority"] = str(self.priority)
        if self.sound is not None:
            fields["sound"] = self.sound
        if self.url is not None:
            fields["url"] = self.url
        if self.url_title is not None:
            fields["url_title"] = self.url_title
        if self.device:
            fields["device"] = ",".join(self.device)
        if self.timestamp is not None:
            fields["timestamp"] = str(self.timestamp)
        if self.html:
            fields["html"] = "1"
        if self.monospace:
            fields["monospace"] = "1"
        if self.ttl is not None:
            fields["ttl"] = str(self.ttl)
        if self.tags:
            fields["tags"] = ",".join(self.tags)
        if self.callback is not None:
            fields["callback"] = self.callback
        if self.retry is not None:
            fields["retry"] = str(self.retry)
        if self.expire is not None:
            fields["expire"] = str(self.expire)
        if self.attachment_base64 is not None:
            fields["attachment_base64"] = self.attachment_base64
            if self.attachment_type is not None:
                fields["attachment_type"] = self.attachment_type
        if self.encrypted:
            fields["encrypted"] = "1"

        return fields


@dataclass
class PushoverResponse:
    """Parsed JSON response from a Pushover API call."""

    status: int
    request: str | None
    receipt: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return True if Pushover reported success (status == 1)."""
        return self.status == 1


class PushoverClient:
    """Async wrapper around the Pushover HTTP API.

    Does not know anything about encryption: callers that want an encrypted
    send must call the crypto module themselves and pass already-encrypted
    field values plus ``encrypted=True`` on the PushoverMessage.
    """

    def __init__(self, session: aiohttp.ClientSession, api_token: str, user_key: str) -> None:
        """Store the shared aiohttp session and this app/user's credentials."""
        self._session = session
        self._api_token = api_token
        self._user_key = user_key

    async def validate_user(self, device: str | None = None) -> dict[str, Any]:
        """Validate the configured user/group key (and optionally a device name)."""
        data = {"token": self._api_token, "user": self._user_key}
        if device:
            data["device"] = device
        return await self._post_form(API_VALIDATE_URL, data)

    async def get_group_info(self, group_key: str | None = None) -> dict[str, Any]:
        """Fetch a delivery group's name and member users/devices.

        Only meaningful when the configured user_key is actually a Pushover
        *group* key rather than a plain user key; raises ApiError (via
        _parse_response) otherwise.
        """
        url = API_GROUP_URL.format(group=group_key or self._user_key)
        async with self._session.get(url, params={"token": self._api_token}) as resp:
            return await self._parse_response(resp)

    async def get_sounds(self) -> dict[str, str]:
        """Return the {sound_key: description} mapping Pushover currently supports."""
        async with self._session.get(API_SOUNDS_URL, params={"token": self._api_token}) as resp:
            payload = await self._parse_response(resp)
        return payload.get("sounds", {})

    async def send_message(self, message: PushoverMessage) -> PushoverResponse:
        """Send a message, returning the parsed response (including any receipt id)."""
        fields = message.to_form_fields()
        fields["token"] = self._api_token
        fields["user"] = self._user_key

        if message.attachment is not None:
            if len(message.attachment) > MAX_ATTACHMENT_BYTES:
                raise ApiError(0, [f"attachment exceeds {MAX_ATTACHMENT_BYTES} byte limit"])
            form = aiohttp.FormData()
            for key, value in fields.items():
                form.add_field(key, value)
            form.add_field(
                "attachment",
                message.attachment,
                filename=message.attachment_filename,
                content_type="application/octet-stream",
            )
            payload = await self._post(API_MESSAGES_URL, form)
        else:
            payload = await self._post_form(API_MESSAGES_URL, fields)

        return PushoverResponse(
            status=payload.get("status", 0),
            request=payload.get("request"),
            receipt=payload.get("receipt"),
            raw=payload,
        )

    async def get_receipt(self, receipt: str) -> dict[str, Any]:
        """Fetch the current delivery/acknowledgement status of an emergency receipt."""
        url = API_RECEIPT_URL.format(receipt=receipt)
        async with self._session.get(url, params={"token": self._api_token}) as resp:
            return await self._parse_response(resp)

    async def cancel_receipt(self, receipt: str) -> dict[str, Any]:
        """Stop further retries of an emergency-priority (priority=2) message."""
        url = API_CANCEL_RECEIPT_URL.format(receipt=receipt)
        return await self._post_form(url, {"token": self._api_token})

    async def cancel_by_tag(self, tag: str) -> dict[str, Any]:
        """Stop further retries of every pending emergency message carrying `tag`."""
        url = API_CANCEL_BY_TAG_URL.format(tag=tag)
        return await self._post_form(url, {"token": self._api_token})

    async def _post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._session.post(url, data=data) as resp:
                return await self._parse_response(resp)
        except aiohttp.ClientError as err:
            raise CannotConnect(str(err)) from err

    async def _post(self, url: str, data: aiohttp.FormData) -> dict[str, Any]:
        try:
            async with self._session.post(url, data=data) as resp:
                return await self._parse_response(resp)
        except aiohttp.ClientError as err:
            raise CannotConnect(str(err)) from err

    async def _parse_response(self, resp: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            payload: dict[str, Any] = await resp.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError) as err:
            text = await resp.text()
            raise ApiError(resp.status, [f"non-JSON response: {text[:200]}"]) from err

        if resp.status == 429:
            raise RateLimitError("Pushover application message limit reached for this billing period.")

        status = payload.get("status", 0)
        if status != 1:
            errors = payload.get("errors", ["unknown error"])
            if resp.status in (401, 400) and (
                "token" in " ".join(errors).lower() or "application" in " ".join(errors).lower()
            ):
                raise InvalidAuth(", ".join(errors))
            raise ApiError(resp.status, errors)

        return payload


def encode_attachment_base64(data: bytes) -> str:
    """Base64-encode raw attachment bytes for the attachment_base64 field."""
    return base64.b64encode(data).decode("ascii")
