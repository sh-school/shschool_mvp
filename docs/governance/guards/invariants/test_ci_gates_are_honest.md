# حارسُ الثوابت: بوّاباتُ CI الصادقة

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **بوّاباتُ CI الصادقة** | `test_ci_gates_are_honest` (`test_no_workflow_hides_a_failing_command_behind_tee`، `TestTheDeployCheckStepIsHonest`)، `test_security_gate` (`test_the_deploy_check_environment_boots_the_production_settings`، `test_the_silenced_system_checks_are_only_the_known_documentation_warnings`) | وظيفةٌ تظهر في ملخّصٍ لا تُبتلع أخطاؤها (`\|\| true`، `\| head`، `continue-on-error`)؛ **وخطوةٌ تلتقط مخرجَ أمرٍ بـ`\| tee` تُفعِّل `pipefail`** (صدفةُ GitHub الافتراضيّة `bash -e` بلا pipefail، فخروجُ الخطّ خروجُ `tee`)؛ وخطوةُ `django check --deploy` تُشغَّل بصدفة GitHub وتُثبَت أنّها تفشل حين ينهار الفحص؛ وبيئةُ وظيفتها تُقلع بها إعداداتُ الإنتاج (S3 إلزاميّ)؛ والمُسكَتُ من فحوص النظام في الإنتاج تحذيراتُ توثيق drf-spectacular وحدَها (`SILENCED_SYSTEM_CHECKS`) |
