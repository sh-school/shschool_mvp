"""محلِّلُ جدول aSc المُصدَّر PDF — مواضعُ الحصص وحدَها، بلا قاعدةِ بيانات.

كلُّ صفحةٍ شبكةُ خمسةِ أيّامٍ (الأحد..الخميس) في سبعِ حصص. حدودُها من `page.lines`:
تسعُ قيمِ x (ثماني أعمدة) وسبعُ قيمِ y (صفُّ العنوان وخمسةُ أيّام). والصفحةُ يمينٌ إلى يسار:

    العمودُ الأيمن = أسماءُ الأيّام · الحصّة = 7 − فهرسُ العمود من اليسار

وغيابُ الخطّ الرأسيّ بين عمودين في صفٍّ معناه حصّةٌ مزدوجةٌ تغطّي الخانتين. والكلمةُ العربيّةُ
تُستخرَج من الـPDF معكوسةَ الحروف، فتُعكس ثمّ تُوحَّد بـNFKC (أشكالُ العرض → الحروفُ الأصل).

    الشكلُ ≠ المعنى      الخطُّ الغائبُ هو الذي يقول «مزدوجة»، لا النصّ.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from typing import IO, Any, NamedTuple

DAYS = 5
PERIODS = 7

#: تسامحُ الإحداثيّات (نقطةُ PDF) بين خطّين يُعدّان واحداً.
TOL = 1.5

_ARABIC = re.compile("[؀-ۿﭐ-﷿ﹰ-﻿]")
_CLASS_CODE = re.compile(r"^\d{1,2}\.\d{1,2}$")
_TITLE_CLASS_CODE = re.compile(r"^(?:HC\.)?(\d{1,2}\.\d{1,2})$")
_LATIN_CODE = re.compile(r"^[A-Za-z0-9.\-_/]+$")


class AscPdfError(ValueError):
    """صفحةٌ لا تطابق الشكل المتوقَّع — تُذكر في التقرير ولا تُخمَّن."""


class Cell(NamedTuple):
    """خانةٌ غيرُ فارغة: اليومُ والحصصُ التي تغطّيها (أكثرُ من واحدةٍ حين تُزدوج) ونصُّها."""

    day: int
    periods: tuple[int, ...]
    tokens: tuple[str, ...]


class TeacherPage(NamedTuple):
    name: str
    #: (يوم، حصّة، رمزُ الشعبة، المادّة) — حصّةٌ لكلّ سطر، فالمزدوجةُ سطران.
    lessons: tuple[tuple[int, int, str, str], ...]


class ClassPage(NamedTuple):
    #: رمزُ الشعبة، وفارغٌ إن لم يطبعه العنوان.
    class_code: str
    #: خاناتُ الشعبة المشغولة (يوم، حصّة).
    slots: frozenset[tuple[int, int]]
    #: نصُّ العنوان — اسمُ الصفحة في التقرير حين يغيب الرمز.
    title: str = ""


def fix_word(text: str) -> str:
    """كلمةٌ عربيّةٌ تُعكس ثمّ NFKC؛ وغيرُ العربيّة (أرقامٌ ورموزُ قاعات) تبقى."""
    if _ARABIC.search(text):
        text = text[::-1]
    return unicodedata.normalize("NFKC", text).strip()


def _clusters(values: Iterable[float]) -> list[float]:
    """قيمٌ متقاربةٌ تُدمج في قيمةٍ واحدة (متوسّطها)، مرتّبةً تصاعديّاً."""
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] <= TOL:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


class _Grid(NamedTuple):
    xs: list[float]
    ys: list[float]
    verticals: list[tuple[float, float, float]]  # (x, أعلى، أسفل)


def _grid(page: Any) -> _Grid:
    lines = list(page.lines)
    vertical = [ln for ln in lines if abs(ln["x0"] - ln["x1"]) <= TOL]
    horizontal = [ln for ln in lines if abs(ln["top"] - ln["bottom"]) <= TOL]
    xs = _clusters(ln["x0"] for ln in vertical)
    ys = _clusters(ln["top"] for ln in horizontal)
    if len(xs) != PERIODS + 2 or len(ys) != DAYS + 2:
        raise AscPdfError(f"الشبكةُ ليست {PERIODS + 2}×{DAYS + 2} خطّاً (وُجد {len(xs)}×{len(ys)})")
    return _Grid(xs, ys, [(ln["x0"], ln["top"], ln["bottom"]) for ln in vertical])


def _words(page: Any) -> list[dict[str, Any]]:
    return [{**w, "text": fix_word(w["text"])} for w in page.extract_words() if fix_word(w["text"])]


def _center(word: dict[str, Any], low: str, high: str) -> float:
    return (word[low] + word[high]) / 2


def _logical(words: Sequence[dict[str, Any]]) -> list[str]:
    """كلماتٌ بترتيب القراءة: سطراً سطراً من الأعلى، وداخلَ السطر من اليمين."""
    ordered = sorted(
        words, key=lambda w: (round(_center(w, "top", "bottom") / (2 * TOL)), -w["x1"])
    )
    return [w["text"] for w in ordered]


def _col_of(grid: _Grid, x: float) -> int | None:
    for col in range(len(grid.xs) - 1):
        if grid.xs[col] <= x <= grid.xs[col + 1]:
            return col
    return None


def _separated(grid: _Grid, boundary: int, mid_y: float) -> bool:
    """أفيه خطٌّ رأسيٌّ على الحدّ `boundary` عند منتصف الصفّ؟"""
    x = grid.xs[boundary]
    return any(
        abs(vx - x) <= TOL and top - TOL <= mid_y <= bottom + TOL
        for vx, top, bottom in grid.verticals
    )


def _row_spans(grid: _Grid, row: int) -> list[list[int]]:
    """أعمدةُ الحصص (0..6) في صفٍّ، مدموجاً منها ما غاب الفاصلُ بينهما."""
    mid = (grid.ys[row] + grid.ys[row + 1]) / 2
    spans: list[list[int]] = [[0]]
    for col in range(1, PERIODS):
        if _separated(grid, col, mid):
            spans.append([col])
        else:
            spans[-1].append(col)
    return spans


def _cells(page: Any, grid: _Grid, words: list[dict[str, Any]]) -> list[Cell]:
    found: list[Cell] = []
    for row in range(1, DAYS + 1):
        low, high = grid.ys[row], grid.ys[row + 1]
        in_row = [w for w in words if low <= _center(w, "top", "bottom") <= high]
        for span in _row_spans(grid, row):
            inside = [w for w in in_row if _col_of(grid, _center(w, "x0", "x1")) in span]
            if inside:
                periods = tuple(sorted(PERIODS - col for col in span))
                found.append(Cell(row - 1, periods, tuple(_logical(inside))))
    return found


def _title(grid: _Grid, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [w for w in words if _center(w, "top", "bottom") < grid.ys[0]]


def _biggest_line(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """كلماتُ العنوان ذاتُ أكبر خطٍّ (حقل size)؛ وبلا الحقل تبقى كلُّها."""
    sizes = [w["size"] for w in words if w.get("size") is not None]
    if not sizes:
        return words
    top = max(sizes)
    return [w for w in words if w.get("size") is not None and top - w["size"] <= 0.5]


def _split_tokens(tokens: Sequence[str]) -> tuple[list[str], str]:
    """(رموزُ الشعب، المادّة) من نصّ خانة؛ ورمزُ القاعة اللاتينيُّ يُهمل."""
    codes = [t for t in tokens if _CLASS_CODE.match(t)]
    rest = [t for t in tokens if not _CLASS_CODE.match(t) and not _LATIN_CODE.match(t)]
    return codes, " ".join(rest)


def parse_teacher_page(page: Any, title_words: Sequence[str] = ()) -> TeacherPage:
    """صفحةُ معلّم: اسمُه من العنوان، وفي كلّ خانةٍ رمزُ الشعبة والمادّة."""
    grid = _grid(page)
    words = _words(page)
    skip = set(title_words)
    biggest = _biggest_line(_title(grid, words))
    name = " ".join(t for t in _logical(biggest) if _ARABIC.search(t) and t not in skip)
    if not name:
        raise AscPdfError("لا اسمَ معلّمٍ في عنوان الصفحة")
    lessons: list[tuple[int, int, str, str]] = []
    for cell in _cells(page, grid, words):
        codes, subject = _split_tokens(cell.tokens)
        if not codes:
            raise AscPdfError(f"خانةٌ بلا رمزِ شعبة ({name}، اليوم {cell.day + 1})")
        for code in codes:
            lessons.extend((cell.day, period, code, subject) for period in cell.periods)
    return TeacherPage(name, tuple(lessons))


def parse_class_page(page: Any) -> ClassPage:
    """صفحةُ شعبة: رمزُها من العنوان («HC.11.2» أو «11.2») إن وُجد، وما شُغل من خاناتها."""
    grid = _grid(page)
    words = _words(page)
    title = _logical(_title(grid, words))
    codes = {m.group(1) for t in title if (m := _TITLE_CLASS_CODE.match(t))}
    if len(codes) > 1:
        raise AscPdfError("رمزُ الشعبة في العنوان ملتبس")
    slots = {(cell.day, p) for cell in _cells(page, grid, words) for p in cell.periods}
    return ClassPage(next(iter(codes), ""), frozenset(slots), " ".join(title))


def open_pdf(path: str | IO[bytes]) -> Any:
    """فتحُ الـPDF بـpdfplumber — منفصلاً ليُستبدل به في الاختبار."""
    import pdfplumber

    return pdfplumber.open(path)


def parse_pdf[T](path: str | IO[bytes], parse: Callable[[Any], T]) -> tuple[list[T], list[str]]:
    """(نتائجُ الصفحات، أخطاؤها) — صفحةٌ فاسدةٌ تُذكر برقمها ولا توقف الباقي."""
    results: list[T] = []
    errors: list[str] = []
    with open_pdf(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            try:
                results.append(parse(page))
            except AscPdfError as exc:
                errors.append(f"صفحة {number}: {exc}")
    return results, errors
