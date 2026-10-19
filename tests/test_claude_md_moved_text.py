"""سقّاطةُ النقل الحرفيّ: كلُّ نصٍّ نُقل من `CLAUDE.md` موجودٌ في وجهته (W-20261015، قرار المالك).

تقليصُ الدستور بلا فقد قاعدة: يفشل الاختبارُ لو حُذف المنقولُ أو بُدّل.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

MOVED = [
    (
        "docs/deployment/session_server.md",
        "كانت القاعدةُ قبل 2026-09-08 «لا worktree أبداً» لأنّ `docker-compose.yml` يربط `- .:/app`؛ فعالجت\nالعَرَضَ بمنع العزل وصار رأسٌ وفهرسٌ واحدٌ لمحادثاتٍ متوازية (تبديلُ فرعٍ يسحب الأرضَ من تحت غيره، و`git add -A`\nيبتلع عملَ غيره). و`docker-compose.session.yml` أزال السبب: خادمٌ لكلّ شجرةٍ على منفذها بقاعدةٍ مشتركة.",
    ),
    (
        "docs/deployment/session_server.md",
        "```bash\ndocker compose -p schoolos-$(basename $PWD) --project-directory . -f D:/shschool_mvp/docker-compose.session.yml exec -T web sh -c 'DJANGO_SETTINGS_MODULE=shschool.settings.testing TEST_DB_HOST=$DB_HOST TEST_DB_PORT=$DB_PORT TEST_DB_USER=$DB_USER TEST_DB_PASSWORD=$DB_PASSWORD python -m pytest <المسارات> -q -p no:cacheprovider'\n```\nواسمُ قاعدةِ الاختبار يُشتقّ من قاعدةِ جلستك تلقائيّاً (`test_ss_<slug>`)، فلا\nتصطدم جلستان. ولو رأيتَ عشراتِ `ERROR` في **الإعداد** دفعةً واحدة فاقرأ\nالرسالةَ قبل أن تتّهم تعديلك: غالبُها تصادمٌ لا عطب.",
    ),
    (
        "docs/deployment/local_preview.md",
        "- **يتبع `main` وما أودعته الجلساتُ ولم يُدمج** بوضع الإنتاج ويتحدّث تلقائياً كلَّ 10 دقائق؛ والحالةُ بـ`bash scripts/preview.sh status`، ولِمَ يُتخطّى فرعٌ بـ`bash scripts/preview.sh integrate`.",
    ),
    (
        "docs/deployment/local_preview.md",
        "وحرّاسُ CSS/JS النصّيّة بلا خادم: `docker run --rm --network none …`.",
    ),
    (
        "docs/deployment/local_preview.md",
        "والمعاينةُ لا تعكس الإنتاجَ في التخزين والبريد وSentry وbeat والبيانات.",
    ),
    (
        ".claude/rules/deploy-window.md",
        "- **الهجراتُ آمنةٌ الآن بلا هذه القاعدة** (`preDeployCommand`، انظر\n  `scripts/railway-predeploy.sh`) — لكنّ إعادة تشغيل daphne نفسِها تقطع طلباتٍ\n  مفتوحة، فالقاعدةُ عن توقيت النشر لا عن سلامة الهجرة وحدها.",
    ),
    (
        ".claude/rules/deploy-window.md",
        "الاسمُ الحاليّ جزءٌ من مفتاح الذاكرة\n  (`CACHE_NAME`؛ مثلاً `schoolos-global-v2`، `schoolos-parents-v3`)، فرفعُ\n  الرقم يُبطل النسخةَ القديمة على أجهزة المستخدمين دون انتظار Ctrl+Shift+R.",
    ),
]


@pytest.mark.parametrize(("dest", "text"), MOVED)
def test_moved_text_exists_verbatim(dest, text):
    body = (ROOT / dest).read_text(encoding="utf-8")
    assert text in body, f"النصّ المنقول مفقودٌ من {dest}"
