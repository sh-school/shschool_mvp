# Change Approval Protocol / بروتوكول اعتماد التغييرات

> **Catalyst / المحفز:** Railway Production Incident - changes were pushed to production without structured approval, risk assessment, or documented rollback plan. This protocol ensures every production change goes through a formal approval pipeline.

---

## 1. Purpose / الهدف

No production change -- whether code, configuration, infrastructure, or data -- may be executed without completing this 8-step approval process. This applies to ALL environments classified as production.

لا يجوز تنفيذ أي تغيير على الإنتاج -- سواء كان كود أو إعداد أو بنية تحتية أو بيانات -- بدون إكمال عملية الاعتماد المكونة من 8 خطوات. ينطبق على جميع بيئات الإنتاج.

---

## 2. The 8-Step Change Approval Pipeline / خط اعتماد التغييرات من 8 خطوات

---

### Step 1: What Is the Change? / ما هو التغيير؟

Clearly define the change in specific, measurable terms.

صف التغيير بشكل محدد وقابل للقياس.

```
CHANGE REQUEST FORM / نموذج طلب التغيير
=========================================

Request ID: CR-____-____
Date Submitted / تاريخ التقديم: ___________
Requested By / مقدم الطلب: ___________
Department / القسم: ___________

Change Title / عنوان التغيير:
_______________________________________________

Change Description / وصف التغيير:
_______________________________________________
_______________________________________________

Change Type / نوع التغيير:
[ ] Code deployment / نشر كود
[ ] Configuration change / تغيير إعدادات
[ ] Infrastructure change / تغيير بنية تحتية
[ ] Database change / تغيير قاعدة بيانات
[ ] Third-party integration / تكامل طرف ثالث
[ ] Security patch / تحديث أمني
[ ] Other / أخرى: _______________

Affected Systems / الأنظمة المتأثرة:
_______________________________________________

Affected Users / المستخدمون المتأثرون:
[ ] All users / جميع المستخدمين
[ ] Specific group / مجموعة محددة: _______________
[ ] Internal only / داخلي فقط
```

---

### Step 2: Why Is It Needed? / لماذا هذا التغيير مطلوب؟

Provide clear business and technical justification. Every change must have a documented reason.

قدّم مبررا واضحا تقنيا وعمليا. كل تغيير يجب أن يكون له سبب موثق.

| Question / السؤال | Answer / الإجابة |
|-------------------|-----------------|
| What problem does this solve? / ما المشكلة التي يحلها؟ | |
| What happens if we do NOT make this change? / ماذا يحدث إذا لم نغيّر؟ | |
| Is there a deadline/urgency? / هل يوجد موعد نهائي؟ | |
| Who requested this? / من طلب هذا؟ | |
| What is the expected business impact? / ما الأثر المتوقع على العمل؟ | |
| Is this change reversible? / هل التغيير قابل للتراجع؟ | |

---

### Step 3: What Are the Risks? / ما هي المخاطر؟

Conduct a formal risk assessment before proceeding.

أجرِ تقييم مخاطر رسمي قبل المتابعة.

#### Risk Matrix / مصفوفة المخاطر

| Risk / المخاطرة | Probability (1-5) | Impact (1-5) | Score | Mitigation / التخفيف |
|----------------|-------------------|-------------|-------|---------------------|
| Service downtime / توقف الخدمة | | | | |
| Data loss / فقدان بيانات | | | | |
| Security vulnerability / ثغرة أمنية | | | | |
| Performance degradation / تدهور الأداء | | | | |
| User experience impact / تأثير على تجربة المستخدم | | | | |
| Integration breakage / كسر التكاملات | | | | |
| _Add rows as needed_ | | | | |

**Risk Score Guide:**
- **1-8:** Low risk - proceed with standard approval / مخاطرة منخفضة
- **9-16:** Medium risk - requires additional review / مخاطرة متوسطة - تحتاج مراجعة إضافية
- **17-25:** High risk - requires CTO approval / مخاطرة عالية - تحتاج موافقة المدير التقني

#### Rollback Plan / خطة التراجع (MANDATORY / إلزامي)

| Item / البند | Details / التفاصيل |
|-------------|-------------------|
| Rollback method / طريقة التراجع | |
| Rollback owner / المسؤول | |
| Estimated rollback time / الوقت المتوقع | |
| Rollback tested? / تم اختبار التراجع؟ | [ ] Yes / [ ] No |
| Data recovery plan / خطة استرجاع البيانات | |

---

### Step 4: Lessons Learned from Similar Changes / الدروس المستفادة من تغييرات مشابهة

**MANDATORY:** Before approval, the requester MUST search the Knowledge Base for previous similar changes and document findings.

**إلزامي:** قبل الموافقة، يجب على مقدم الطلب البحث في قاعدة المعرفة عن تغييرات مشابهة سابقة.

