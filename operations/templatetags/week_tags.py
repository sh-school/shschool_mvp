from django import template

from core.dept_colors import dept_key
from operations.schedule_paper import cell_kind

register = template.Library()

#: `{{ cell|cell_kind }}` — علامةُ خانةٍ في الجدول العامّ (`swap` أو `cover` أو `comp` أو فارغ).
#: هنا في `operations/templatetags` لا `core/templatetags`: الدالّةُ من `operations.schedule_paper`،
#: واستيرادٌ نازلٌ من core إلى operations يخالف حارس الطبقات (انظر `exemption_tags`).
register.filter("cell_kind", cell_kind)

#: `{{ row.department.code|dept_key }}` — مفتاحُ لون القسم المركزيّ (`dept-{مفتاح}` في 20-components) لجدول الشاشة العامّ؛
#: الورقةُ تبقى بصنفها `dept-{كود}` لأنّ ألوانَها في قالبها (انظر `pdf/matrix_table.html`).
register.filter("dept_key", dept_key)
