"""[التشغيل] إيقاعُ تطبيق المعاينة وحدُّ التثبيت وطابورُه وفجوةُ الظهور (W-20261002-029، قرارُ المالك 2026-10-02).

كان التطبيقُ ينتظر سكونَ main ثلاثَ دقائقَ بسقفٍ 15، والدمجُ دفعاتٌ فقد لا يهدأ. صار إيقاعاً إجباريّاً كلَّ 10 دقائق (وأوّلُ تغييرٍ بعد خمولٍ فوراً)،
وصار التثبيتُ بحدٍّ أقصى 30 دقيقةً بالقصّ لا الرفض، ومن يُرفض تثبيتُه يدخل طابورَ انتظارٍ يُثبَّت آليّاً عند الفكّ، ويُقاس الظهورُ من سجلّ تطبيقاتٍ (`gaps`).

لا docker ولا شبكة ولا تشغيلَ للسكربت على 8500: تُستدعى دوالُّه بـ`source` في مستودعٍ مؤقّت (كـ`test_preview_integration.py`)؛ والحالةُ ملفّاتٌ حقيقيّةٌ
في مجلّد الحالة المؤقّت (`PREVIEW_DRY_RUN=0` للدوالّ التي تكتبها فقط)، وما يلمس docker (`deploy_pin`) يُستبدل بدالّةٍ وهميّةٍ تطبع ما كانت ستفعله.
"""

from __future__ import annotations

import shutil
import time

import pytest

from tests.test_preview_integration import (
    SCRIPT,
    Sandbox,
    _git,
    _git_version,
    _write,
)

pytestmark = [
    pytest.mark.skipif(shutil.which("bash") is None, reason="لا bash في هذه البيئة"),
    pytest.mark.skipif(_git_version() < (2, 38), reason="merge-tree --write-tree يلزمه git 2.38"),
]

LIVE = {"PREVIEW_DRY_RUN": "0"}


@pytest.fixture(scope="module")
def box(tmp_path_factory) -> Sandbox:
    sandbox = Sandbox(tmp_path_factory.mktemp("cadence"))
    for name in ("a", "b", "c"):  # شجراتٌ «قابلةٌ للتثبيت» (manage.py) — لا يُلمس غيرُ ملفٍّ غيرِ متتبَّع
        _write(sandbox.wt / name / "manage.py", "")
    return sandbox


@pytest.fixture()
def clean(box):
    if box.state.exists():
        shutil.rmtree(box.state)
    yield
    if box.state.exists():
        shutil.rmtree(box.state)


def _state(box, name, text):
    """ملفُّ حالةٍ بنهايات LF كما يكتبها السكربتُ نفسُه (`write_text` على ويندوز يكتب CRLF)."""
    box.state.mkdir(parents=True, exist_ok=True)
    (box.state / name).write_bytes(text.encode("utf-8"))


def _out(result):
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


# ── الإيقاع ─────────────────────────────────────────────────────


def test_the_defaults_are_the_owners_decision(box):
    out = _out(box.bash('echo "$APPLY_EVERY $QUIET $PIN_MAX $PIN_MINUTES $MAX_WAIT"'))
    assert out == "600 0 30 30 900"


def test_due_by_the_cadence_even_if_main_never_settles(box):
    # آخرُ تطبيقٍ قبل 601 ثانيةً، وmain يتغيّر الآن (عمرُ التغيّر 5 ثوانٍ فقط، لا سكون)
    assert box.bash("apply_due 0 5 700 601").returncode == 0
    assert box.bash("apply_due 0 5 700 600").returncode == 0


def test_not_due_before_the_cadence_and_without_force(box):
    assert box.bash("apply_due 0 5 100 599").returncode == 1
    assert (
        box.bash("apply_due 0 400 100 599").returncode == 1
    )  # لا سكونَ مفعَّلاً افتراضاً: العمرُ وحدَه لا يكفي


def test_force_applies_at_once(box):
    assert box.bash("apply_due 1 0 0 0").returncode == 0


def test_the_old_quiet_rule_is_an_opt_in_switch(box):
    assert box.bash("apply_due 0 200 100 10", PREVIEW_QUIET_SECONDS="180").returncode == 0
    assert box.bash("apply_due 0 100 100 10", PREVIEW_QUIET_SECONDS="180").returncode == 1


def test_the_hard_wait_cap_stays_as_the_last_resort(box):
    assert box.bash("apply_due 0 0 900 10").returncode == 0
    assert box.bash("apply_due 0 0 899 10").returncode == 1


def test_a_zero_cadence_disables_it(box):
    assert box.bash("apply_due 0 5 100 99999", PREVIEW_APPLY_EVERY_SECONDS="0").returncode == 1