| Question / السؤال | Answer / الإجابة |
|-------------------|-----------------|
| Have we made a similar change before? / هل أجرينا تغييرا مشابها من قبل؟ | |
| What happened last time? / ماذا حدث في المرة السابقة؟ | |
| What went wrong? / ما الذي سار خطأ؟ | |
| What should we do differently? / ما الذي يجب فعله بشكل مختلف؟ | |
| Related incident IDs / معرّفات الحوادث المرتبطة | |
| KB articles referenced / مقالات قاعدة المعرفة المرجعية | |

**Railway Incident Lesson / درس حادثة Railway:**
> The Railway production incident proved that deploying without proper review, risk assessment, and rollback planning leads to extended downtime and costly recovery. Every change request must demonstrate awareness of this lesson.

> حادثة Railway أثبتت أن النشر بدون مراجعة ملائمة وتقييم مخاطر وخطة تراجع يؤدي إلى توقف مطوّل واسترداد مكلف.

---

### Step 5: Present to Stakeholder and Wait for Approval / العرض على صاحب المصلحة وانتظار الموافقة

The completed change request (Steps 1-4) must be presented to the appropriate approver(s).

يجب تقديم طلب التغيير المكتمل (الخطوات 1-4) إلى المعتمد المناسب.

#### Approval Authority Matrix / مصفوفة صلاحيات الاعتماد

| Change Type / نوع التغيير | Risk Level | Approver / المعتمد |
|--------------------------|-----------|-------------------|
| Standard code deploy / نشر كود عادي | Low | Team Lead |
| Configuration change / تغيير إعدادات | Low-Medium | Team Lead + DevOps Lead |
| Database migration / هجرة قاعدة بيانات | Medium | Team Lead + DevOps Lead + QA Lead |
| Infrastructure change / تغيير بنية تحتية | Medium-High | DevOps Lead + CTO |
| Security-related change / تغيير أمني | High | Security Lead + CTO |
| Emergency hotfix / إصلاح طارئ | Any | CTO (with post-hoc full review) |

#### Approval Status / حالة الاعتماد

```
Presented to / قُدّم إلى: ___________________________
Presentation Date / تاريخ العرض: ___________________________
Decision / القرار: [ ] APPROVED  [ ] REJECTED  [ ] DEFERRED
Decision Date / تاريخ القرار: ___________________________
Approver Signature / توقيع المعتمد: ___________________________
Conditions (if any) / شروط (إن وجدت): ___________________________
```

**CRITICAL RULE / قاعدة حرجة:**
> DO NOT execute any change before receiving explicit written approval. Verbal approval is NOT sufficient.
> لا تنفذ أي تغيير قبل الحصول على موافقة كتابية صريحة. الموافقة الشفهية غير كافية.

---

### Step 6: Execute Only After Approval / التنفيذ فقط بعد الموافقة

Once approval is received, execute the change following the [Deployment Sign-Off Protocol](deployment-signoff.md).

بعد الحصول على الموافقة، نفّذ التغيير وفقا لبروتوكول اعتماد النشر.

#### Execution Checklist / قائمة التنفيذ

- [ ] Written approval received and filed / الموافقة الكتابية مستلمة ومحفوظة
- [ ] Deployment sign-off checklist completed / قائمة اعتماد النشر مكتملة
- [ ] All 3 departments signed off (for production deploys) / الأقسام الثلاثة اعتمدت
- [ ] Rollback plan ready and tested / خطة التراجع جاهزة ومختبرة
- [ ] Monitoring in place / المراقبة مُفعلة
- [ ] On-call engineer assigned / مهندس الطوارئ مُعين
- [ ] Stakeholders notified of execution window / أصحاب المصلحة مُبلغون
- [ ] Execute change / تنفيذ التغيير
- [ ] Post-deployment verification completed / التحقق بعد النشر مكتمل

---

### Step 7: Document + Update KB + Archive (MANDATORY) / التوثيق + تحديث قاعدة المعرفة + الأرشفة (إلزامي)

**This step is NOT optional.** Every change, successful or failed, must be fully documented.

**هذه الخطوة ليست اختيارية.** كل تغيير، ناجح أو فاشل، يجب توثيقه بالكامل.

#### Post-Change Documentation Checklist / قائمة التوثيق بعد التغيير

| # | Action / الإجراء | Status | Owner |
|---|-----------------|--------|-------|
| 1 | Write change summary report / كتابة تقرير ملخص التغيير | [ ] | |
| 2 | Document what actually happened vs. plan / توثيق ما حدث فعليا مقارنة بالخطة | [ ] | |
| 3 | Record any issues encountered / تسجيل أي مشاكل واجهتها | [ ] | |
| 4 | Update Knowledge Base with lessons learned / تحديث قاعدة المعرفة بالدروس المستفادة | [ ] | |
| 5 | Archive all artifacts (logs, configs, approvals) / أرشفة جميع المستندات | [ ] | |
| 6 | Update runbooks if procedures changed / تحديث الأدلة التشغيلية | [ ] | |
| 7 | Update system documentation / تحديث توثيق النظام | [ ] | |
| 8 | Close change request ticket / إغلاق تذكرة طلب التغيير | [ ] | |

