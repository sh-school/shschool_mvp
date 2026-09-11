"""الرقمُ الشخصيُّ مستورٌ في الشاشة، كاملٌ في الطباعة.

الرقمُ معرّفٌ حكوميٌّ دائمٌ لا يُبدَّل، وكشفُه بالجملة أثقلُ من كشفه واحداً:
شاشةٌ فيها خمسون رقماً تُصوَّر وتُرسَل، وواحدٌ يُفتح ملفُّه لا يُصوَّر. وحاجةُ
من يقرأ كشفاً أن **يميّز** لا أن **يعرف** — وأربعُ خاناتٍ تكفي للتمييز.

والطباعةُ استثناءٌ مقصود (قرارُ المستخدم 2026-09-11): شهادةٌ أو كشفُ نتائجَ أو
تعهّدٌ برقمٍ مستورٍ لا يُغني عن صاحبه. وكذلك حقولُ الإدخال: قيمةٌ مستورةٌ في
حقلٍ تُحفَظ نجوماً.
"""

import re
from pathlib import Path

import pytest

from core.privacy import VISIBLE_TAIL, mask_national_id

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

#: وثائقُ الطباعة — الرقمُ فيها كاملٌ عمداً.
PRINTED = re.compile(r"(^reports/|^behavior/pdf/|_pdf\.html$|(^|/)print_)")

#: حقولُ الإدخال: `{{ form.national_id.value }}` قيمةٌ تُعاد إلى الحقل، وسترُها
#: يحفظ نجوماً مكانَ الرقم.
INPUT_VALUE = re.compile(r"form\.national_id")

RENDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z_.]*national_id)((?:\|[^}]*?)?)\s*\}\}")


def _screens():
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = str(path.relative_to(TEMPLATES)).replace("\\", "/")
        if PRINTED.search(rel):
            continue
        text = path.read_text(encoding="utf-8")
        for expr, filters in RENDER.findall(text):
            if INPUT_VALUE.search(expr):
                continue
            yield rel, expr, filters


def _printed():
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = str(path.relative_to(TEMPLATES)).replace("\\", "/")
        if not PRINTED.search(rel):
            continue
        for expr, filters in RENDER.findall(path.read_text(encoding="utf-8")):
            yield rel, expr, filters


class TestTheMask:
    @pytest.mark.parametrize(
        ("raw", "shown"),
        [
            ("31473600538", "*******0538"),
            ("28576002649", "*******2649"),
            ("", ""),
            (None, ""),
            ("1234", "****"),
            ("12345", "*****"),
            ("123456", "**3456"),
        ],
    )
    def test_only_the_tail_survives(self, raw, shown):
        assert mask_national_id(raw) == shown

    def test_the_tail_is_four(self):
        assert VISIBLE_TAIL == 4

    def test_a_masked_number_keeps_its_length(self):
        """الطولُ يُبقي الشكلَ مألوفاً في عمودٍ — ولا يُعيد بناءَ الرقم."""
        assert len(mask_national_id("31473600538")) == len("31473600538")

    def test_masking_twice_changes_nothing(self):
        """العرضُ يستر والقالبُ يستر — فلو لم يكن الستْرُ محايدَ التكرار
        لأكل النجومُ بعضَها وضاع الذيل."""
        once = mask_national_id("31473600538")

        assert mask_national_id(once) == once

    def test_nothing_but_the_tail_leaks(self):
        raw = "31473600538"
        assert raw[:-4] not in mask_national_id(raw)


class TestEveryScreenMasks:
    """من كتب رقماً خاماً في شاشةٍ غداً يسقط اختبارُه هنا."""

    @pytest.mark.parametrize(("path", "expr", "filters"), list(_screens()), ids=lambda v: str(v))
    def test_the_screen_masks_the_number(self, path, expr, filters):
        assert (
            "mask_id" in filters
        ), f"{path}: «{expr}» يُعرض خاماً — أضِف |mask_id (و{{% load privacy %}})"

    def test_the_sweep_actually_found_screens(self):
        """حارسٌ يمسح صفراً يمرّ دائماً."""
        assert len(list(_screens())) > 15


class TestPrintingKeepsTheFullNumber:
    """قرارُ المستخدم: الستْرُ للمنصّة لا للطباعة."""

    @pytest.mark.parametrize(("path", "expr", "filters"), list(_printed()), ids=lambda v: str(v))
    def test_the_document_is_not_masked(self, path, expr, filters):
        assert "mask_id" not in filters, f"{path}: وثيقةٌ رسميّةٌ برقمٍ مستورٍ لا تُغني عن صاحبها"

    def test_there_are_printed_documents_to_protect(self):
        assert len(list(_printed())) > 3
