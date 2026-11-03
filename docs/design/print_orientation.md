# جدولُ اتّجاه الطباعة الواحد (W-20261021-007، قرارُ المالك 2026-10-21)

**القاعدة:** أفقيٌّ للقوائم والكشوف (`sheet`)، وعموديٌّ للنماذج والخطابات (`form`، `letter`). **الشعارُ إلزاميٌّ** في الوثائق الإداريّة. **استمارةُ الإشراف خارج الإطار** عمداً. **الختمُ خانةٌ يدويّةٌ فارغة** (`components/print/stamp_box.html`).

المصدرُ البرمجيّ: `core/print_policy.py` (الجدولُ نفسُه)، وحارسُه `tests/test_print_policy.py`: قالبٌ مطبوعٌ جديدٌ بلا سطرٍ هناك يُسقط الاختبار، والدَّينُ لا يزيد.

## الجدول

| القالب | النوع | الاتّجاه اليوم | الحال | الشعار |
|---|---|---|---|---|
| `wings/register_pdf.html` | كشف | أفقي | مطابق | من `base_qatar_report` |
| `wings/ministry_pdf.html` | كشف | أفقي | مطابق | من `base_qatar_report` |
| `operations/absence_followup_print.html` | كشف | أفقي (التواصل والإجراءات) | مطابق — «الإجراءات» صارت أفقيّةً بقرار المالك D-449م | من `base_qatar_report` |
| `breach/pdf_report.html` | خطاب | عمودي | مطابق | من `base_qatar_report` |
| `quality/pdf/progress_report.html` | خطاب | عمودي | مطابق | من `base_qatar_report` |
| `schedule/print_schedule.html` وَ`print_pages.html` | كشف | أفقي | مطابق | الإطار المركزيّ |
| `behavior/pdf/base_form.html` | نموذج | عمودي | مطابق | الإطار المركزيّ |
| `quality/observation_pdf.html` | نموذج | عمودي | مطابق، **خارج الإطار عمداً** | وسمٌ محلّيّ |
| `reports/student_result_pdf.html` | نموذج | عمودي | مطابق | من `base_qatar_report` |
| `student_affairs/student_profile_pdf.html` | نموذج | عمودي | مطابق | من `base_qatar_report` |
| `student_affairs/student_list_pdf.html` | كشف | أفقي (صار) | مطابق + خانة ختم | من `base_qatar_report` |
| `student_affairs/attendance_overview_pdf.html` | كشف | أفقي (صار) | مطابق + خانة ختم | من `base_qatar_report` |
| `student_affairs/behavior_overview_pdf.html` | كشف | أفقي (صار) | مطابق + خانة ختم | من `base_qatar_report` |
| `student_affairs/tardiness_pdf.html` | كشف | أفقي (صار) | مطابق + خانة ختم | من `base_qatar_report` |

الشعارُ يرثه كلُّ قالبٍ يمتدّ من `reports/base_qatar_report.html` (وسمُ `ministry_logo` فيه)؛ فكلُّ الوثائق الإداريّة بشعار، واستمارةُ الإشراف بوسمها المحلّيّ. والدَّينُ المسجَّل صفر.

## ما صُنِّف في W-20261021-012

- `schedule/print_view.html` وَ`quality/observation_pdf_view.html`: **عرضا شاشة** يمتدّان من `base/base.html` (يحرس ذلك `test_screen_views_are_really_screen_pages`)، لا PDF مستقلّ.
- `wings/pdf/exit_permit.html`: نموذجٌ A5 عموديّ يرث `base_qatar_report` — سطرٌ في الجدول أعلاه.
- `wings/pdf/*` الباقية (`section_sheet`، `sheet_footer`، `signatures`، `wing_summary`) وَ`schedule/pdf/*`: جزئيّاتٌ تُدمج في قوالبَ مصنَّفةٍ لا وثائقُ مطبوعةٌ قائمةٌ بذاتها.
- قوالبُ `exam_control` (`incident_pdf`، `session_report_pdf`) تُبنى في `exam_control/views.py` عبر `core.pdf_utils.render_pdf`؛ **لم تُقرأ بعد** وتبقى لبطاقةٍ لاحقة.

## مساراتُ الطباعة الأربعة

1. **`base_qatar_report`** — القالبُ الأمّ للوثائق الإداريّة (الشعارُ والتذييلُ منه): كشوفُ الأجنحة والحضور وشؤون الطلاب والخطابات.
2. **الإطارُ المركزيّ** `core/print_frame.py` + وسوم `print_frame_*` — الجدول الدراسي ونموذج السلوك (ترقيمُ صفحاتٍ «صفحة س من ص»).
3. **`components/pdf_footer.html`** — تذييلُ سطرٍ واحد بلا ترقيم، لاستمارة الزيارة الصفّيّة وحدَها (خارج الإطار عمداً).
4. **`core/pdf_utils.render_pdf`** بقوالبَ تصوغ أنماطها محلّيّاً (مثل `exam_control`) — الدَّينُ غيرُ المصنَّف أعلاه.

## قرارٌ محسوم

«الإجراءات» في متابعة الغياب كشفٌ بأعمدة؛ قرّر المالك (D-449م) أن تُطبع أفقيّةً كالقوائم، فنُسخ قرارُ 2026-10-17 وصار `DEFAULT_ORIENT["actions"] = "landscape"`.
