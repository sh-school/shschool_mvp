# خارطة طريق لتطبيق توصيات قانون حماية البيانات الشخصية (PDPPL) في منصة SHSchool

لضمان الامتثال الفوري والفعال لقانون حماية البيانات الشخصية (PDPPL) في قطر [1]، إليك خارطة طريق تقنية وعملية تركز على الخطوات الأولى الأكثر أهمية، مع أمثلة برمجية حيثما أمكن.

## 1. الخطوات العاجلة للالتزام التقني

### 1.1. تطبيق التشفير الشامل للبيانات الحساسة

**المشكلة:** البيانات الحساسة في نماذج مثل `ClinicVisit` و`HealthRecord` قد لا تكون مشفرة بشكل كامل حالياً، مما يشكل مخالفة للمادة 8 من قانون PDPPL التي تتطلب اتخاذ احتياطات فنية وإدارية مناسبة لحماية البيانات، بما في ذلك تشفير البيانات ذات الطبيعة الخاصة (مثل الصحية) [1].

**الخطوات:**
1.  **التأكد من توفر `FERNET_KEY` في بيئة الإنتاج:**
    يجب التأكد من أن `FERNET_KEY` يتم توفيره كمتغير بيئة قوي وفريد في بيئة الإنتاج، وعدم الاعتماد على القيمة الافتراضية الفارغة في `base.py`.
    ```python
    # shschool/settings/production.py
    from decouple import config
    # ...
    FERNET_KEY = config("FERNET_KEY") # يجب أن يكون موجوداً ولا يوجد قيمة افتراضية
    if not FERNET_KEY:
        raise ImproperlyConfigured("FERNET_KEY must be set in production environment for data encryption")
    ```
2.  **تعديل النماذج لتطبيق `encrypt_field`:**
    يجب تطبيق `encrypt_field` على جميع الحقول التي تحتوي على بيانات حساسة في النماذج المعنية، مثل `ClinicVisit` و`HealthRecord`، وأي نماذج أخرى قد تحتوي على معلومات شخصية خاصة.
    ```python
    # core/models.py (مثال لتطبيق encrypt_field)
    from django.db import models
    from .fields import EncryptedCharField, EncryptedTextField # تأكد من استيراد الحقول المشفرة
    # ...

    class HealthRecord(models.Model):
        student = models.ForeignKey("core.Student", on_delete=models.CASCADE, related_name="health_records")
        record_date = models.DateField()
        # يجب تشفير هذه الحقول
        blood_type = EncryptedCharField(max_length=5, blank=True, null=True)
        allergies = EncryptedTextField(blank=True, null=True)
        medical_conditions = EncryptedTextField(blank=True, null=True)
        medications = EncryptedTextField(blank=True, null=True)
        notes = EncryptedTextField(blank=True, null=True)
        # ...

    class ClinicVisit(models.Model):
        student = models.ForeignKey("core.Student", on_delete=models.CASCADE, related_name="clinic_visits")
        visit_date = models.DateTimeField(auto_now_add=True)
        # يجب تشفير هذه الحقول
        reason = EncryptedTextField()
        diagnosis = EncryptedTextField(blank=True, null=True)
        treatment = EncryptedTextField(blank=True, null=True)
        notes = EncryptedTextField(blank=True, null=True)
        # ...
    ```
    **ملاحظة:** تأكد من أن `EncryptedCharField` و`EncryptedTextField` (أو ما يعادلهما في الكود المصدري) يستخدمان `FERNET_KEY` بشكل صحيح للتشفير وفك التشفير.

### 1.2. تفعيل وإدارة الموافقات (Consent Management)

**المشكلة:** نموذج `ConsentRecord` موجود ولكنه غير مستخدم، مما يعني عدم وجود آلية صريحة لجمع موافقات أولياء الأمور على معالجة بيانات أطفالهم، وهو أمر ضروري بموجب المادتين 16 و 17 من قانون PDPPL [1].

