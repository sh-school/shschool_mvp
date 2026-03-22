"""
core/managers.py — Custom Managers للنماذج الأساسية
=====================================================
"""

from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """
    Manager مخصص يستخدم national_id بدل email.
    يُدمج مع UserQuerySet ليوفّر chainable methods
    على مستوى الـ Model (CustomUser.objects.students().search(...)).
    """

    def get_queryset(self):
        from .querysets import UserQuerySet

        return UserQuerySet(self.model, using=self._db)

    # ── البحث الذكي (مباشرة على المانجر) ─────────────────────────────────

    def search(self, query: str):
        return self.get_queryset().search(query)

    def search_fuzzy(self, query: str, threshold: float = 0.2):
        return self.get_queryset().search_fuzzy(query, threshold)

    def search_simple(self, query: str):
        return self.get_queryset().search_simple(query)

    # ── الفلترة حسب الدور ──────────────────────────────────────────────────

    def students(self, school=None):
        return self.get_queryset().students(school)

    def teachers(self, school=None):
        return self.get_queryset().teachers(school)

    def parents(self):
        return self.get_queryset().parents()

    def staff(self, school=None):
        return self.get_queryset().staff(school)

    def active(self):
        return self.get_queryset().active()

    # ── إنشاء المستخدمين ──────────────────────────────────────────────────

    def create_user(self, national_id, full_name, password=None, **extra_fields):
        if not national_id:
            raise ValueError(_("الرقم الوطني مطلوب"))
        user = self.model(national_id=national_id, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, national_id, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(national_id, full_name, password, **extra_fields)
