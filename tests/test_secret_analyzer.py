from __future__ import annotations

import pytest

from project_nurilab.analyzers.secrets import (
    _is_placeholder,
    _preview,
    find_potential_secrets,
)


@pytest.mark.parametrize(
    "placeholder_value",
    [
        "example",
        "EXAMPLE",
        "sample",
        "dummy",
        "placeholder",
        "changeme",
        "replace-me",
        "replace_me",
        "not-a-secret",
        "not_a_secret",
        "test-token",
        "test_token",
        "your_api_key",
        "YOUR_API_KEY_HERE",
        "your-secret-token",
        "your-password",
        "<API_KEY>",
        "<insert_token_here>",
        "${DB_PASSWORD}",
        "${SECRET_KEY}",
        "  dummy  ",
        "  your_key  ",
    ],
)
def test_is_placeholder_true_for_placeholders(placeholder_value: str) -> None:
    assert _is_placeholder(placeholder_value) is True


@pytest.mark.parametrize(
    "real_secret_value",
    [
        "sk_live_1234567890abcdef",
        "ghp_1234567890abcdef1234567890abcdef",
        "ak_live_sample98234710928347109823471098",
        "8f7b2c9e1a4d5f6e8b7c6d5e4f3a2b1c",
        "my_actual_complex_password_1234!",
    ],
)
def test_is_placeholder_false_for_real_secrets(real_secret_value: str) -> None:
    assert _is_placeholder(real_secret_value) is False


def test_find_potential_secrets_suppresses_explicit_placeholders() -> None:
    source_lines = [
        'api_key = "your_api_key_here"',
        'API_SECRET = "your-secret-token"',
        'token = "<INSERT_TOKEN_HERE>"',
        'password = "${DATABASE_PASSWORD}"',
        'secret = "changeme"',
        'token = "test-token"',
        'api_key = "placeholder"',
        'pwd = "dummy"',
    ]
    findings = find_potential_secrets(source_lines)
    assert findings == []


def test_find_potential_secrets_detects_real_secret_literals() -> None:
    source_lines = [
        "# harmless comment",
        'api_key = "sk_live_1234567890abcdef"',
        'token = "ak_live_sample98234710928347109823471098"',
        'password = "SuperSecretPassword123!"',
    ]
    findings = find_potential_secrets(source_lines)
    assert len(findings) == 3

    assert findings[0].kind == "api_key"
    assert findings[0].line == 2
    assert findings[0].severity == "high"
    assert findings[0].preview.startswith("sk_l")
    assert "sk_live_1234567890abcdef" not in findings[0].preview

    assert findings[1].kind == "token"
    assert findings[1].line == 3
    assert findings[1].severity == "high"

    assert findings[2].kind == "password"
    assert findings[2].line == 4
    assert findings[2].severity == "high"


def test_find_potential_secrets_detects_private_key_markers() -> None:
    source_lines = [
        "-----BEGIN RSA PRIVATE KEY-----",
        "MIIEowIBAAKCAQEA0Y...",
        "-----END RSA PRIVATE KEY-----",
    ]
    findings = find_potential_secrets(source_lines)
    assert len(findings) == 1
    assert findings[0].kind == "private_key"
    assert findings[0].line == 1
    assert findings[0].severity == "critical"
    assert findings[0].preview == "-----BEGIN ... PRIVATE KEY-----"


def test_preview_masking_contract() -> None:
    assert _preview("short") == "shor****"
    assert _preview("123") == "***"
    assert _preview("1234") == "****"
    assert _preview("sk_live_abcdef123456") == "sk_l****************"
    assert "abcdef123456" not in _preview("sk_live_abcdef123456")
