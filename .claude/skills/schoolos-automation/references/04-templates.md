# قوالبُ البداية — أمرٌ ومهمّةٌ ومسارُ عملٍ وسكربتُ ويندوز

متى تقرأ هذا الملف: عند كتابة الأتمتة بعد اختيار مكانها. انسخ الهيكل وعدّل الأسماء؛ الأسماءُ هنا مختلَقة (`reports.weekly_digest`).

## 1) المنصّة: خدمةٌ واحدة، يستدعيها أمرٌ ومهمّة (نمط `enforce_retention`)
المنطقُ في الخدمة وحدَها، فالأمرُ للتشغيل اليدويّ والتحقّق، والمهمّةُ للجدول — ولا تكرار. المصدر: `governance/tasks.py`، `.../commands/enforce_retention.py`.
```python
# reports/services/weekly_digest.py
@dataclass(frozen=True)
class DigestReport:
    enabled: bool
    counts: dict[str, int]          # أعدادٌ فقط — لا أسماء

def run_weekly_digest(*, dry_run: bool) -> DigestReport:
    """ثابتةُ التكرار: تختار ما لم يُعالَج بعد (حقلُ ختم) لا «ما جرى هذا الأسبوع»."""
    if not settings.WEEKLY_DIGEST_ENABLED:            # مفتاحُ الإيقاف من البيئة
        return DigestReport(enabled=False, counts={})
    pending = Item.objects.filter(digested_at__isnull=True)
    if not dry_run:
        with transaction.atomic():
            ...                                        # العمل، ثمّ ختمُ الصفوف المعالجة
            AuditLog.objects.create(...)               # ملخّصُ ما كُتب
    return DigestReport(enabled=True, counts={"pending": pending.count()})
```
```python
# reports/management/commands/weekly_digest.py — عرضٌ افتراضاً، وكتابةٌ بـ--apply
class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="التنفيذُ فعلاً")
    def handle(self, *args, **opts):
        report = run_weekly_digest(dry_run=not opts["apply"])
        if not report.enabled:
            self.stdout.write(self.style.WARNING("معطَّل من الإعداد — لا شيء."))
            return
        for key, n in report.counts.items():
            self.stdout.write(f"{n:>7}  {key}")
```
```python
# reports/tasks.py — اسمٌ صريحٌ ثابت، ومهلةٌ أقصرُ من الدورة، وقفلٌ ضدّ التداخل
LOCK = "lock:reports.weekly_digest"

@shared_task(name="reports.weekly_digest", soft_time_limit=120, time_limit=150,
             autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3)
def weekly_digest() -> dict:
    if not cache.add(LOCK, 1, timeout=150):          # تشغيلٌ سابقٌ لم ينتهِ: تخطٍّ لا تكرار
        logger.info("weekly_digest: skipped, previous run still holds the lock")
        return {"skipped": 1}
    try:
        return run_weekly_digest(dry_run=False).counts
    finally:
        cache.delete(LOCK)
```
```python
# shschool/celery.py — داخل app.conf.beat_schedule، والتعليقُ يذكر السببَ والتوقيت (قطر)
"reports-weekly-digest": {
    "task": "reports.weekly_digest",
    "schedule": crontab(hour=6, minute=10, day_of_week="0"),  # الأحد 06:10 الدوحة، قبل الدوام
},
```
مهمّةٌ لمدرسةٍ بعينها: ترث `TenantRLSTask` وتأخذ `school_id` (`core/celery_tasks.py`). وإن لزم المالكَ أن يرى نتيجتَها لوحةً: مجمِّعٌ بـ`contract.store` (`03-output-contract.md`).

## 2) الاختبارات الدنيا
```python
def test_digest_is_idempotent(db):
    first = run_weekly_digest(dry_run=False)
    second = run_weekly_digest(dry_run=False)
    assert second.counts["pending"] == 0             # الثاني لا يجد ما يعالجه

def test_dry_run_writes_nothing(db): ...
def test_disabled_by_setting(settings, db): ...

def test_digest_is_scheduled_on_sunday_before_school():
    app.loader.import_default_modules()
    [entry] = [e for e in app.conf.beat_schedule.values() if e["task"] == "reports.weekly_digest"]
    assert entry["schedule"].day_of_week == {0} and max(entry["schedule"].hour) < 7
```
والتسجيلُ يحرسه `tests/test_beat_tasks_registered.py` تلقائيّاً. شغّلها بأمر الاختبار في CLAUDE.md.

