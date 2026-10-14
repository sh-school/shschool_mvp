from django import forms

from ux_survey.models import FREE_TEXT_MAX, SurveyResponse

SCALE = [(i, str(i)) for i in range(1, 6)]


def _radio(choices):
    return forms.ChoiceField(choices=choices, widget=forms.RadioSelect)


class SurveyForm(forms.Form):
    usage_frequency = _radio(SurveyResponse.FREQUENCY)
    usage_place = _radio(SurveyResponse.PLACE)
    sus_easy = _radio(SCALE)
    sus_slow = _radio(SCALE)
    sus_confident = _radio(SCALE)
    sus_remember = _radio(SCALE)
    find_fast = _radio(SurveyResponse.FAST)
    hardest_task = forms.CharField(
        max_length=FREE_TEXT_MAX,
        widget=forms.Textarea(
            attrs={"rows": 3, "maxlength": FREE_TEXT_MAX, "class": "form-control"}
        ),
    )
    wish = forms.CharField(
        max_length=FREE_TEXT_MAX,
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "maxlength": FREE_TEXT_MAX, "class": "form-control"}
        ),
    )
