"""End-to-end encryption helper for Pushover's account-wide AES secret.

Ported from a standalone script (not part of this integration) that was
validated byte-for-byte against Pushover's own OpenSSL example from
https://pushover.net/api#e2ee, and confirmed to decrypt correctly on a real
device. Do not alter the algorithm, byte order, or parameter choices here
without re-validating against that reference.

Scheme per field (message, title, url, url_title):
  1. gzip-compress the UTF-8 plaintext
  2. random 16-byte IV
  3. AES-256-CBC encrypt (PKCS7 padding) with the 32-byte key and IV
  4. HMAC-SHA256 over IV || ciphertext, same key
  5. base64(IV || ciphertext || HMAC)
"""
from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import hmac
import os
import re

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .exceptions import CryptoError

KEY_LENGTH_BYTES = 32  # 256 bits
IV_LENGTH_BYTES = 16
HMAC_LENGTH_BYTES = 32

_HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def generate_key() -> str:
    """Generate a new random 64-char hex key (256 bits)."""
    return os.urandom(KEY_LENGTH_BYTES).hex()


def validate_key_hex(key_hex: str) -> str:
    """Validate (and normalize) a 64-character hex AES secret.

    Raises CryptoError if the value isn't a well-formed 32-byte hex key.
    """
    key_hex = key_hex.strip()
    if not _HEX_KEY_RE.match(key_hex):
        raise CryptoError(
            "The encryption key must be exactly 64 hex characters "
            "(the 256-bit secret shown in the Pushover app)."
        )
    return key_hex.lower()


def _key_bytes(key_hex: str) -> bytes:
    return bytes.fromhex(validate_key_hex(key_hex))


def encrypt_field(plaintext: str, key_hex: str) -> str:
    """Encrypt a single field value with the account's AES secret.

    Returns the base64-encoded ``iv || ciphertext || hmac`` blob that should
    be sent in place of the plaintext value.
    """
    key = _key_bytes(key_hex)
    compressed = gzip.compress(plaintext.encode("utf-8"), mtime=0)

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(compressed) + padder.finalize()

    iv = os.urandom(IV_LENGTH_BYTES)
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    mac = hmac.new(key, iv + ciphertext, hashlib.sha256).digest()

    return base64.b64encode(iv + ciphertext + mac).decode("ascii")


def decrypt_field(encoded: str, key_hex: str) -> str:
    """Decrypt a field previously produced by encrypt_field.

    Pushover's servers never decrypt anything; this exists only so a key can
    be self-tested (encrypt then decrypt a canary string) before it is saved
    in the options flow, not as part of the send path.
    """
    key = _key_bytes(key_hex)
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as err:
        raise CryptoError(f"Invalid base64 payload: {err}") from err

    if len(blob) < IV_LENGTH_BYTES + HMAC_LENGTH_BYTES:
        raise CryptoError("Encrypted payload is too short to be valid.")

    iv, ciphertext, mac = (
        blob[:IV_LENGTH_BYTES],
        blob[IV_LENGTH_BYTES:-HMAC_LENGTH_BYTES],
        blob[-HMAC_LENGTH_BYTES:],
    )

    expected_mac = hmac.new(key, iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise CryptoError("HMAC verification failed; wrong key or corrupted payload.")

    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    try:
        compressed = unpadder.update(padded) + unpadder.finalize()
        return gzip.decompress(compressed).decode("utf-8")
    except ValueError as err:
        raise CryptoError(f"Could not unpad/decompress payload: {err}") from err


def self_test(key_hex: str) -> bool:
    """Round-trip a canary string through encrypt/decrypt to sanity-check a key."""
    canary = "pushover-next self-test"
    try:
        return decrypt_field(encrypt_field(canary, key_hex), key_hex) == canary
    except CryptoError:
        return False
