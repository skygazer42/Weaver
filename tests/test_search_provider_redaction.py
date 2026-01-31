from tools.search import providers


def test_is_valid_api_key_rejects_common_placeholders_and_short_values():
    assert providers._is_valid_api_key("") is False
    assert providers._is_valid_api_key("   ") is False
    assert providers._is_valid_api_key("short") is False
    assert providers._is_valid_api_key("demo") is False
    assert providers._is_valid_api_key("YOUR_API_KEY_HERE") is False


def test_is_valid_api_key_accepts_reasonable_length_keys():
    assert providers._is_valid_api_key("a" * 10) is True
    assert providers._is_valid_api_key(" tvly-1234567890 ") is True


def test_sanitize_error_message_redacts_common_secret_shapes_and_urls():
    raw = (
        "request failed: https://example.com/path?x=1 "
        "token=0123456789abcdef0123456789abcdef "
        "api_key=sk-THIS_SHOULD_NOT_LEAK "
        "Authorization: Bearer abc.def.ghi"
    )
    sanitized = providers._sanitize_error_message(raw)

    assert "https://" not in sanitized
    assert "[URL_REDACTED]" in sanitized

    # Long key-like tokens should not survive.
    assert "0123456789abcdef0123456789abcdef" not in sanitized
    assert "[KEY_REDACTED]" in sanitized

    assert "api_key=[REDACTED]" in sanitized
    assert "Bearer [REDACTED]" in sanitized


def test_sanitize_error_message_limits_length():
    raw = "X" * 2000
    sanitized = providers._sanitize_error_message(raw)
    assert len(sanitized) <= 303
