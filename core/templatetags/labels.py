"""عنوانُ الصفّ في القوالب — بالصيغة الوزاريّة نفسِها التي في الشاشات الأخرى.

{% load labels %}
{% class_label row.grade_code row.section_code %}   →  07/2
"""

from django import template

from core.labels import class_label as _label

register = template.Library()


@register.simple_tag(name="class_label")
def class_label(grade, section):
    return _label(grade, section)
