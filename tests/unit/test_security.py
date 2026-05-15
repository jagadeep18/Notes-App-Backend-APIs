"""Unit tests for core security functions."""
from __future__ import annotations

import pytest
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_content,
    encrypt_content,
    generate_share_token,
    hash_password,
    hash_share_token,
    verify_password,
    TokenType,
)
from app.core.exceptions import DecryptionError, InvalidTokenError, TokenExpiredError


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("MySecret@1")
        assert hashed != "MySecret@1"

    def test_verify_correct_password(self):
        hashed = hash_password("MySecret@1")
        assert verify_password("MySecret@1", hashed) is True

    def test_reject_wrong_password(self):
        hashed = hash_password("MySecret@1")
        assert verify_password("wrongpass", hashed) is False

    def test_two_hashes_of_same_password_differ(self):
        """bcrypt salt ensures no two hashes are identical."""
        h1 = hash_password("MySecret@1")
        h2 = hash_password("MySecret@1")
        assert h1 != h2


class TestJWT:
    def test_create_and_decode_access_token(self):
        token = create_access_token("user-123")
        payload = decode_token(token, expected_type=TokenType.ACCESS)
        assert payload["sub"] == "user-123"
        assert payload["type"] == TokenType.ACCESS

    def test_wrong_token_type_raises(self):
        token = create_access_token("user-123")
        with pytest.raises(InvalidTokenError):
            decode_token(token, expected_type=TokenType.REFRESH)

    def test_invalid_token_raises(self):
        with pytest.raises(InvalidTokenError):
            decode_token("not.a.real.token")

    def test_refresh_token_type(self):
        token = create_refresh_token("user-456")
        payload = decode_token(token, expected_type=TokenType.REFRESH)
        assert payload["sub"] == "user-456"
        assert payload["type"] == TokenType.REFRESH


class TestShareToken:
    def test_generate_returns_raw_and_hash(self):
        raw, hashed = generate_share_token()
        assert raw != hashed
        assert len(raw) > 20
        assert len(hashed) == 64  # SHA-256 hex

    def test_hash_is_deterministic(self):
        raw, hashed = generate_share_token()
        assert hash_share_token(raw) == hashed

    def test_different_tokens_different_hashes(self):
        raw1, h1 = generate_share_token()
        raw2, h2 = generate_share_token()
        assert h1 != h2


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "This is my secret note content"
        ciphertext, key_version = encrypt_content(plaintext)
        assert ciphertext != plaintext
        assert key_version == "v1"
        assert decrypt_content(ciphertext) == plaintext

    def test_tampered_ciphertext_raises(self):
        ciphertext, _ = encrypt_content("secret")
        tampered = ciphertext[:-5] + "XXXXX"
        with pytest.raises(DecryptionError):
            decrypt_content(tampered)

    def test_empty_string_encrypts(self):
        ciphertext, _ = encrypt_content("")
        assert decrypt_content(ciphertext) == ""
