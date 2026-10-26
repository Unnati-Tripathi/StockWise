"""
Unit tests for security helpers (app.core.security).
"""
import pytest
from app.core.security import (
    validate_user_message,
    sanitize_retrieved_content,
    MAX_USER_MESSAGE_LENGTH,
)


def test_validate_user_message_valid():
    msg = "How many boxes of Amoxicillin do we have?"
    assert validate_user_message(msg) == msg


def test_validate_user_message_strips_control_chars():
    dirty = "Hello\x00\x07\tWorld\x1f!"
    cleaned = validate_user_message(dirty)
    assert cleaned == "Hello\tWorld!"


def test_validate_user_message_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_user_message("   ")

    with pytest.raises(ValueError, match="None"):
        validate_user_message(None)


def test_validate_user_message_rejects_too_long():
    long_msg = "A" * (MAX_USER_MESSAGE_LENGTH + 1)
    with pytest.raises(ValueError, match="exceeds maximum length"):
        validate_user_message(long_msg)


def test_sanitize_retrieved_content():
    raw = "Supplier policy:\x00 delivery within 3 days."
    sanitized = sanitize_retrieved_content(raw)
    assert "<untrusted_document_context>" in sanitized
    assert "</untrusted_document_context>" in sanitized
    assert "\x00" not in sanitized
    assert "delivery within 3 days." in sanitized


def test_sanitize_retrieved_content_empty():
    assert sanitize_retrieved_content("") == ""
    assert sanitize_retrieved_content(None) == ""