**الخطوات:**
1.  **تعديل نموذج `ConsentRecord` (إذا لزم الأمر):**
    تأكد من أن النموذج يلتقط المعلومات الضرورية مثل نوع الموافقة، من وافق، تاريخ الموافقة، والبيانات التي تغطيها الموافقة.
    ```python
    # core/models.py (مثال لنموذج ConsentRecord)
    class ConsentRecord(models.Model):
        parent_membership = models.ForeignKey("core.Membership", on_delete=models.CASCADE, related_name="consents")
        student = models.ForeignKey("core.Student", on_delete=models.CASCADE, related_name="consents")
        consent_type = models.CharField(max_length=100, help_text="مثال: معالجة البيانات الصحية، مشاركة الصور، إلخ.")
        is_granted = models.BooleanField(default=False)
        granted_date = models.DateTimeField(auto_now_add=True)
        revoked_date = models.DateTimeField(null=True, blank=True)
        # ... حقول إضافية لتفاصيل الموافقة أو الوثيقة الموقعة

        class Meta:
            unique_together = ("parent_membership", "student", "consent_type")
    ```
2.  **إنشاء واجهات لجمع الموافقات:**
    *   تطوير واجهة مستخدم (View) في بوابة أولياء الأمور تسمح لهم بمراجعة أنواع الموافقات المطلوبة وتقديمها إلكترونياً.
    *   ربط هذه الواجهة بنموذج `ConsentRecord` لتسجيل الموافقات أو سحبها.
    ```python
    # parents/views.py (مثال لدالة view لجمع الموافقات)
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib.auth.decorators import login_required
    from core.models import Student, Membership, ConsentRecord
    from django.contrib import messages

    @login_required
    def manage_consents(request, student_id):
        student = get_object_or_404(Student, id=student_id)
        parent_membership = get_object_or_404(Membership, user=request.user, role__name="Parent")

        # مثال على أنواع الموافقات المطلوبة
        required_consents = [
            {"type": "Health Data Processing", "description": "الموافقة على معالجة البيانات الصحية للطالب.", "model_field": "health_data_consent"},
            {"type": "Behavioral Data Processing", "description": "الموافقة على معالجة البيانات السلوكية للطالب.", "model_field": "behavioral_data_consent"},
            {"type": "Photo Sharing", "description": "الموافقة على مشاركة صور الطالب في أنشطة المدرسة.", "model_field": "photo_sharing_consent"},
        ]

        if request.method == 'POST':
            for consent_info in required_consents:
                consent_type = consent_info["type"]
                is_granted = request.POST.get(consent_info["model_field"]) == 'on'

                consent, created = ConsentRecord.objects.update_or_create(
                    parent_membership=parent_membership,
                    student=student,
                    consent_type=consent_type,
                    defaults={
                        'is_granted': is_granted,
                        'revoked_date': timezone.now() if not is_granted else None
                    }
                )
            messages.success(request, "تم تحديث الموافقات بنجاح.")
            return redirect("manage_consents", student_id=student.id)

        # جلب حالة الموافقات الحالية
        current_consents = {c.consent_type: c.is_granted for c in ConsentRecord.objects.filter(parent_membership=parent_membership, student=student)}

        context = {
            "student": student,
            "required_consents": required_consents,
            "current_consents": current_consents,
        }
        return render(request, "parents/manage_consents.html", context)
    ```
3.  **فرض التحقق من الموافقة:**
    قبل معالجة أي بيانات حساسة، يجب التحقق من وجود الموافقة المطلوبة. يمكن تحقيق ذلك في الـ Views أو الـ Services أو حتى باستخدام Decorator مخصص.
    ```python
    # core/decorators.py (مثال لـ decorator للتحقق من الموافقة)
    from functools import wraps
    from django.http import HttpResponseForbidden
    from core.models import ConsentRecord

    def consent_required(consent_type):
        def decorator(view_func):
            @wraps(view_func)
            def _wrapped_view(request, *args, **kwargs):
                student_id = kwargs.get("student_id") # افترض أن student_id موجود في kwargs
                if not student_id:
                    return HttpResponseForbidden("Student ID is required for consent check.")

                try:
                    student = Student.objects.get(id=student_id)
                    parent_membership = Membership.objects.get(user=request.user, role__name="Parent")
                    consent = ConsentRecord.objects.get(parent_membership=parent_membership, student=student, consent_type=consent_type, is_granted=True)
                except (Student.DoesNotExist, Membership.DoesNotExist, ConsentRecord.DoesNotExist):
                    return HttpResponseForbidden(f"الموافقة على '{consent_type}' مطلوبة.")
                return view_func(request, *args, **kwargs)
            return _wrapped_view
        return decorator

    # في views.py (مثال للاستخدام)
    @consent_required("Health Data Processing")
    def view_health_records(request, student_id):
        # ... منطق عرض السجلات الصحية
        pass
    ```