def test_the_first_change_after_idleness_is_due_at_once(box, clean):
    """بلا تطبيقٍ مسجَّل: العمرُ رقمٌ كبيرٌ فيحلّ الموعد."""
    age = int(_out(box.bash('apply_age "$(now)"')))
    assert age > 10**6
    assert box.bash(f"apply_due 0 1 1 {age}").returncode == 0


def test_the_age_is_measured_from_the_last_recorded_apply(box, clean):
    now = int(time.time())
    _state(box, "synced_at", str(now - 250))
    assert int(_out(box.bash(f"apply_age {now}"))) == 250


# ── حدُّ التثبيت ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("120", "30"),
        ("45", "30"),
        ("30", "30"),
        ("10", "10"),
        ("1", "1"),
        ("0", "30"),
        ("", "30"),
        ("abc", "30"),
    ],
)
def test_pin_minutes_are_clamped_not_refused(box, given, expected):
    assert _out(box.bash(f'clamp_pin_minutes "{given}"')) == expected


# ── طابورُ الانتظار ────────────────────────────────────────────


def _tree(box, name):
    return (box.wt / name).as_posix()


def test_adding_returns_the_position_and_dedupes(box, clean):
    a, b = _tree(box, "a"), _tree(box, "b")
    assert _out(box.bash(f'queue_add "{a}" 20', **LIVE)) == "1"
    assert _out(box.bash(f'queue_add "{b}" 15', **LIVE)) == "2"
    # a تعيد طلبَها: تنتقل إلى الآخر بمدّتها الجديدة ولا تتكرّر
    assert _out(box.bash(f'queue_add "{a}" 25', **LIVE)) == "2"
    lines = [
        line.split("\t")[:2]
        for line in (box.state / "pin_queue").read_text(encoding="utf-8").splitlines()
    ]
    assert lines == [[b, "15"], [a, "25"]]


def test_pop_takes_the_first_valid_tree_and_keeps_the_rest_in_order(box, clean):
    a, b, c = _tree(box, "a"), _tree(box, "b"), _tree(box, "c")
    gone = (box.wt / "gone").as_posix()  # شجرةٌ أُزيلت: تُسقط بصمتٍ لا تُثبَّت
    _state(box, "pin_queue", f"{gone}\t10\t1\n{a}\t20\t2\n{b}\t15\t3\n{c}\t5\t4\n")
    out = _out(box.bash('queue_pop; echo "$QTREE|$QMINS"', **LIVE))
    assert out == f"{a}|20"
    rest = [
        line.split("\t")[0]
        for line in (box.state / "pin_queue").read_text(encoding="utf-8").splitlines()
    ]
    assert rest == [b, c]


def test_pop_on_an_empty_queue_leaves_nothing(box, clean):
    assert _out(box.bash('queue_pop; echo "[$QTREE][$QMINS]"', **LIVE)) == "[][]"


def test_promotion_pins_the_next_waiter_with_its_minutes(box, clean):
    a, b = _tree(box, "a"), _tree(box, "b")
    _state(box, "pin_queue", f"{a}\t20\t1\n{b}\t15\t2\n")
    out = _out(box.bash('deploy_pin() { echo "PIN $(basename "$1") $2"; }\npromote_queue', **LIVE))
    assert "PIN a 20" in out and "دورُ المنتظِر" in out
    assert [
        ln.split("\t")[0]
        for ln in (box.state / "pin_queue").read_text(encoding="utf-8").splitlines()
    ] == [b]


def test_promotion_with_no_waiters_does_nothing(box, clean):
    assert _out(box.bash("deploy_pin() { echo PIN; }\npromote_queue", **LIVE)) == ""


def _busy_pin(box):
    """معاينةٌ مثبَّتةٌ الآن على شجرةٍ أخرى لعشرين دقيقةً."""
    _state(box, "mode", "pin")
    _state(box, "pin_tree", _tree(box, "c"))
    _state(box, "pin_until", str(int(time.time()) + 1200))


def test_a_refused_pin_queues_instead_of_failing_and_says_where(box, clean):
    _busy_pin(box)
    a = _tree(box, "a")
    result = box.bash(f'SELF_ROOT="{box.repo.as_posix()}"\ncmd_pin "{a}" 20', **LIVE)
    assert result.returncode == 0, result.stderr
    assert "طابور الانتظار بالترتيب 1" in result.stdout
    assert "--force" in result.stdout
    assert (box.state / "pin_queue").read_text(encoding="utf-8").startswith(f"{a}\t20\t")


