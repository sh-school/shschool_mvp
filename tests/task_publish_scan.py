"""[B4-6] ماسحٌ واحد لمواضع نشر مهامّ Celery — يستعمله أكثر من حارس.

كُتب لأن حارساً جديداً وُلد أضعف من ماسحٍ قائم في المستودع: كان يشترط
`ast.Name` باسم المهمّة، فتمرّ من تحته ثلاث صيغ من أربع.

**ولا يدّعي أنه محلّل ساكن كامل لبايثون.** غرضه تغطية طرق النشر الواقعية في هذا
المستودع، وأن يُمسك الانحراف المعتاد في مراجعةٍ عابرة — لا أن يُثبت استحالته.
فما يمرّ منه اليوم: نشرٌ عبر متغيّر يُسنَد في وقت التشغيل، أو `getattr`، أو اسم
مهمّة يُبنى من أجزاء.

الصيغ المُغطّاة:

    send_push_task.delay(...)                      اسمٌ مباشر
    sp.delay(...)                                  بعد `import ... as sp`
    notifications.tasks.send_push_task.delay(...)  مسارٌ منقّط
    app.send_task("notifications.send_push", ...)  بالاسم النصّي

والأخيرة أصعبها: لا تمرّ بكائن المهمّة إطلاقاً، فلا تُلتقط بهويّة بل بالنصّ.
"""

import ast
from collections import namedtuple

#: موضع نشر واحد. `task` اسم رمز المهمّة كما يُعرَف في الكود، و`task_name` اسمها
#: المسجَّل في Celery حين يكون النشر بالاسم النصّي.
PublishSite = namedtuple("PublishSite", "lineno enclosing method task task_name keywords")

PUBLISH_METHODS = frozenset({"delay", "apply_async", "s", "signature"})
BY_NAME_METHODS = frozenset({"send_task"})


def _alias_map(tree):
    """`from notifications.tasks import send_push_task as sp` ⇒ {sp: send_push_task}."""
    aliases = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                aliases[name.asname or name.name] = name.name
        elif isinstance(node, ast.Import):
            for name in node.names:
                if name.asname:
                    aliases[name.asname] = name.name

    return aliases


def _symbol(node):
    """آخرُ اسمٍ في `X` أو `a.b.X` — أو None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _literal(node):
    """قيمةُ سلسلةٍ حرفية، أو None."""
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def iter_publish_sites(text, *, extra_publishers=None):
    """كل موضع ينشر مهمّةً في هذا الملفّ.

    `extra_publishers` يربط دالّةً مملوكة بالمهمّة التي تنشرها — مثل
    `{"enqueue_push": "send_push_task"}` — فيتبع الماسحُ المُنتِج حيث انتقل.
    """
    extra_publishers = extra_publishers or {}
    tree = ast.parse(text)
    aliases = _alias_map(tree)
    sites = []

    def _walk(node, enclosing):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            enclosing = node.name

        if isinstance(node, ast.Call):
            site = _classify(node, enclosing, aliases, extra_publishers)
            if site is not None:
                sites.append(site)

        for child in ast.iter_child_nodes(node):
            _walk(child, enclosing)

    _walk(tree, None)
    return sites


def _classify(node, enclosing, aliases, extra_publishers):
    keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
    func = node.func

    # ناشرٌ مملوك: `enqueue_push(...)`
    if isinstance(func, ast.Name) and func.id in extra_publishers:
        return PublishSite(
            node.lineno, enclosing, func.id, extra_publishers[func.id], None, keywords
        )

    if not isinstance(func, ast.Attribute):
        return None

    # نشرٌ بالاسم النصّي: `app.send_task("notifications.send_push", ...)`
    if func.attr in BY_NAME_METHODS:
        name = _literal(node.args[0]) if node.args else None
        if name is None:
            for keyword in node.keywords:
                if keyword.arg == "name":
                    name = _literal(keyword.value)
        return PublishSite(node.lineno, enclosing, func.attr, None, name, keywords)

    if func.attr not in PUBLISH_METHODS:
        return None

    symbol = _symbol(func.value)

    if symbol is None:
        return None

    # الاسم المستعار يُردّ إلى أصله قبل المقارنة.
    return PublishSite(
        node.lineno, enclosing, func.attr, aliases.get(symbol, symbol), None, keywords
    )
