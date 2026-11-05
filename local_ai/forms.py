"""استماراتُ الذكاء المحلّيّ — رفعُ وثيقةٍ، ورسالةُ المساعد."""

from __future__ import annotations

from django import forms
from django.conf import settings

from local_ai.services.assistant import MESSAGE_MAX_CHARS
from local_ai.text_extraction import SUPPORTED_EXTENSIONS, extension_of


class DocumentUploadForm(forms.Form):
    title = forms.CharField(max_length=200, label="العنوان")
    file = forms.FileField(label="الملفّ (PDF أو DOCX أو TXT أو MD)")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if extension_of(upload.name) not in SUPPORTED_EXTENSIONS:
            raise forms.ValidationError("الامتدادُ غيرُ مدعوم؛ المدعوم: PDF وDOCX وTXT وMD.")
        limit_mb = getattr(settings, "LOCAL_AI_MAX_UPLOAD_MB", 20)
        if upload.size > limit_mb * 1024 * 1024:
            raise forms.ValidationError(f"حجمُ الملفّ يتجاوز {limit_mb} ميغابايت.")
        return upload


class AssistantMessageForm(forms.Form):
    message = forms.CharField(
        max_length=MESSAGE_MAX_CHARS,
        label="سؤالك",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "اسأل عن تعميمٍ أو سياسةٍ أو خطّة…"}),
    )
