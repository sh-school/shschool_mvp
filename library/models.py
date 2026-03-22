"""
library/models.py
نماذج المكتبة المدرسية — نُقلت من core/models.py
db_table مضبوط صراحةً لإبقاء نفس الجداول في قاعدة البيانات
"""

import uuid

from django.db import models

from .querysets import BookQuerySet, BorrowingQuerySet


def _uuid():
    return uuid.uuid4()


class LibraryBook(models.Model):
    """كتاب في المكتبة — يدعم المطبوع والرقمي والدوريات"""

    BOOK_TYPES = [
        ("PRINT", "مطبوع"),
        ("DIGITAL", "رقمي / PDF"),
        ("PERIODICAL", "دورية / مجلة"),
    ]
    objects = BookQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        "core.School", on_delete=models.CASCADE, related_name="library_books"
    )
    title = models.CharField(max_length=500, verbose_name="عنوان الكتاب")
    author = models.CharField(max_length=200, verbose_name="المؤلف")
    isbn = models.CharField(max_length=20, blank=True, verbose_name="ISBN")
    category = models.CharField(max_length=100, verbose_name="التصنيف (ديوي العشري)")
    book_type = models.CharField(max_length=20, choices=BOOK_TYPES, default="PRINT")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية المتوفرة")
    available_qty = models.PositiveIntegerField(default=1, verbose_name="الكمية المتاحة للإعارة")
    digital_file = models.FileField(
        upload_to="library/digital/", null=True, blank=True, verbose_name="الملف الرقمي"
    )
    location = models.CharField(max_length=100, blank=True, verbose_name="موقع الكتاب (الرف)")

    class Meta:
        verbose_name = "كتاب مكتبة"
        verbose_name_plural = "كتب المكتبة"
        db_table = "core_librarybook"  # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"{self.title} - {self.author}"


class BookBorrowing(models.Model):
    """عملية إعارة كتاب"""

    STATUS = [
        ("BORROWED", "قيد الإعارة"),
        ("RETURNED", "تم الإرجاع"),
        ("OVERDUE", "متأخر"),
        ("LOST", "مفقود"),
    ]
    objects = BorrowingQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    book = models.ForeignKey(LibraryBook, on_delete=models.CASCADE, related_name="borrowings")
    user = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.CASCADE,
        related_name="borrowed_books",
        verbose_name="المستعير",
    )
    borrow_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(verbose_name="تاريخ الإرجاع المتوقع")
    return_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الإرجاع الفعلي")
    status = models.CharField(max_length=20, choices=STATUS, default="BORROWED")
    librarian = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="processed_borrowings",
        verbose_name="أمين المكتبة",
    )

    class Meta:
        verbose_name = "عملية إعارة"
        verbose_name_plural = "عمليات الإعارة"
        ordering = ["-borrow_date", "-id"]
        db_table = "core_bookborrowing"  # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"{self.user.full_name} - {self.book.title}"


class LibraryActivity(models.Model):
    """نشاط مكتبة — قراءة جماعية، معارض، إلخ"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    title = models.CharField(max_length=200, verbose_name="اسم النشاط")
    description = models.TextField(verbose_name="وصف النشاط")
    date = models.DateField()
    participants = models.ManyToManyField(
        "core.CustomUser", related_name="library_activities", verbose_name="المشاركون"
    )
    outcome = models.TextField(blank=True, verbose_name="مخرجات النشاط")

    class Meta:
        verbose_name = "نشاط مكتبة"
        verbose_name_plural = "أنشطة المكتبة"
        db_table = "core_libraryactivity"  # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"{self.title} - {self.date}"
