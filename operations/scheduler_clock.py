"""ساعةُ محاولة التوليد — مسؤوليّةٌ مستقلّةٌ عن الشبكة والمحاولات (W-20261002-033)."""

from __future__ import annotations

import time
from collections.abc import Callable


class Deadline:
    """ساعةُ البحث: تُمرَّر إلى الإصلاح فيقف عند نفاد الميزانية، وتذكر أنّها قطعت ومتى (لتُسجَّل في اللقطة).

    كانت الميزانيةُ تُسأل **بين المحاولات** وحدَها، والمحاولةُ نفسُها (الإزاحةُ الموجَّهة بعمق 3 لكلّ متعذّرة،
    ثلاثَ مرّاتٍ) بلا ساعةٍ — فشعبةٌ فوق سعتها تُنفق ≈290 ثانيةً على ميزانيةِ 4 ثوانٍ (W-20261002-033).
    والفحصُ عند كلّ متعذّرة: تجاوزُه بقدر إزاحةٍ واحدةٍ لا أكثر. وبساعةٍ رتيبةٍ (`monotonic`) فلا يُربكها تعديلُ
    ساعة النظام. وبعد أوّل قطعٍ تبقى منتهيةً: المحاولاتُ اللاحقةُ تُنهي إصلاحَها فوراً (مقصود).
    """

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started = clock()
        self.at = self._started + seconds
        self.attempt = 0  # المحاولةُ الجاريةُ — تضعها حلقةُ التوليد
        self.hit = False
        self.hit_attempt: int | None = None
        self.hit_after: float | None = None

    def expired(self) -> bool:
        if not self.hit and self._clock() >= self.at:
            self.hit = True
            self.hit_attempt = self.attempt
            self.hit_after = round(self._clock() - self._started, 1)
        return self.hit
