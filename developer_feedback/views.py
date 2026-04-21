"""
Views لميزة "أرسل إلى المطوّر".
يوجد 6 views:
1. OnboardingView — شاشة الإعداد القانوني (consent + quiz) قبل أول استخدام
2. DeveloperMessageCreateView — نموذج إرسال الرسالة
3. MessageSuccessView — صفحة النجاح مع رقم التذكرة
4. UserMessageHistoryView — قائمة رسائل المستخدم الحالي
5. DeveloperInboxListView — صندوق المطوّر
6. DeveloperInboxDetailView — تفاصيل رسالة + تحديث حالة
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from developer_feedback.forms import (
    DeveloperMessageEditForm,
    DeveloperMessageForm,
    OnboardingConsentForm,
    OnboardingQuizForm,
)
from developer_feedback.models import (
    DeveloperMessage,
    LegalOnboardingConsent,
    MessageEditHistory,
    MessageStatus,
    MessageStatusLog,
)
from developer_feedback.permissions import (
    DeveloperOnlyMixin,
    NotStudentMixin,
    OnboardingRequiredMixin,
)
from developer_feedback.services.audit import (
    log_inbox_view,
    log_message_edit,
    log_message_view,
    log_status_update,
)
from developer_feedback.services.notifications import (
    send_developer_edit_notification,
    send_developer_notification,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 1) OnboardingView
# ═══════════════════════════════════════════════════════════════


class OnboardingView(NotStudentMixin, View):
    """
    شاشة الإعداد القانوني. يعرض:
    - النصوص القانونية
    - OnboardingConsentForm (4 حقول)
    - OnboardingQuizForm (3 أسئلة)

    عند الإرسال: إذا نجح الاختبار → ينشئ LegalOnboardingConsent ويحوّل للنموذج الرئيسي.
    """

    template_name = "developer_feedback/onboarding.html"

    def get(self, request, *args, **kwargs):
        # إذا كان المستخدم قد أكمل بالفعل، حوّله إلى النموذج مباشرة
        existing = LegalOnboardingConsent.objects.filter(
            user=request.user,
            revoked_at__isnull=True,
            quiz_passed=True,
        ).first()
        if existing:
            return redirect("developer_feedback:message_create")

        return render(
            request,
            self.template_name,
            {
                "consent_form": OnboardingConsentForm(),
                "quiz_form": OnboardingQuizForm(),
            },
        )

    def post(self, request, *args, **kwargs):
        consent_form = OnboardingConsentForm(request.POST)
        quiz_form = OnboardingQuizForm(request.POST)

        if consent_form.is_valid() and quiz_form.is_valid():
            # كلا النموذجين صالحان → أنشئ/حدّث الموافقة
            with transaction.atomic():
                LegalOnboardingConsent.objects.update_or_create(
                    user=request.user,
                    defaults={
                        "consent_version": "1.0",
                        "quiz_passed": True,
                        "quiz_score": quiz_form.get_score(),
                        "admin_authorization_doc": consent_form.cleaned_data[
                            "admin_authorization_doc"
                        ],
                        "revoked_at": None,
                    },
                )
            messages.success(
                request,
                _("تم إكمال الإعداد القانوني بنجاح. يمكنك الآن إرسال ملاحظاتك."),
            )
            return redirect("developer_feedback:message_create")

        # فشل التحقق
        return render(
            request,
            self.template_name,
            {"consent_form": consent_form, "quiz_form": quiz_form},
            status=400,
        )


# ═══════════════════════════════════════════════════════════════
# 2) DeveloperMessageCreateView
# ═══════════════════════════════════════════════════════════════


class DeveloperMessageCreateView(OnboardingRequiredMixin, CreateView):
    """نموذج إرسال رسالة جديدة للمطوّر."""

    model = DeveloperMessage
    form_class = DeveloperMessageForm
    template_name = "developer_feedback/message_create.html"
    success_url = reverse_lazy("developer_feedback:message_success")

    def form_valid(self, form):
        instance = form.save(commit=False, user=self.request.user)
        instance.save()
        # أرسل إشعار SMTP (إذا فشل، الرسالة محفوظة في DB)
        try:
            send_developer_notification(instance)
        except Exception:  # noqa: BLE001
            # لا تُفشل الـ view — الرسالة محفوظة، الإشعار يُحاول retry
            pass

        # خزّن رقم التذكرة في session لعرضه في صفحة النجاح
        self.request.session["last_ticket_number"] = instance.ticket_number
        messages.success(
            self.request,
            _("تم استلام رسالتك. رقم التذكرة: %(t)s") % {"t": instance.ticket_number},
        )
        return redirect(self.success_url)


# ═══════════════════════════════════════════════════════════════
# 3) MessageSuccessView
# ═══════════════════════════════════════════════════════════════


class MessageSuccessView(NotStudentMixin, TemplateView):
    """صفحة تأكيد النجاح مع رقم التذكرة."""

    template_name = "developer_feedback/message_success.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ticket_number"] = self.request.session.pop("last_ticket_number", None)
        return ctx


# ═══════════════════════════════════════════════════════════════
# 4) UserMessageHistoryView
# ═══════════════════════════════════════════════════════════════


class UserMessageHistoryView(OnboardingRequiredMixin, ListView):
    """قائمة رسائل المستخدم الحالي — رسائله فقط."""

    model = DeveloperMessage
    template_name = "developer_feedback/my_messages.html"
    context_object_name = "messages_list"
    paginate_by = 20

    def get_queryset(self):
        return DeveloperMessage.objects.filter(user=self.request.user).order_by("-created_at")


# ═══════════════════════════════════════════════════════════════
# 4.b) DeveloperMessageEditView — تعديل رسالة سبق إرسالها
# ═══════════════════════════════════════════════════════════════


class DeveloperMessageEditView(OnboardingRequiredMixin, UpdateView):
    """
    يُتيح للمُرسِل تعديل رسالة سبق إرسالها. لكل تعديل:
    - تُحفظ لقطة MessageEditHistory للقيم القديمة
    - يُسجَّل EDIT_MESSAGE في AuditLog
    - يُرسَل إشعار SMTP جديد للمطوّر مع بادئة [تعديل]

    قيود الوصول: المُرسِل فقط يعدّل رسائله (get_object يقيّد بـ user=request.user).
    """

    model = DeveloperMessage
    form_class = DeveloperMessageEditForm
    template_name = "developer_feedback/message_edit.html"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        # يقيّد الوصول: المُرسِل فقط يرى/يعدّل رسائله
        return DeveloperMessage.objects.filter(user=self.request.user)

    def form_valid(self, form):
        # self.object = instance الأصلي قبل تطبيق التعديلات (UpdateView ملأه في get())
        original = DeveloperMessage.objects.get(pk=self.object.pk)
        with transaction.atomic():
            MessageEditHistory.objects.create(
                message=original,
                old_subject=original.subject,
                old_body=original.body,
                old_message_type=original.message_type,
                old_priority=original.priority,
                edited_by=self.request.user,
            )
            updated = form.save(commit=False)
            updated.save(update_fields=["subject", "body", "message_type", "priority"])
            log_message_edit(self.request, updated)

        # إشعار المطوّر (فشل SMTP لا يُفشل الحفظ)
        try:
            send_developer_edit_notification(updated)
        except Exception:  # noqa: BLE001
            pass

        messages.success(
            self.request,
            _("تم حفظ التعديل على الرسالة %(t)s وإخطار المطوّر.") % {"t": updated.ticket_number},
        )
        return redirect(reverse("developer_feedback:my_messages"))


# ═══════════════════════════════════════════════════════════════
# 5) DeveloperInboxListView
# ═══════════════════════════════════════════════════════════════


class DeveloperInboxListView(DeveloperOnlyMixin, ListView):
    """صندوق الوارد للمطوّر — يعرض كل الرسائل مع فلترة."""

    model = DeveloperMessage
    template_name = "developer_feedback/inbox_list.html"
    context_object_name = "messages_list"
    paginate_by = 25

    def get(self, request, *args, **kwargs):
        try:
            log_inbox_view(request)
        except Exception:
            logger.exception("AuditLog failed in InboxListView — non-fatal")
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = DeveloperMessage.objects.select_related("user").order_by("-created_at")
        # فلترة بسيطة عبر query params
        status_filter = self.request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        type_filter = self.request.GET.get("type")
        if type_filter:
            qs = qs.filter(message_type=type_filter)
        priority_filter = self.request.GET.get("priority")
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        search = self.request.GET.get("q")
        if search:
            qs = qs.filter(Q(subject__icontains=search) | Q(body__icontains=search))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = MessageStatus.choices
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["current_type"] = self.request.GET.get("type", "")
        ctx["current_priority"] = self.request.GET.get("priority", "")
        ctx["current_q"] = self.request.GET.get("q", "")
        return ctx


# ═══════════════════════════════════════════════════════════════
# 6) DeveloperInboxDetailView
# ═══════════════════════════════════════════════════════════════


class DeveloperInboxDetailView(DeveloperOnlyMixin, DetailView):
    """تفاصيل رسالة + تحديث الحالة."""

    model = DeveloperMessage
    template_name = "developer_feedback/inbox_detail.html"
    context_object_name = "dev_message"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        log_message_view(request, self.object)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = MessageStatus.choices
        ctx["status_logs"] = self.object.status_logs.all()
        return ctx

    def post(self, request, *args, **kwargs):
        """تحديث الحالة (POST من الفورم)."""
        self.object = self.get_object()
        new_status = request.POST.get("new_status", "").strip()
        note = request.POST.get("note", "").strip()

        valid_statuses = {choice[0] for choice in MessageStatus.choices}
        if new_status not in valid_statuses:
            messages.error(request, _("حالة غير صالحة."))
            return redirect("developer_feedback:inbox_detail", pk=self.object.pk)

        old_status = self.object.status
        if new_status != old_status:
            with transaction.atomic():
                self.object.status = new_status
                self.object.save(update_fields=["status", "updated_at"])
                MessageStatusLog.objects.create(
                    message=self.object,
                    old_status=old_status,
                    new_status=new_status,
                    changed_by=request.user,
                    note=note,
                )
                log_status_update(request, self.object)
            messages.success(request, _("تم تحديث حالة الرسالة."))

        return redirect("developer_feedback:inbox_detail", pk=self.object.pk)
