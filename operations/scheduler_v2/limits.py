"""limits.py — سقوفُ زمن التوليد في مكانٍ واحد (W-20261010-031).

كانت ثلاثةُ أرقامٍ تحكم مصيرَ توليدٍ واحد، كلٌّ في ملفّ: `soft_time_limit` للمهمّة، وحارسُ
`reap_stuck_schedule_generations` (900+300ث)، وحارسُ الزرّ (20 دقيقة). فلمّا صار الزرُّ يولّد
بـV2 (سقفُه 30 دقيقةً) كان الحارسان يُفشلان توليداً سليماً ما زال يعمل. فهنا المصدرُ الوحيد،
ولا يعرّف أحدٌ سقفاً آخر.
"""

from __future__ import annotations

#: مهلةُ الحلّال نفسِه (runner.DEFAULT_MAX_SECONDS) — يقرؤها المشغّل منها لا من هنا.
SOLVER_MAX_SECONDS = 1800
#: سقفُ المهمّة الليّن: الحلُّ + التقييمُ + كتابةُ المسودّة بهامش.
GENERATION_SOFT_TIME_LIMIT = 3600
GENERATION_HARD_TIME_LIMIT = GENERATION_SOFT_TIME_LIMIT + 60
#: هامشُ انتظارٍ في الطابور قبل أن يلتقط عاملٌ المهمّة.
QUEUE_MARGIN_SECONDS = 300
#: بعده يُعدّ التوليدُ المعلّقُ ميّتاً: يُفشله الحارسُ ويُفتح الزرُّ من جديد.
GENERATION_STALE_AFTER_SECONDS = GENERATION_SOFT_TIME_LIMIT + QUEUE_MARGIN_SECONDS
