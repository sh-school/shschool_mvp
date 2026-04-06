"""
tests/test_secrets_manager.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
اختبارات مدير الأسرار.
"""

import os
from unittest.mock import patch

from core.secrets_manager import get_all_secrets, get_secret, is_secrets_manager_available


class TestSecretsManager:
    """اختبارات مدير الأسرار."""

    def test_env_backend_reads_environment(self):
        """الخلفية البيئية تقرأ المتغيرات."""
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env", "TEST_SECRET": "hello"}):
            result = get_secret("TEST_SECRET")
            assert result == "hello"

    def test_env_backend_returns_default(self):
        """الخلفية البيئية ترجع القيمة الافتراضية."""
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            result = get_secret("NON_EXISTENT_KEY_XYZ", "default_val")
            assert result == "default_val"

    def test_get_all_secrets(self):
        """جلب عدة أسرار دفعة واحدة."""
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env", "A": "1", "B": "2"}):
            result = get_all_secrets(["A", "B"])
            assert result == {"A": "1", "B": "2"}

    def test_is_available_for_env_backend(self):
        """الخلفية البيئية متاحة دائماً."""
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}):
            assert is_secrets_manager_available() is True

    def test_aws_fallback_without_boto3(self):
        """AWS تتراجع للمتغيرات البيئية بدون boto3."""
        with patch.dict(
            os.environ,
            {"SECRETS_BACKEND": "aws", "MY_KEY": "env_value"},
        ):
            result = get_secret("MY_KEY")
            assert result == "env_value"

    def test_vault_fallback_without_hvac(self):
        """Vault يتراجع للمتغيرات البيئية بدون hvac."""
        with patch.dict(
            os.environ,
            {"SECRETS_BACKEND": "vault", "MY_KEY": "env_value"},
        ):
            result = get_secret("MY_KEY")
            assert result == "env_value"

    def test_azure_fallback_without_sdk(self):
        """Azure يتراجع للمتغيرات البيئية بدون SDK."""
        with patch.dict(
            os.environ,
            {"SECRETS_BACKEND": "azure", "MY_KEY": "env_value"},
        ):
            result = get_secret("MY_KEY")
            assert result == "env_value"
