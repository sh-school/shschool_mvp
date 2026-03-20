"""
python manage.py generate_vapid_keys
يولّد VAPID keys جديدة ويطبعها للإضافة في .env
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'توليد VAPID keys لـ Push Notifications'

    def handle(self, *args, **options):
        try:
            from cryptography.hazmat.primitives.asymmetric.ec import generate_private_key, SECP256R1
            from cryptography.hazmat.primitives.serialization import (
                Encoding, PrivateFormat, PublicFormat, NoEncryption
            )
            import base64

            private_key = generate_private_key(SECP256R1())
            public_key  = private_key.public_key()

            priv_pem = private_key.private_bytes(
                Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
            ).decode().strip().replace('\n', '\\n')

            pub_pem = public_key.public_bytes(
                Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
            ).decode().strip().replace('\n', '\\n')

            pub_b64 = base64.urlsafe_b64encode(
                public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
            ).rstrip(b'=').decode()

            self.stdout.write(self.style.SUCCESS('\n✅ أضف هذه القيم في .env:\n'))
            self.stdout.write(f'VAPID_PRIVATE_KEY={priv_pem}')
            self.stdout.write(f'VAPID_PUBLIC_KEY={pub_pem}')
            self.stdout.write(f'VAPID_PUBLIC_KEY_B64={pub_b64}')
            self.stdout.write('VAPID_CLAIMS_EMAIL=admin@shahaniya.edu.qa\n')

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'خطأ: {e}'))