## 2. الخطوات الإدارية والتنظيمية

### 2.1. إجراء تقييم أثر حماية البيانات (DPIA)

**المشكلة:** عدم وجود تقييم رسمي لأثر حماية البيانات، وهو مطلوب قانونياً للمشاريع التي تعالج بيانات حساسة أو على نطاق واسع [1].

**الخطوات:**
1.  **تعيين مسؤول حماية البيانات (DPO):** يجب تعيين شخص أو فريق مسؤول عن حماية البيانات داخل المنظمة.
2.  **إجراء تقييم شامل:** تقييم جميع العمليات التي تتضمن معالجة البيانات الشخصية في المنصة، وتحديد المخاطر المحتملة، ووضع خطط للتخفيف من هذه المخاطر.
3.  **توثيق الـ DPIA:** إعداد تقرير رسمي يوثق عملية التقييم والنتائج والتوصيات.

### 2.2. تطوير آلية الإبلاغ عن خروقات البيانات (Breach Notification Workflow)

**المشكلة:** عدم وجود آلية واضحة للإبلاغ عن خروقات البيانات خلال 72 ساعة، كما هو منصوص عليه في القانون [1].

**الخطوات:**
1.  **وضع خطة استجابة للحوادث:** تحديد الإجراءات التي يجب اتخاذها في حالة حدوث خرق للبيانات، بما في ذلك من يجب إبلاغه ومتى.
2.  **تطوير قنوات الإبلاغ:** إنشاء قنوات داخلية وخارجية للإبلاغ عن الخروقات (مثل نموذج إلكتروني، بريد إلكتروني مخصص).
3.  **التدريب:** تدريب الموظفين على كيفية التعرف على خروقات البيانات والإبلاغ عنها.

### 2.3. توثيق سياسات الخصوصية وشروط الاستخدام

**المشكلة:** عدم وجود سياسات خصوصية وشروط استخدام واضحة ومتاحة للمستخدمين.

**الخطوات:**
1.  **صياغة سياسة خصوصية شاملة:** توضح بوضوح أنواع البيانات التي يتم جمعها، الغرض من جمعها، كيفية معالجتها وتخزينها، من يمكنه الوصول إليها، ومدة الاحتفاظ بها، وحقوق المستخدمين.
2.  **صياغة شروط الاستخدام:** تحدد حقوق ومسؤوليات المستخدمين والمدرسة عند استخدام المنصة.
3.  **إتاحة السياسات:** نشر هذه السياسات في مكان واضح وسهل الوصول إليه داخل المنصة (مثل تذييل الصفحة الرئيسية).

## 3. الخلاصة

تطبيق هذه الخطوات الأولى سيضع منصة SHSchool على المسار الصحيح للامتثال الكامل لقانون حماية البيانات الشخصية (PDPPL). من الضروري البدء بتشفير البيانات الحساسة وتفعيل نظام إدارة الموافقات كأولوية قصوى، ثم الانتقال إلى الجوانب الإدارية والتنظيمية مثل DPIA، وآلية الإبلاغ عن الخروقات، وتوثيق السياسات. هذا النهج يضمن حماية بيانات المستخدمين ويعزز ثقتهم في المنصة.

## المراجع
[1] قانون رقم (13) لسنة 2016 بشأن حماية خصوصية البيانات الشخصية (PDPPL).
[2] `core/models.py` (لنماذج البيانات)
[3] `shschool/settings/production.py` (لإعدادات الإنتاج)
[4] `parents/views.py` (مثال مقترح لـ View إدارة الموافقات)
