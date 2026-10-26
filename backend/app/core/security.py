"""
Security and input validation helpers (Phase 1).

Protects against:
- Malformed inputs and buffer abuse (message length limits, control character stripping)
- Prompt injection from user queries
- Indirect prompt injection from untrusted document chunks (RAG context isolation)
"""
from __future__ import annotations

import re

# Maximum allowed character length for a user chat turn
MAX_USER_MESSAGE_LENGTH = 2000

# Control character pattern: ASCII 0-31 and 127, excluding \t (9), \n (10), \r (13)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_user_message(text: str) -> str:
    """
    Validate and sanitize user input before passing to the assistant service.

    - Strips leading/trailing whitespace.
    - Removes non-printable ASCII control characters.
    - Enforces maximum length of 2000 characters.

    Raises
    ------
    ValueError
        If the message is empty or exceeds the maximum length.
    """
    if text is None:
        raise ValueError("User message cannot be None.")

    # Strip control characters
    sanitized = _CONTROL_CHAR_RE.sub("", text).strip()

    if not sanitized:
        raise ValueError("User message cannot be empty or contain only whitespace.")

    if len(sanitized) > MAX_USER_MESSAGE_LENGTH:
        raise ValueError(
            f"User message exceeds maximum length of {MAX_USER_MESSAGE_LENGTH} characters."
        )

    return sanitized


def sanitize_retrieved_content(text: str) -> str:
    """
    Sanitize text chunks retrieved from external documents (PDF/DOCX/TXT)
    before injecting them into prompt context.

    Prevents indirect prompt injection by:
    - Stripping control characters and null bytes.
    - Wrapping content in unambiguous untrusted context markers.
    """
    if not text:
        return ""

    cleaned = _CONTROL_CHAR_RE.sub("", text).strip()

    # Wrap in structural boundaries so the LLM treats it as reference data, not instructions
    return f"<untrusted_document_context>\n{cleaned}\n</untrusted_document_context>"


def validate_uploaded_file(
    filename: str,
    content: bytes,
    allowed_extensions: set[str],
    max_bytes: int = 20 * 1024 * 1024,
) -> str:
    """
    Validate an uploaded file against extension, file size, and magic bytes.

    Guards against:
    - Path traversal via filenames
    - 0-byte or oversized uploads
    - Extension spoofing (e.g. uploading an executable disguised as .pdf)

    Returns
    -------
    str
        The verified lowercase extension.

    Raises
    ------
    ValueError
        If the file violates size, extension, or format constraints.
    """
    import os

    if not filename or not filename.strip():
        raise ValueError("Filename cannot be empty.")

    if not content or len(content) == 0:
        raise ValueError("Uploaded file is empty (0 bytes).")

    if len(content) > max_bytes:
        raise ValueError(
            f"File size ({len(content)} bytes) exceeds the maximum allowed limit of {max_bytes} bytes."
        )

    _, ext = os.path.splitext(filename)
    ext_lower = ext.lower()
    if ext_lower not in allowed_extensions:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Allowed: {sorted(list(allowed_extensions))}"
        )

    # Magic byte inspection
    if ext_lower == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("File content does not match PDF format (missing %PDF- header).")
    elif ext_lower == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            raise ValueError("File content does not match DOCX format (invalid ZIP/OpenXML signature).")
    elif ext_lower in (".png",):
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("File content does not match PNG format signature.")
    elif ext_lower in (".jpg", ".jpeg"):
        if not content.startswith(b"\xff\xd8\xff"):
            raise ValueError("File content does not match JPEG format signature.")
    elif ext_lower == ".txt":
        # Ensure it is valid text and not an executable binary
        if b"\x00" in content:
            raise ValueError("Text file contains binary null bytes, which is not permitted.")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
            except Exception as exc:
                raise ValueError(f"Text file could not be decoded: {exc}")

    return ext_lower


