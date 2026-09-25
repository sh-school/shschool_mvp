from django import template

from operations.schedule_paper import cell_kind

register = template.Library()

#: `{{ cell|cell_kind }}` — علامةُ خانةٍ في الجدول العامّ (`swap` أو `cover` أو `comp` أو فارغ).
#: هنا في `operations/templatetags` لا `core/templatetags`: الدالّةُ من `operations.schedule_paper`،
#: واستيرادٌ نازلٌ من core إلى operations يخالف حارس الطبقات (انظر `exemption_tags`).
register.filter("cell_kind", cell_kind)
