"""Unit tests for developer_feedback forms."""

from __future__ import annotations

import json
import unittest

from django.test import TestCase

from developer_feedback.forms import (
    DeveloperMessageForm,
    OnboardingConsentForm,
    OnboardingQuizForm,
)


class DeveloperMessageFormTests(TestCase):
    def _valid_data(self, **overrides):
        data = {
            "message_type": "bug",
            "priority": "normal",
            "subject": "اختبار عنوان صالح",
            "body": "وصف طويل كفاية لاختبار النموذج.",
            "consent_privacy": True,
            "context_json_raw": "",
        }
        data.update(overrides)
        return data

    def test_valid_form(self):
        form = DeveloperMessageForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_subject_too_short(self):
        form = DeveloperMessageForm(data=self._valid_data(subject="aa"))
        self.assertFalse(form.is_valid())
        self.assertIn("subject", form.errors)

    def test_body_too_short(self):
        form = DeveloperMessageForm(data=self._valid_data(body="short"))
        self.assertFalse(form.is_valid())
        self.assertIn("body", form.errors)

    def test_consent_required(self):
        form = DeveloperMessageForm(data=self._valid_data(consent_privacy=False))
        self.assertFalse(form.is_valid())
        self.assertIn("consent_privacy", form.errors)

    def test_context_json_whitelist_removes_unknown_keys(self):
        payload = json.dumps(
            {
                "url_path": "/test",
                "evil_token": "super-secret-abc",
                "cookies": "session=xxx",
                "role": "teacher",
            }
        )
        form = DeveloperMessageForm(data=self._valid_data(context_json_raw=payload))
        self.assertTrue(form.is_valid(), form.errors)
        ctx = form.cleaned_data["context_json_raw"]
        self.assertIn("url_path", ctx)
        self.assertIn("role", ctx)
        self.assertNotIn("evil_token", ctx)
        self.assertNotIn("cookies", ctx)

    def test_context_json_strips_query_string(self):
        payload = json.dumps({"url_path": "/page?token=abc&sid=xyz"})
        form = DeveloperMessageForm(data=self._valid_data(context_json_raw=payload))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["context_json_raw"]["url_path"], "/page")

    def test_context_json_blocks_token_values(self):
        payload = json.dumps({"url_path": "/page", "role": "teacher-with-jwt-token"})
        form = DeveloperMessageForm(data=self._valid_data(context_json_raw=payload))
        self.assertTrue(form.is_valid())
        # role تحوي "jwt" و "token" → يُحذف
        self.assertNotIn("role", form.cleaned_data["context_json_raw"])


class OnboardingConsentFormTests(TestCase):
    def _valid_data(self, **overrides):
        data = {
            "accept_privacy_policy": True,
            "accept_data_handling": True,
            "no_student_data_pledge": True,
            "admin_authorization_doc": "AUTH-2026-001",
        }
        data.update(overrides)
        return data

    def test_all_agreements_required(self):
        form = OnboardingConsentForm(data=self._valid_data(no_student_data_pledge=False))
        self.assertFalse(form.is_valid())
        self.assertIn("no_student_data_pledge", form.errors)

    def test_admin_doc_required(self):
        form = OnboardingConsentForm(data=self._valid_data(admin_authorization_doc=""))
        self.assertFalse(form.is_valid())

    def test_valid_form(self):
        form = OnboardingConsentForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)


class OnboardingQuizFormTests(TestCase):
    def test_all_correct_passes(self):
        form = OnboardingQuizForm(data={"q1": "no", "q2": "c", "q3": "yes"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_score(), 3)
        self.assertTrue(form.is_passed())

    def test_one_wrong_fails(self):
        form = OnboardingQuizForm(data={"q1": "yes", "q2": "c", "q3": "yes"})
        self.assertFalse(form.is_valid())

    def test_all_wrong_fails(self):
        form = OnboardingQuizForm(data={"q1": "yes", "q2": "a", "q3": "no"})
        self.assertFalse(form.is_valid())


class ContextOrderTests(TestCase):
    """[PRIVACY] الاقتطاع يسبق الفحص — وإلّا سقط المسار بدل أن يُنظَّف.

    مرشِّحان يعملان على `url_path`: أحدهما يقتطع سلسلة الاستعلام، والآخر
    يُسقط المفتاح إن حوت قيمتُه «token» أو «session» أو أخواتها. وكان
    الثاني يسبق الأوّل، فيرى الكلمة داخل `?token=abc` ويُلقي المسار كلّه
    قبل أن يصل إلى الاقتطاع — أي أن الاقتطاع لم يكن يعمل قطّ.

    وأثره أوسع من الرمز المسرَّب: خمسة مسارات في `exam_control` تحمل كلمة
    «session» في نصّها، فكانت الشكوى تصل بلا موضعٍ يدلّ على مصدرها.
    """

    def _data(self, payload):
        return {
            "message_type": "bug",
            "priority": "normal",
            "subject": "اختبار عنوان صالح",
            "body": "وصف طويل كفاية لاختبار النموذج.",
            "consent_privacy": True,
            "context_json_raw": json.dumps(payload),
        }

    def test_the_query_string_is_cut_not_the_whole_path(self):
        form = DeveloperMessageForm(data=self._data({"url_path": "/page?token=abc&sid=xyz"}))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["context_json_raw"]["url_path"], "/page")

    @unittest.expectedFailure
    def test_a_real_path_containing_the_word_survives(self):
        """مقصودٌ ولم يتحقّق بعد — سؤالُ سياسةٍ لا عطبُ شيفرة.

        الاقتطاع يُنقذ `?token=abc`، ولا يُنقذ الكلمة حين تكون في المسار
        نفسه. وخمسة مسارات في `exam_control` تحملها: ‏/exam_control/session/<pk>/‎.

        وإعفاء `url_path` من فحص الكلمات بعد الاقتطاع يبدو بلا ثمن — فالسرّ
        في المسار قيمةٌ معتِمة لا الكلمةُ الإنجليزية نفسها، حتى في مسار
        استعادة كلمة المرور في جانغو. لكنه تخفيفُ ضابطٍ يمسّ بياناتٍ
        شخصية، فلا يُقرَّر من طرفٍ واحد.
        """
        path = "/exam_control/session/7/"
        form = DeveloperMessageForm(data=self._data({"url_path": path}))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["context_json_raw"]["url_path"], path)

    def test_the_secret_itself_never_reaches_the_cleaned_data(self):
        """الاقتطاع أوّلاً لا يعني تسرّباً — القيمة تُقطع قبل أن تُخزَّن."""
        form = DeveloperMessageForm(data=self._data({"url_path": "/p?token=SECRETVALUE"}))
        form.is_valid()

        self.assertNotIn("SECRETVALUE", json.dumps(form.cleaned_data["context_json_raw"]))

    def test_a_path_that_embeds_the_word_outside_a_query_is_still_dropped(self):
        """الفحص باقٍ بعد الاقتطاع — لم يُستبدل بالترتيب بل تأخّر عنه."""
        form = DeveloperMessageForm(data=self._data({"view_name": "auth:password_reset"}))
        form.is_valid()

        self.assertNotIn("view_name", form.cleaned_data["context_json_raw"])