#### Change Summary Report Template / نموذج تقرير ملخص التغيير

```
CHANGE SUMMARY REPORT / تقرير ملخص التغيير
============================================
Change Request ID: CR-____-____
Execution Date / تاريخ التنفيذ: ___________
Executed By / نُفّذ بواسطة: ___________

Result / النتيجة: [ ] SUCCESS  [ ] PARTIAL  [ ] FAILED  [ ] ROLLED BACK

Planned Duration / المدة المخططة: ___________
Actual Duration / المدة الفعلية: ___________

Issues Encountered / المشاكل التي واجهتها:
_______________________________________________

Lessons Learned / الدروس المستفادة:
_______________________________________________

KB Articles Created/Updated / مقالات قاعدة المعرفة:
_______________________________________________

Archived Location / موقع الأرشفة:
_______________________________________________
```

---

### Step 8: Update Automation If Applicable / تحديث الأتمتة إذا كان ذلك مناسبا

If the change revealed manual steps that should be automated, or if existing automation needs updating:

إذا كشف التغيير عن خطوات يدوية يجب أتمتتها، أو إذا كانت الأتمتة الحالية تحتاج تحديثا:

| # | Action / الإجراء | Status | Owner |
|---|-----------------|--------|-------|
| 1 | Identify manual steps that can be automated / تحديد الخطوات اليدوية القابلة للأتمتة | [ ] | |
| 2 | Update CI/CD pipeline if needed / تحديث CI/CD إذا لزم | [ ] | |
| 3 | Update monitoring/alerting rules / تحديث قواعد المراقبة والتنبيهات | [ ] | |
| 4 | Update deployment scripts / تحديث سكربتات النشر | [ ] | |
| 5 | Update rollback automation / تحديث أتمتة التراجع | [ ] | |
| 6 | Create/update Terraform/IaC if applicable / تحديث البنية كرمز | [ ] | |
| 7 | Add new test cases based on issues found / إضافة حالات اختبار جديدة | [ ] | |
| 8 | File automation improvement tickets / إنشاء تذاكر تحسين الأتمتة | [ ] | |

---

## 3. Process Flow Diagram / مخطط سير العملية

```
[1. Define Change]
       |
[2. Justify Why]
       |
[3. Assess Risks]
       |
[4. Review Lessons Learned]
       |
[5. Present to Stakeholder] ---> [REJECTED] ---> [Revise & Resubmit]
       |
   [APPROVED]
       |
[6. Execute Change]
       |
   [SUCCESS?]
    /       \
  YES        NO ---> [Rollback] ---> [Post-Mortem]
   |                                      |
[7. Document + KB + Archive]    [7. Document + KB + Archive]
   |                                      |
[8. Update Automation]          [8. Update Automation]
   |                                      |
  [DONE]                        [Resubmit from Step 1]
```

---

## 4. Emergency Change Process / عملية التغيير الطارئ

For genuine emergencies (P1 production outage), the following expedited process applies:

للطوارئ الحقيقية (توقف إنتاج P1)، تُطبق العملية المُعجّلة التالية:

1. **CTO verbal approval** to proceed (documented immediately after) / موافقة شفهية من المدير التقني
2. **Execute the minimum fix only** -- no additional changes / تنفيذ الحد الأدنى للإصلاح فقط
3. **Full documentation within 24 hours** / توثيق كامل خلال 24 ساعة
4. **Post-hoc formal change request** filed and reviewed / طلب تغيير رسمي بأثر رجعي
5. **Post-mortem within 48 hours** / تحليل جذري خلال 48 ساعة

**WARNING / تحذير:** Abuse of the emergency process will result in escalation. Every emergency change is audited.

---

## 5. Reference: Railway Incident / مرجع: حادثة Railway

This protocol was born from the Railway production incident. Key failures that this protocol addresses:

| Failure / الفشل | Protocol Step That Prevents It / الخطوة التي تمنعه |
|----------------|---------------------------------------------------|
| No risk assessment / لم يكن هناك تقييم مخاطر | Step 3: Formal risk matrix |
| No rollback plan / لم تكن هناك خطة تراجع | Step 3: Mandatory rollback plan |
| No approval process / لم تكن هناك عملية اعتماد | Step 5: Stakeholder approval required |
| No lessons learned review / لم تتم مراجعة الدروس | Step 4: KB search mandatory |
| No documentation / لم يكن هناك توثيق | Step 7: Mandatory documentation + archiving |
| No automation update / لم يتم تحديث الأتمتة | Step 8: Automation review |

---

*Document Version: 1.0*
*Created: 2026-04-06*
*Review Cycle: Quarterly / كل ربع سنة*
*Related: [Deployment Sign-Off Protocol](deployment-signoff.md)*
