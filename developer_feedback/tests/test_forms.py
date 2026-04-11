"""Unit tests for developer_feedback forms."""

from __future__ import annotations

import json

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
        payload = json.dumps(
            {"url_path": "/page", "role": "teacher-with-jwt-token"}
        )
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
        form = OnboardingConsentForm(
            data=self._valid_data(no_student_data_pledge=False)
        )
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
