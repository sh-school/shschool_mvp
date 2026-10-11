"""نماذجُ الأدمن لتفضيلات المعلّم: سقفا الأولى والسابعة قائمتان من 2 إلى 5 لا غير (قرارُ المالك 2026-10-10).

المالكُ حسمها بعد معاينتين: لا إدخالَ حرّ ولا min/max ولا رسائلَ ولا خيارَ فارغ — قائمةٌ منسدلة خياراتُها
2 و3 و4 و5. و«فارغ» كان يعني السقفَ العامّ (اثنتان) فصارت القيمةُ المحدَّدةُ سلفاً هي 2، والمحرّكُ يحكم
بالقيمتين حكماً واحداً (الأولى: ما لا يعلو العامَّ لا يُقرأ؛ السابعة: `personal_last_cap(2) or 2`).
وما خُزّن قبل هذا القرار خارج المدى لا يُلمس: يظهر لصاحبه وحدَه خياراً محدَّداً فلا يُكتب فوقه بحفظٍ عابر.
"""

from django import forms

from .models import TeacherPreference
from .models.schedule import MAX_PERSONAL_FIRST, MIN_PERSONAL_FIRST

#: السقفُ العامّ للأولى والسابعة معاً (اثنتان) — القيمةُ المحدَّدة سلفاً حين لا يُختار شيء.
GENERAL_CAP = MIN_PERSONAL_FIRST
CAP_CHOICES = [(value, str(value)) for value in range(MIN_PERSONAL_FIRST, MAX_PERSONAL_FIRST + 1)]
CAP_FIELDS = ("max_first_periods", "max_last_periods")
#: قيمُ سقف التتالي الشخصيّ المسموحة كما في شاشة المعلّم (حصصُ اليوم سبع).
RUN_CAP_VALUES = tuple(range(1, 8))


def effective_cap(value: int | None) -> int:
    """القيمةُ التي يحكم بها المحرّك: الفارغُ هو العامّ، فلا يُسجَّل تغييرٌ بين الفارغ و2."""
    return GENERAL_CAP if value is None else value


class TeacherPreferenceAdminForm(forms.ModelForm):
    class Meta:
        model = TeacherPreference
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in CAP_FIELDS:
            model_field = TeacherPreference._meta.get_field(name)
            stored = self.initial.get(name) if self.instance.pk else None
            choices = list(CAP_CHOICES)
            if stored is not None and stored not in dict(CAP_CHOICES):
                choices.insert(0, (stored, str(stored)))
            self.fields[name] = forms.TypedChoiceField(
                label=model_field.verbose_name,
                help_text=model_field.help_text,
                choices=choices,
                coerce=int,
                required=True,
            )
            self.initial[name] = GENERAL_CAP if stored is None else stored
        self._run_cap_as_select()

    def _run_cap_as_select(self) -> None:
        """«أقصى حصص متتالية» قائمةٌ كأخويها: أوّلُها «السقف العامّ» (فارغ) ثم 1 إلى 7 كشاشة المعلّم.

        الفارغُ هنا قرارٌ معتبر (لا قرارَ شخصيَّ) فيبقى خياراً؛ وما خُزّن خارج 1–7 يظهر لصاحبه وحدَه.
        """
        from .preference_capacity import effective_run_cap

        name = "max_consecutive"
        model_field = TeacherPreference._meta.get_field(name)
        stored = self.initial.get(name) if self.instance.pk else None
        choices: list[tuple[int | str, str]] = [
            ("", f"السقف العامّ ({effective_run_cap(None)})"),
            *[(value, str(value)) for value in RUN_CAP_VALUES],
        ]
        if stored is not None and stored not in RUN_CAP_VALUES:
            choices.insert(1, (stored, str(stored)))
        self.fields[name] = forms.TypedChoiceField(
            label=model_field.verbose_name,
            help_text=model_field.help_text,
            choices=choices,
            coerce=int,
            empty_value=None,
            required=False,
        )
        self.initial[name] = "" if stored is None else stored
