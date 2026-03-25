"""
core/secrets_manager.py
━━━━━━━━━━━━━━━━━━━━━━━
مدير الأسرار — يدعم مصادر متعددة للمفاتيح السرية.
يستبدل .env في الإنتاج بخدمات إدارة أسرار آمنة.

المصادر المدعومة (بالترتيب):
1. AWS Secrets Manager
2. HashiCorp Vault
3. Azure Key Vault
4. متغيرات البيئة (fallback)
5. ملف .env (التطوير فقط)

الاستخدام:
    from core.secrets_manager import get_secret
    db_password = get_secret("DB_PASSWORD")
"""

import json
import logging
import os

logger = logging.getLogger("core")

# ── المصدر النشط ──────────────────────────────────────
SECRETS_BACKEND = os.environ.get("SECRETS_BACKEND", "env")
# القيم: "aws", "vault", "azure", "env"


def get_secret(key, default=""):
    """
    يجلب سراً من المصدر المُعَد.

    Args:
        key: اسم المفتاح السري
        default: القيمة الافتراضية إذا لم يُوجد

    Returns:
        str: قيمة السر
    """
    backend = SECRETS_BACKEND.lower()

    if backend == "aws":
        return _get_from_aws(key, default)
    elif backend == "vault":
        return _get_from_vault(key, default)
    elif backend == "azure":
        return _get_from_azure(key, default)
    else:
        return os.environ.get(key, default)


def _get_from_aws(key, default=""):
    """جلب السر من AWS Secrets Manager."""
    try:
        import boto3

        region = os.environ.get("AWS_REGION", "me-south-1")
        secret_name = os.environ.get("AWS_SECRET_NAME", "schoolos/production")

        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)

        secrets = json.loads(response["SecretString"])
        return secrets.get(key, default)
    except ImportError:
        logger.warning("boto3 غير مثبت — استخدم: pip install boto3")
        return os.environ.get(key, default)
    except Exception as e:
        logger.error("AWS Secrets Manager خطأ: %s — fallback إلى env", e)
        return os.environ.get(key, default)


def _get_from_vault(key, default=""):
    """جلب السر من HashiCorp Vault."""
    try:
        import hvac

        vault_url = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")
        vault_token = os.environ.get("VAULT_TOKEN", "")
        vault_path = os.environ.get("VAULT_SECRET_PATH", "secret/data/schoolos")

        client = hvac.Client(url=vault_url, token=vault_token)
        response = client.secrets.kv.v2.read_secret_version(path=vault_path)

        secrets = response["data"]["data"]
        return secrets.get(key, default)
    except ImportError:
        logger.warning("hvac غير مثبت — استخدم: pip install hvac")
        return os.environ.get(key, default)
    except Exception as e:
        logger.error("Vault خطأ: %s — fallback إلى env", e)
        return os.environ.get(key, default)


def _get_from_azure(key, default=""):
    """جلب السر من Azure Key Vault."""
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        vault_url = os.environ.get("AZURE_VAULT_URL", "")
        if not vault_url:
            return os.environ.get(key, default)

        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)

        # Azure Key Vault لا يقبل _ في الأسماء
        azure_key = key.replace("_", "-").lower()
        secret = client.get_secret(azure_key)
        return secret.value or default
    except ImportError:
        logger.warning("azure-keyvault-secrets غير مثبت")
        return os.environ.get(key, default)
    except Exception as e:
        logger.error("Azure Key Vault خطأ: %s — fallback إلى env", e)
        return os.environ.get(key, default)


# ── دوال مساعدة ──────────────────────────────────────

def get_all_secrets(keys):
    """جلب مجموعة أسرار دفعة واحدة."""
    return {key: get_secret(key) for key in keys}


def is_secrets_manager_available():
    """يتحقق من توفر خدمة إدارة الأسرار."""
    backend = SECRETS_BACKEND.lower()
    if backend == "env":
        return True
    try:
        # اختبار اتصال بسيط
        get_secret("__health_check__", "ok")
        return True
    except Exception:
        return False
