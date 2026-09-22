"""`/status/` يكشف زمنَ اتّصال القاعدة وRedis وحالةَ الهجرات — لفريق العمليّات لا
لأيّ مستخدم (P4-9). كان بلا حراسة IP، بخلاف `/metrics` الذي يحرسه `internal_only`
منذ 2026-09-05؛ و`SchoolPermissionMiddleware` يمنع غيرَ المسجَّل أصلاً، فالمصادَقةُ
شرطٌ سابقٌ على `internal_only` هنا — لا بديلٌ عنه.
"""

import pytest


@pytest.mark.django_db
def test_an_authenticated_user_from_outside_is_still_refused(client, teacher_user, settings):
    settings.TRUSTED_PROXY_HOPS = 0
    client.force_login(teacher_user)
    response = client.get("/status/", REMOTE_ADDR="203.0.113.9")
    assert response.status_code == 403


@pytest.mark.django_db
def test_an_authenticated_user_from_inside_is_served(client, teacher_user):
    client.force_login(teacher_user)
    response = client.get("/status/")  # REMOTE_ADDR الافتراضيّ 127.0.0.1
    assert response.status_code == 200