## 3) Actions مجدول (لعملٍ يحتمل التأخّر)
انسخ خطوتَي «الفشل: فتحُ قضيّةٍ أو التعليقُ على المفتوحة» و«النجاح: إغلاقُ قضايا الفشل» من `.github/workflows/nightly.yml` كما هما، وغيّر البادئةَ والوسم.
```yaml
name: <وصفٌ صادق — «بأفضل جهد» إن كان مراقباً>
on:
  schedule:
    - cron: "30 1 * * 0"   # الأحد 01:30 UTC = 04:30 الدوحة
  workflow_dispatch:
concurrency:
  group: <اسمٌ-ثابت>
  cancel-in-progress: false
permissions:
  contents: read
  issues: write
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v7
      - name: التشغيل
        env:
          PRODUCTION_URL: ${{ vars.PRODUCTION_URL }}   # متغيّرٌ لا نصٌّ حرفيّ
        run: |
          set -euo pipefail
          python scripts/<script>.py --json | tee result.json
      - name: ملخّص
        if: always()
        run: { echo "## <العنوان>"; cat result.json 2>/dev/null || echo "لا نتيجة"; } >> "$GITHUB_STEP_SUMMARY"
      # + خطوتا الفشل والنجاح من nightly.yml
```
التعديلُ على `.github/workflows/` يحتاج إذنَ المالك الصريح (مصنِّفُ الأذونات).

## 4) سكربتُ ويندوز (بايثون) — قفلٌ وحالةٌ ورمزُ خروج
```python
# <automation>.py — يعمل بـpythonw بلا نافذة، فالسجلُّ ملفٌّ لا شاشة
AUTOMATION, PERIOD_H, GRACE_H = "watch-once", 0.5, 1

def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    lock, failed = out / f"{AUTOMATION}.lock", out / f"{AUTOMATION.upper()}_FAILED.txt"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # إنشاءٌ حصريّ = القفل
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < 3600:
            return 0                                   # تشغيلٌ آخر يعمل: تخطٍّ هادئ
        lock.unlink(); fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # قفلٌ عالق
    started = datetime.now().astimezone()
    status = {"automation": AUTOMATION, "ok": False, "started": started.isoformat(timespec="seconds"),
              "exit_code": 1, "counts": {}, "err": "", "grace_h": GRACE_H}
    try:
        status["counts"] = do_work()                   # أعدادٌ فقط
        status.update(ok=True, exit_code=0)
        failed.unlink(missing_ok=True)
    except Exception as exc:                           # لا كتمان: رمزٌ في الحالة والتفصيلُ في السجلّ
        status["err"] = type(exc).__name__
        failed.write_text(f"{AUTOMATION} {started:%Y-%m-%d %H:%M} {status['err']}\n", encoding="utf-8")
        log(out, traceback.format_exc())
    finally:
        os.close(fd); lock.unlink(missing_ok=True)
        now = datetime.now().astimezone()
        status["finished"] = now.isoformat(timespec="seconds")
        status["next_due"] = (now + timedelta(hours=PERIOD_H)).isoformat(timespec="seconds")
        tmp = out / "LAST_STATUS.json.tmp"             # كتابةٌ ذرّيّة
        tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out / "LAST_STATUS.json")
    return status["exit_code"]

if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
```
التسجيل (بموافقة المالك، أمرٌ يشغّله هو أو يأذن به): `New-ScheduledTaskTrigger` + `New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)` كما في `~/.claude/scripts/install_backup_task.ps1`، والمهمّةُ تحت المجلّد `\SchoolOS\`.

## أنماطٌ مضادّة
- منطقٌ مكرَّرٌ في الأمر والمهمّة بدل خدمةٍ واحدة.
- أمرٌ يكتب افتراضاً بلا `--apply` — تشغيلٌ يدويٌّ للفحص يصير تنفيذاً.
- `cache.delete(LOCK)` خارج `finally`، أو قفلٌ بلا مهلة.
- نسخُ خطوة القضيّة وتركُ البادئة القديمة (يغلق قضايا مسارٍ آخر).
- `datetime.now()` بلا `astimezone()` في سجلٍّ يُقرأ على جهازٍ آخر.
