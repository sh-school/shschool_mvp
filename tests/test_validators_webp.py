"""tests/test_validators_webp.py — فحص magic bytes لصيغة WebP."""

import pytest
from django.core.exceptions import ValidationError

from core.validators import FileTypeValidator


def test_webp_valid_magic_passes():
    v = FileTypeValidator(allowed_types="image")
    # RIFF + 4 بايت حجم + WEBP
    header = b"RIFF\x10\x00\x00\x00WEBP" + b"VP8 "
    v._check_magic_bytes(header, ".webp")  # لا يرفع استثناء


def test_webp_wrong_magic_rejected():
    v = FileTypeValidator(allowed_types="image")
    with pytest.raises(ValidationError):
        # محتوى ليس WebP (مثلاً PNG مُعاد تسميته .webp)
        v._check_magic_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", ".webp")


def test_webp_riff_but_not_webp_rejected():
    v = FileTypeValidator(allowed_types="image")
    with pytest.raises(ValidationError):
        # RIFF لكنه WAV لا WebP
        v._check_magic_bytes(b"RIFF\x10\x00\x00\x00WAVEfmt ", ".webp")
