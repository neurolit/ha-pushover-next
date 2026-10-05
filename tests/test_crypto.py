"""Tests for the crypto module (ported from a separately validated script)."""
import base64

import pytest

from custom_components.pushover_next.crypto import (
    CryptoError,
    decrypt_field,
    encrypt_field,
    generate_key,
    self_test,
)

# Captured once from the standalone script this module was ported from, which
# was itself verified byte-for-byte against Pushover's own OpenSSL example
# and confirmed to decrypt correctly on a real device. If this test ever
# fails, the algorithm has silently regressed (wrong gzip settings, wrong
# HMAC input order, wrong IV/HMAC length, ...) - do not "fix" it by updating
# the vector, fix the code.
KNOWN_KEY = "1f046d257b8eeaf278c5218fe03a9887c21f80ecd5ad11e39f28cb7cb8b9ce03"
KNOWN_PLAINTEXT = "known-vector regression check"
KNOWN_CIPHERTEXT_B64 = (
    "3sBQOOIEaZjUiKRl9RckIeIzhMWE7ujDDSUYqrrFgHc65ll9sKpu1KTVM7mWXp/b"
    "VUi7f0SwzRZNKhumn7aaJ4rTGnwlCw9roA0RmLdHITTIuPeL/PXPawSN2tvklam3"
    "bAZxcbOslp1JMlZ+55wShQ=="
)


def test_known_vector_decrypts_correctly():
    assert decrypt_field(KNOWN_CIPHERTEXT_B64, KNOWN_KEY) == KNOWN_PLAINTEXT


@pytest.mark.parametrize(
    "plaintext",
    ["hellorld", "Message avec accents : éàç€", "x" * 1024, ""],
)
def test_round_trip(plaintext):
    key = generate_key()
    encrypted = encrypt_field(plaintext, key)
    assert decrypt_field(encrypted, key) == plaintext


def test_generate_key_is_64_hex_chars():
    key = generate_key()
    assert len(key) == 64
    bytes.fromhex(key)  # raises if not valid hex


def test_wrong_key_fails_hmac():
    key = generate_key()
    other_key = generate_key()
    encrypted = encrypt_field("secret", key)
    with pytest.raises(CryptoError):
        decrypt_field(encrypted, other_key)


def test_tampered_payload_fails_hmac():
    key = generate_key()
    encrypted = encrypt_field("secret", key)
    raw = bytearray(base64.b64decode(encrypted))
    raw[-1] ^= 0xFF  # flip a bit in the HMAC tag
    tampered = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(CryptoError):
        decrypt_field(tampered, key)


@pytest.mark.parametrize("bad_key", ["too-short", "f" * 63, "g" * 64, "f" * 65])
def test_invalid_key_format_rejected(bad_key):
    with pytest.raises(CryptoError):
        encrypt_field("x", bad_key)


def test_self_test_valid_key():
    assert self_test(generate_key()) is True


def test_self_test_invalid_key():
    assert self_test("not-a-valid-key") is False
