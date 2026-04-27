import pytest
from app.auth.api_key import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    looks_like_api_key,
)


def test_generate_returns_prefixed_plaintext_hash_and_last_four():
    plaintext, key_hash, last_four = generate_api_key()
    assert plaintext.startswith(API_KEY_PREFIX)
    assert len(plaintext) > len(API_KEY_PREFIX) + 20
    assert last_four == plaintext[-4:]
    assert key_hash == hash_api_key(plaintext)


def test_generate_produces_unique_values():
    a, _, _ = generate_api_key()
    b, _, _ = generate_api_key()
    assert a != b


def test_hash_is_deterministic():
    plaintext, key_hash, _ = generate_api_key()
    assert hash_api_key(plaintext) == key_hash


def test_hash_requires_secret(monkeypatch):
    monkeypatch.setenv("API_KEY_HMAC_SECRET", "")
    with pytest.raises(RuntimeError):
        hash_api_key("hou_anything")


def test_looks_like_api_key():
    assert looks_like_api_key("hou_abc")
    assert not looks_like_api_key("eyJhbGciOi...")
    assert not looks_like_api_key("")
