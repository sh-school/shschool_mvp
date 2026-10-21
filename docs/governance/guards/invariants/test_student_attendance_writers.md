# حارسُ الثوابت: رصدُ المعلّم الفعليّ واعتمادُه (W-20261002-020، D-125م)

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **رصدُ المعلّم الفعليّ واعتمادُه (W-20261002-020، D-125م)** | `test_student_attendance_writers`، `test_attendance_ledger_readers_guard`، `test_attendance_erasure_flag_guard`، `test_attendance_ledger_hardening`، `test_attendance_teacher_changes_s7` | (١) **الكتّاب**: لا كاتبَ جديداً على `StudentAttendance` خارج `ALLOWED_WRITERS` بسببٍ يُراجَع (مسحُ AST)، وما لا يلتقطه المسحُ في `UNDETECTABLE_BY_SCAN`؛ (٢) **القرّاء**: لا وحدةَ تذكر `AttendanceEntry`/`AttendanceDecision` أو علاقتَيهما خارج `ALLOWED_READERS` — فالرصدُ المعتمَدُ في `StudentAttendance` وحدَه والمبدئيُّ لا يُحتسب حضوراً ولا غياباً؛ (٣) **المحو**: علَمُ `app.attendance_erasure` لا يُكتب إلّا في `erase_attendance_ledger`؛ (٤) **السجلّ**: مُشغِّلُ القاعدة يمنع UPDATE وDELETE إلّا بعلَم المحو داخل المعاملة، وRLS على الجدولين، ولا TRUNCATE لدور التطبيق؛ (٥) **S7**: كاتبُ `Session.teacher` جديدٌ يسقط الاختبارَ حتى يُضاف له اختبارُ مسارٍ يثبت أنّه يكتب عند التنفيذ وحدَه |