def test_an_over_long_pin_request_is_clamped_with_a_notice(box, clean):
    _busy_pin(box)
    a = _tree(box, "a")
    result = box.bash(f'SELF_ROOT="{box.repo.as_posix()}"\ncmd_pin "{a}" 120', **LIVE)
    assert result.returncode == 0, result.stderr
    assert "قُصّت المدّةُ من 120" in result.stdout
    assert (box.state / "pin_queue").read_text(encoding="utf-8").split("\t")[1] == "30"


# ── سجلُّ التطبيقات وفجوةُ الظهور ───────────────────────────────


def test_a_successful_apply_appends_time_and_short_sha(box, clean):
    out = _out(box.bash('apply_log abcdef0123456789abcdef; cat "$(state_dir)/apply.log"', **LIVE))
    stamp, sha = out.split()
    assert abs(int(stamp) - time.time()) < 30 and sha == "abcdef012345"


def _empty_commit(box, parent, when):
    tree = _git(box.repo, "rev-parse", f"{parent}^{{tree}}")
    return _git(box.repo, "commit-tree", tree, "-p", parent, "-m", "c", when=when)


def test_the_gap_is_commit_time_to_visibility_time_per_new_commit(box, clean):
    now = int(time.time())
    base = box.main
    c1 = _empty_commit(box, base, now - 3600)
    c2 = _empty_commit(box, c1, now - 1800)
    _state(
        box,
        "apply.log",
        f"{now - 5000} {base[:12]}\n{now - 3000} {c1[:12]}\n{now - 1500} {c2[:12]}\n",
    )
    out = _out(box.bash('gap_stats "$(state_dir)/apply.log" 7', **LIVE))
    assert out == "n=2 max=600 p90=600 p50=300"  # 3600→3000 = 600 ثانية، و1800→1500 = 300


def test_applies_older_than_the_window_are_ignored(box, clean):
    now = int(time.time())
    c1 = _empty_commit(box, box.main, now - 20 * 86400)
    _state(
        box,
        "apply.log",
        f"{now - 21 * 86400} {box.main[:12]}\n{now - 20 * 86400 + 600} {c1[:12]}\n",
    )
    assert _out(box.bash('gap_stats "$(state_dir)/apply.log" 7', **LIVE)) == "n=0"


def test_integration_merge_commits_are_not_counted_as_work(box, clean):
    """إيداعاتُ التكامل (دمجٌ) صنعتها المعاينةُ نفسُها لا مطوّر: لا تُحتسب فجوتُها."""
    now = int(time.time())
    c1 = _empty_commit(box, box.main, now - 3600)
    tree = _git(box.repo, "rev-parse", f"{c1}^{{tree}}")
    merge = _git(
        box.repo, "commit-tree", tree, "-p", c1, "-p", box.main, "-m", "merge", when=now - 100
    )
    _state(box, "apply.log", f"{now - 5000} {box.main[:12]}\n{now - 50} {merge[:12]}\n")
    out = _out(box.bash('gap_stats "$(state_dir)/apply.log" 7', **LIVE))
    assert out == "n=1 max=3550 p90=3550 p50=3550"  # c1 وحدَه: 3600→50، لا دمجَ التكامل


def test_the_report_is_honest_about_no_history_and_the_theoretical_before(box, clean):
    out = _out(box.bash("cmd_gaps"))
    assert "لا قياسَ رجعيّاً" in out
    assert "حدٌّ نظريٌّ من الإعداد القديم لا قياس" in out and "حتى 15 دقيقةً" in out


def test_the_report_shows_max_p90_and_median_from_the_log(box, clean):
    now = int(time.time())
    c1 = _empty_commit(box, box.main, now - 3600)
    _state(box, "apply.log", f"{now - 5000} {box.main[:12]}\n{now - 3000} {c1[:12]}\n")
    out = _out(box.bash("cmd_gaps", **LIVE))
    assert "الأقصى 10 دقيقة، وp90 10، والوسيط 10" in out


# ── الأسلاك: يبقى الإيقاعُ والسجلُّ موصولَين ───────────────────────────


def test_the_sync_cycle_uses_the_cadence_and_the_apply_is_logged():
    source = SCRIPT.read_text(encoding="utf-8")
    sync = source[source.index("cmd_sync() {") : source.index("cmd_watch() {")]
    assert 'apply_due "$force"' in sync and "apply_age" in sync and 'age" -ge "$QUIET"' not in sync
    assert "promote_queue" in sync  # عند انتهاء التثبيت يُثبَّت التالي
    apply = source[source.index("apply_main() {") : source.index("cmd_up() {")]
    assert 'apply_log "$target"' in apply
    assert source.count("promote_queue") >= 3  # التعريفُ والمزامنةُ والفكُّ اليدويّ
    assert "gaps)      cmd_gaps" in source
