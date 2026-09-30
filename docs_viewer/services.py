"""عارضُ md المركزيّ — قراءةُ ملفّات التوثيق من القرص حيّاً وتصييرُها (W-20260930-002).

القاعدةُ الوحيدة هنا: **لا خروجَ عن `DOCS_ROOT`**. المسارُ مُدخَلٌ من المستخدم (جزءٌ
من الرابط)، فـ`safe_resolve` تحلّ الرمزيّاتِ (`resolve()`) ثمّ تتحقّق أنّ الناتج
داخل الجذر بـ`is_relative_to` — لا مقارنةَ نصّيّةً تخدعها `..` أو رابطٌ رمزيّ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.http import Http404

#: جذرُ المشروع — نفسُ BASE_DIR، فيشمل `.claude/` (طلبُ المالك صراحةً).
DOCS_ROOT = Path(settings.BASE_DIR).resolve()

#: مجلّداتٌ تُستبعد من الشجرة: توليدٌ أو تبعيّاتٌ أو تاريخُ غيت — لا توثيقَ فيها.
EXCLUDED_DIR_NAMES = {
    ".git",
    "node_modules",
    "staticfiles",
    "media",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "dist",
    "build",
    "logs",
    ".idea",
    ".vscode",
}


@dataclass
class DocNode:
    """مجلّدٌ أو ملفٌّ في شجرة العرض."""

    name: str
    rel_path: str
    is_dir: bool
    children: list[DocNode] = field(default_factory=list)


def safe_resolve(rel_path: str) -> Path:
    """يحلّ مساراً نسبيّاً داخل `DOCS_ROOT` وحدَه، أو يرفع Http404.

    `resolve()` يبتلع `..` والروابطَ الرمزيّة، و`is_relative_to` يتحقّق من الناتج
    لا من النصّ الخام — فـ`../../etc/passwd` أو رابطٌ رمزيٌّ يخرج بها يُرفض هنا.
    """
    candidate = (DOCS_ROOT / rel_path).resolve()
    if not candidate.is_relative_to(DOCS_ROOT):
        raise Http404("مسارٌ خارج جذر المشروع")
    if candidate.suffix.lower() != ".md":
        raise Http404("ليس ملفَّ md")
    if not candidate.is_file():
        raise Http404("الملفُّ غير موجود")
    return candidate


def build_tree() -> DocNode:
    """يبني شجرةَ ملفّات `.md` تحت `DOCS_ROOT` — للفهرس `/docs/`."""
    root = DocNode(name="/", rel_path="", is_dir=True)
    nodes_by_rel: dict[str, DocNode] = {"": root}

    for dirpath, dirnames, filenames in os.walk(DOCS_ROOT):
        dirnames[:] = sorted(
            d for d in dirnames if d not in EXCLUDED_DIR_NAMES and not d.startswith(".")
        )
        md_files = sorted(f for f in filenames if f.lower().endswith(".md"))
        if not md_files:
            continue

        rel_dir = os.path.relpath(dirpath, DOCS_ROOT)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")

        parent = _ensure_dir_node(nodes_by_rel, rel_dir)
        for filename in md_files:
            file_rel = f"{rel_dir}/{filename}" if rel_dir else filename
            parent.children.append(DocNode(name=filename, rel_path=file_rel, is_dir=False))

    _prune_empty(root)
    return root


def _ensure_dir_node(nodes_by_rel: dict[str, DocNode], rel_dir: str) -> DocNode:
    if rel_dir in nodes_by_rel:
        return nodes_by_rel[rel_dir]
    parent_rel, _, name = rel_dir.rpartition("/")
    parent = _ensure_dir_node(nodes_by_rel, parent_rel)
    node = DocNode(name=name or rel_dir, rel_path=rel_dir, is_dir=True)
    parent.children.append(node)
    nodes_by_rel[rel_dir] = node
    return node


def _prune_empty(node: DocNode) -> None:
    for child in list(node.children):
        if child.is_dir:
            _prune_empty(child)
    node.children.sort(key=lambda n: (not n.is_dir, n.name.lower()))
