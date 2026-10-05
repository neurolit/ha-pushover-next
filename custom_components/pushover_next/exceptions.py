"""Exceptions for the Pushover Next integration."""
from __future__ import annotations


class PushoverNextError(Exception):
    """Base error for anything that goes wrong talking to Pushover."""


class CannotConnect(PushoverNextError):
    """Raised on a network-level failure reaching the Pushover API."""


class InvalidAuth(PushoverNextError):
    """Raised when the application token or user/group key is rejected."""


class RateLimitError(PushoverNextError):
    """Raised when the application's monthly message limit is exceeded."""


class ApiError(PushoverNextError):
    """Raised for any other error response returned by the Pushover API."""

    def __init__(self, status: int, errors: list[str]) -> None:
        """Store the numeric status and the list of error strings."""
        self.status = status
        self.errors = errors
        super().__init__(f"Pushover API error (status={status}): {', '.join(errors) or 'unknown error'}")


class CryptoError(PushoverNextError):
    """Raised when a message cannot be encrypted or decrypted as requested."""
