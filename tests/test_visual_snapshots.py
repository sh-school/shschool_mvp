"""[IDENTITY] مقارنةُ لقطات الهويّة (VI-13) — منطقُ المقارنة بلا متصفّح. راجع `tests/visual_snapshots.py`.

هذه الاختباراتُ تحرس **المقارِن** لا الصفحات: إن أخطأ فأعلن لقطتَين مختلفتَين متطابقتَين ضاعت الحمايةُ كلُّها بصمت، وإن أعلن
متطابقتَين مختلفتَين حُجب كلُّ طلبٍ بلا سبب. والتقاطُ الصفحات نفسِها في `tests/e2e/test_visual_snapshots_live.py`.
"""

from __future__ import annotations

import ast
import pathlib

from PIL import Image

from tests import visual_snapshots as vs


def _image(path, colour=(255, 255, 255), size=(40, 30), paint=None):
    image = Image.new("RGB", size, colour)
    if paint:
        for xy, value in paint.items():
            image.putpixel(xy, value)
    image.save(path)
    return path


def test_identical_images_have_no_difference(tmp_path):
    a = _image(tmp_path / "a.png")
    b = _image(tmp_path / "b.png")
    diff = vs.compare(a, b)
    assert diff.ratio == 0 and diff.changed == 0 and diff.bbox is None and not diff.size_mismatch


def test_a_real_change_is_counted_and_located(tmp_path):
    a = _image(tmp_path / "a.png")
    b = _image(tmp_path / "b.png", paint={(5, 6): (200, 0, 0), (6, 6): (200, 0, 0)})
    diff = vs.compare(a, b)
    assert diff.changed == 2
    assert diff.ratio == 2 / (40 * 30)
    assert diff.bbox == (5, 6, 7, 7)


def test_noise_below_the_tolerance_is_ignored_and_above_it_is_not(tmp_path):
    a = _image(tmp_path / "a.png", colour=(100, 100, 100))
    quiet = _image(tmp_path / "quiet.png", colour=(100 + vs.PIXEL_TOLERANCE, 100, 100))
    loud = _image(tmp_path / "loud.png", colour=(100 + vs.PIXEL_TOLERANCE + 1, 100, 100))
    assert vs.compare(a, quiet).ratio == 0
    assert vs.compare(a, loud).ratio == 1


def test_a_change_in_any_single_channel_counts(tmp_path):
    a = _image(tmp_path / "a.png", colour=(50, 50, 50))
    for channel in range(3):
        colour = [50, 50, 50]
        colour[channel] += 60
        b = _image(tmp_path / f"b{channel}.png", colour=tuple(colour))
        assert vs.compare(a, b).ratio == 1, f"القناةُ {channel} لا تُعدّ"


def test_a_different_size_is_a_total_change(tmp_path):
    a = _image(tmp_path / "a.png", size=(40, 30))
    b = _image(tmp_path / "b.png", size=(40, 31))
    diff = vs.compare(a, b)
    assert diff.size_mismatch and diff.ratio == 1.0 and diff.bbox is None


def test_the_diff_image_paints_only_what_changed(tmp_path):
    a = _image(tmp_path / "a.png")
    b = _image(tmp_path / "b.png", paint={(3, 3): (0, 0, 0)})
    out = tmp_path / "out" / "diff.png"
    vs.save_diff(a, b, out)
    with Image.open(out) as image:
        assert image.getpixel((3, 3)) == (255, 0, 0)
        assert image.getpixel((0, 0)) == (255, 255, 255)


def _journeys() -> dict[str, tuple[str, ...]]:
    """`JOURNEYS` من `tests/test_mobile_audit.py` بلا استيراده (يتخطّى نفسَه بلا Playwright)."""
    tree = ast.parse(pathlib.Path("tests/test_mobile_audit.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "JOURNEYS":
            return {role: pages for role, (_fixture, pages) in ast.literal_eval(node.value).items()}
    raise AssertionError("JOURNEYS غيرُ معرَّف في tests/test_mobile_audit.py")


def test_the_matrix_is_the_identity_five_the_role_journeys_and_the_steps():
    shots = vs.matrix()
    identity = len(vs.SHOTS) * len(vs.THEMES) * len(vs.PROFILE_NAMES)
    journeys = len(vs.JOURNEY_SHOTS) * len(vs.PROFILE_NAMES)
    assert identity == 20 and journeys == 40 and len(vs.STEP_SHOTS) == 3
    assert len(shots) == identity + journeys + len(vs.STEP_SHOTS) == 63
    keys = [shot.key for shot in shots]
    assert len(set(keys)) == len(keys), "مفتاحان متطابقان — تُكتب لقطةٌ فوق أخرى"
    assert all("/" in key and key.endswith(".png") for key in keys)
    assert set(vs.PROFILE_NAMES) == {"mobile", "desktop"}


def test_every_shot_page_is_a_role_journey_page():
    """كلُّ (دور، صفحة) جديدٍ يجب أن يكون في `JOURNEYS` (الحسابُ المبذور والرابط) — شرطُ صاحب VI-13."""
    journeys = _journeys()
    every = list(vs.SHOTS) + list(vs.JOURNEY_SHOTS) + [(r, p) for r, p, *_ in vs.STEP_SHOTS]
    for role, page in every:
        assert page in journeys.get(role, ()), f"{role}:{page} ليست في JOURNEYS"


def test_the_journeys_are_covered_completely():
    """رحلاتُ الأدوار الخمس كلُّها في المصفوفة — صفحةٌ تُضاف إلى JOURNEYS تُضاف هنا أو تسقط بعلّتها."""
    every = {(role, page) for role, pages in _journeys().items() for page in pages}
    covered = set(vs.SHOTS) | set(vs.JOURNEY_SHOTS)
    assert not (set(vs.SHOTS) & set(vs.JOURNEY_SHOTS)), "صفحةٌ في القائمتَين — لقطتان لشيءٍ واحد"
    assert (
        covered == every
    ), f"غيرُ مغطّاة: {sorted(every - covered)}؛ زائدةٌ: {sorted(covered - every)}"


def test_the_steps_are_known_and_the_mobile_menu_is_mobile_only():
    for role, page, step, profile in vs.STEP_SHOTS:
        assert step in vs.STEPS and profile in vs.PROFILE_NAMES
        if step == "menu":
            assert profile == "mobile", "قائمةُ الهامبرغر لا تظهر على سطح المكتب"
    assert "@menu" in vs.shot_key("leadership", "dashboard", "light", "mobile", "menu")
    assert "@" not in vs.shot_key("leadership", "dashboard", "light", "mobile")


def test_the_summary_lists_every_shot():
    rows = [
        {"key": "mobile/light/a.png", "determinism": 0.0, "change": None, "status": "✓"},
        {"key": "desktop/dark/b.png", "determinism": 0.0004, "change": 0.0123, "status": "تغيّر"},
    ]
    text = vs.summary_markdown(rows)
    assert "`mobile/light/a.png`" in text and "`desktop/dark/b.png`" in text
    assert "1.230%" in text and "—" in text
