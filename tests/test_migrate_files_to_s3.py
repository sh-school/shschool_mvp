"""[البند 11] `migrate_files_to_s3` — ينسخ من StoredFile إلى S3، بلا حذفٍ وبلا شبكة.

الاختباراتُ هنا لا تلمس R2 الحقيقيّة أصلاً — توسيعٌ ثمّ تقليص، ووثوقيّةُ CI
تحتاج تخزيناً وهمياً لا خدمةً خارجيّة حيّة. `storages["default"]` يُستبدَل
بمزيّفٍ يحاكي واجهة `Storage` (`exists`/`save`) دون أيّ اتصال.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from core.db_storage import DatabaseStorage
from core.models import StoredFile

pytestmark = pytest.mark.django_db


class _FakeS3Storage:
    """يحاكي واجهةَ `Storage` بما يكفي لهذا الأمر — قاموسٌ في الذاكرة لا شبكة."""

    def __init__(self, preexisting=()):
        self.objects = dict.fromkeys(preexisting, b"")
        self.saved = []

    def exists(self, name):
        return name in self.objects

    def save(self, name, content):
        self.objects[name] = content.read()
        self.saved.append(name)
        return name


def _make(name, content=b"x"):
    StoredFile.objects.create(
        name=name, content=content, size=len(content), content_type="text/plain"
    )


def _run(*args):
    out, err = StringIO(), StringIO()
    call_command("migrate_files_to_s3", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


@patch("core.management.commands.migrate_files_to_s3.storages")
def test_a_dry_run_reports_without_writing_anything(mock_storages):
    _make("a.pdf")
    _make("b.png")
    fake = _FakeS3Storage()
    mock_storages.__getitem__.return_value = fake

    out, _err = _run()

    assert fake.saved == []
    assert "سيُنسَخ 2" in out
    assert "تقريرٌ فقط" in out


@patch("core.management.commands.migrate_files_to_s3.storages")
def test_apply_copies_missing_files_with_their_original_content(mock_storages):
    _make("new.pdf", content=b"hello-pdf")
    fake = _FakeS3Storage()
    mock_storages.__getitem__.return_value = fake

    out, _err = _run("--apply")

    assert fake.saved == ["new.pdf"]
    assert fake.objects["new.pdf"] == b"hello-pdf"
    assert "نُسخ 1" in out


@patch("core.management.commands.migrate_files_to_s3.storages")
def test_files_already_on_s3_are_skipped_not_overwritten(mock_storages):
    _make("already-there.png")
    fake = _FakeS3Storage(preexisting=["already-there.png"])
    mock_storages.__getitem__.return_value = fake

    out, _err = _run("--apply")

    assert fake.saved == []
    assert "تُجووِز (موجودٌ سلفاً) 1" in out


@patch("core.management.commands.migrate_files_to_s3.storages")
def test_a_failed_copy_is_counted_and_does_not_stop_the_rest(mock_storages):
    _make("bad.pdf")
    _make("good.pdf")
    fake = _FakeS3Storage()

    def _save(name, content):
        if name == "bad.pdf":
            raise OSError("network blip")
        return _FakeS3Storage.save(fake, name, content)

    fake.save = _save
    mock_storages.__getitem__.return_value = fake

    out, err = _run("--apply")

    assert fake.saved == ["good.pdf"]
    assert "نُسخ 1" in out
    assert "فشل 1" in out
    assert "bad.pdf" in err


def test_refuses_to_run_while_the_default_storage_is_still_the_database():
    """حارسٌ ضدّ نسخ StoredFile إلى نفسه — الأمرُ بلا أثرٍ إن لم يُفعَّل S3 بعد."""
    _make("whatever.pdf")

    with patch(
        "core.management.commands.migrate_files_to_s3.storages",
        {"default": DatabaseStorage()},
    ):
        _out, err = _run("--apply")

    assert "DatabaseStorage" in err
