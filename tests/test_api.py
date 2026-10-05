"""Tests for the async Pushover API client.

Uses a small hand-rolled fake aiohttp session instead of a third-party
mocking library, since those libraries reach into aiohttp's internal
ClientResponse construction and break on nearly every aiohttp release.
"""
from __future__ import annotations

import aiohttp
import pytest

from custom_components.pushover_next.api import (
    PushoverClient,
    PushoverMessage,
    encode_attachment_base64,
)
from custom_components.pushover_next.exceptions import ApiError, InvalidAuth, RateLimitError


class _FakeResponse:
    def __init__(self, status=200, payload=None, text_body=""):
        self.status = status
        self._payload = payload
        self._text = text_body

    async def json(self, content_type=None):
        if self._payload is None:
            raise aiohttp.ContentTypeError(None, None)
        return self._payload

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Records every get/post call and replays a queue of canned responses."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self._responses: list[_FakeResponse] = []
        self._raise: Exception | None = None

    def queue_response(self, response: _FakeResponse) -> None:
        self._responses.append(response)

    def raise_on_next_call(self, exc: Exception) -> None:
        self._raise = exc

    def get(self, url, **kwargs):
        return self._handle("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._handle("POST", url, kwargs)

    def _handle(self, method, url, kwargs):
        if self._raise is not None:
            exc, self._raise = self._raise, None
            raise exc
        self.calls.append((method, url, kwargs))
        return self._responses.pop(0)


@pytest.fixture
def session():
    return _FakeSession()


@pytest.fixture
def client(session):
    return PushoverClient(session, api_token="TOKEN", user_key="USER")


async def test_validate_user_success(client, session):
    session.queue_response(_FakeResponse(payload={"status": 1, "devices": ["phone"], "request": "r1"}))
    result = await client.validate_user()
    assert result["devices"] == ["phone"]
    assert session.calls[0][1].endswith("/users/validate.json")


async def test_validate_user_invalid_auth(client, session):
    session.queue_response(
        _FakeResponse(status=400, payload={"status": 0, "errors": ["application token is invalid"]})
    )
    with pytest.raises(InvalidAuth):
        await client.validate_user()


async def test_get_sounds(client, session):
    session.queue_response(
        _FakeResponse(payload={"status": 1, "sounds": {"pushover": "Pushover (default)"}})
    )
    sounds = await client.get_sounds()
    assert sounds == {"pushover": "Pushover (default)"}


async def test_get_group_info(client, session):
    session.queue_response(_FakeResponse(payload={"status": 1, "name": "Family", "users": []}))
    result = await client.get_group_info()
    assert result["name"] == "Family"


async def test_send_message_plain(client, session):
    session.queue_response(_FakeResponse(payload={"status": 1, "request": "r1"}))
    msg = PushoverMessage(message="hello", tags=["a", "b"], html=True)
    response = await client.send_message(msg)
    assert response.ok
    assert response.request == "r1"

    _, url, kwargs = session.calls[0]
    assert url.endswith("/messages.json")
    sent = kwargs["data"]
    assert sent["message"] == "hello"
    assert sent["tags"] == "a,b"
    assert sent["html"] == "1"
    assert "attachment" not in sent


async def test_send_message_with_attachment_uses_multipart(client, session):
    session.queue_response(_FakeResponse(payload={"status": 1, "request": "r2"}))
    msg = PushoverMessage(message="hello", attachment=b"fake-image-bytes")
    response = await client.send_message(msg)
    assert response.ok

    _, _, kwargs = session.calls[0]
    assert isinstance(kwargs["data"], aiohttp.FormData)


async def test_send_message_encrypted_sets_flag(client, session):
    session.queue_response(_FakeResponse(payload={"status": 1, "request": "r3"}))
    msg = PushoverMessage(message="ciphertext", title="ciphertext-title", encrypted=True)
    await client.send_message(msg)

    _, _, kwargs = session.calls[0]
    assert kwargs["data"]["encrypted"] == "1"


async def test_rate_limit_raises(client, session):
    session.queue_response(_FakeResponse(status=429, payload={"status": 0, "errors": ["limit"]}))
    with pytest.raises(RateLimitError):
        await client.send_message(PushoverMessage(message="hi"))


async def test_generic_api_error(client, session):
    session.queue_response(_FakeResponse(status=500, payload={"status": 0, "errors": ["server error"]}))
    with pytest.raises(ApiError):
        await client.send_message(PushoverMessage(message="hi"))


async def test_non_json_response_raises_api_error(client, session):
    session.queue_response(_FakeResponse(payload=None, text_body="<html>not json</html>"))
    with pytest.raises(ApiError):
        await client.send_message(PushoverMessage(message="hi"))


async def test_cancel_by_tag(client, session):
    session.queue_response(_FakeResponse(payload={"status": 1}))
    result = await client.cancel_by_tag("mytag")
    assert result["status"] == 1
    assert session.calls[0][1].endswith("/receipts/cancel_by_tag/mytag.json")


async def test_connection_error_wrapped(client, session):
    from custom_components.pushover_next.exceptions import CannotConnect

    session.raise_on_next_call(aiohttp.ClientConnectionError("boom"))
    with pytest.raises(CannotConnect):
        await client.send_message(PushoverMessage(message="hi"))


def test_encode_attachment_base64():
    encoded = encode_attachment_base64(b"abc")
    assert encoded == "YWJj"
