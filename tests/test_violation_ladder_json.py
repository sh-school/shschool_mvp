"""[LEGAL] سلّمُ المخالفات في قاعدة البيانات — حارسٌ على ladder_json.

يتحقّق من:
1. Ladder.to_json() يُنتج بنيةً صحيحة بلا استثناء.
2. seed_violations_2026 يُحقن 41 مخالفةً مع سلّمها في ViolationCategory.
3. استعلاماتٌ مباشرةٌ على ladder_json__* تعمل (JSONB في PG أو JSON في SQLite).
4. 4-15 ت2: إحالةُ الحماية **قبل** الفصل — الترتيبُ الصحيح المُدمَج في #667 + #658.
5. D1: 6 تكراراتٍ وما بعد السلّم = الإحالة للحماية.
"""

import pytest
from django.core.management import call_command

from behavior.conduct_2026 import CATALOG, LADDERS

# ════════════════════════════════════════════════════════════════════
# 1. Ladder.to_json() — بلا DB
# ════════════════════════════════════════════════════════════════════


def test_to_json_structure_d4_danger():
    ladder = LADDERS["d4_danger"]
    data = ladder.to_json()

    assert data["ladder_key"] == "d4_danger"
    assert data["max_reps"] == len(ladder.steps)
    assert len(data["steps"]) == data["max_reps"]

    first_step = data["steps"][0]
    assert first_step["rep"] == 1
    assert isinstance(first_step["actions"], list)
    assert all("actor" in a and "action" in a for a in first_step["actions"])


def test_to_json_all_ladders_no_exception():
    """كلُّ السلالم تُحوَّل بلا استثناء."""
    for key, ladder in LADDERS.items():
        data = ladder.to_json()
        assert data["ladder_key"] == key
        assert data["max_reps"] >= 1


def test_to_json_d1_six_reps():
    data = LADDERS["d1"].to_json()
    assert data["max_reps"] == 6
    assert data["beyond"] != ""


# ════════════════════════════════════════════════════════════════════
# 2. 4-15 ترتيب ت2 — إحالةُ الحماية أوّلاً (#667 + #658)
# ════════════════════════════════════════════════════════════════════


def test_d4_danger_rep2_protection_before_suspension():
    """4-15 ت2: الإحالة لقسم الحماية أوّلاً، ثمّ الفصل، ثمّ الجهات الأمنية."""
    ladder = LADDERS["d4_danger"]
    rep2_actions = [a["action"] for a in ladder.to_json()["steps"][1]["actions"]]

    protection_idx = next((i for i, a in enumerate(rep2_actions) if "حماية ورعاية" in a), None)
    suspension_idx = next(
        (i for i, a in enumerate(rep2_actions) if "فصل" in a and "الدوام" in a), None
    )
    security_idx = next(
        (i for i, a in enumerate(rep2_actions) if "الجهات الأمنيّة" in a or "الجهات الأمنية" in a),
        None,
    )

    assert protection_idx is not None, "إحالة الحماية مفقودة في ت2"
    assert suspension_idx is not None, "الفصل مفقود في ت2"
    assert security_idx is not None, "طلب الجهات الأمنية مفقود في ت2"

    assert (
        protection_idx < suspension_idx
    ), f"إحالة الحماية (idx={protection_idx}) يجب أن تسبق الفصل (idx={suspension_idx})"
    assert (
        suspension_idx < security_idx
    ), f"الفصل (idx={suspension_idx}) يجب أن يسبق الجهات الأمنية (idx={security_idx})"


# ════════════════════════════════════════════════════════════════════
# 3. CATALOG مكتمل — 41 مخالفة
# ════════════════════════════════════════════════════════════════════


def test_catalog_total_41():
    assert len(CATALOG) == 41


def test_catalog_degrees_count():
    from collections import Counter

    counts = Counter(v.degree for v in CATALOG)
    assert counts[1] == 9
    assert counts[2] == 7
    assert counts[3] == 10
    assert counts[4] == 15


def test_catalog_every_ladder_key_exists():
    for infraction in CATALOG:
        assert (
            infraction.ladder in LADDERS
        ), f"{infraction.code} يشير إلى سلّم غير موجود: {infraction.ladder}"


# ════════════════════════════════════════════════════════════════════
# 4. DB — seed_violations_2026 (يتطلب pytest-django وقاعدة بيانات)
# ════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_seed_populates_ladder_json():
    """بعد الـseed: كلُّ مخالفاتِ 2026 لها ladder_json (41 مخالفة)."""
    from behavior.models import ViolationCategory

    call_command("seed_violations_2026")

    catalog_codes = {inf.code for inf in CATALOG}
    with_ladder = ViolationCategory.objects.filter(
        code__in=catalog_codes, ladder_json__isnull=False
    ).count()
    assert with_ladder == 41


@pytest.mark.django_db
def test_seed_idempotent():
    """التشغيل مرّتين لا يُكرّر السجلّات."""
    from behavior.models import ViolationCategory

    call_command("seed_violations_2026")
    call_command("seed_violations_2026")

    assert ViolationCategory.objects.filter(code="4-15").count() == 1


@pytest.mark.django_db
def test_db_query_4_15_rep2_first_action_is_protection():
    """استعلامٌ مباشرٌ: أوّلُ فعلٍ في ت2 لـ4-15 يحتوي «حماية»."""
    from behavior.models import ViolationCategory

    call_command("seed_violations_2026")

    v = ViolationCategory.objects.get(code="4-15")
    rep2 = v.ladder_json["steps"][1]  # index 1 = التكرار الثاني
    first_action = rep2["actions"][0]["action"]
    assert "حماية" in first_action, f"أوّل فعلٍ في ت2 لـ4-15: «{first_action}»"


@pytest.mark.django_db
def test_db_query_ladder_key_index():
    """الاستعلام بـladder_key يعمل بسرعة."""
    from behavior.models import ViolationCategory

    call_command("seed_violations_2026")

    danger_violations = list(
        ViolationCategory.objects.filter(ladder_key="d4_danger").values_list("code", flat=True)
    )
    assert set(danger_violations) == {"4-14", "4-15"}
