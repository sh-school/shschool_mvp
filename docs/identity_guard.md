# حارسُ الهويّة قبل الدفع — `identity_ack` (W-20261011-002، D-376م)

الغرضُ: ألّا يُعتمد رأسٌ للواجهة قبل أن تُشغَّل عليه حرّاسُ الهويّة الثلاثة، وألّا يُكتشف سقوطُها بعد دورة CI كاملة.

## ما يجري

1. `python scripts/prepush_check.py` (أو `make prepush`) يحسب الفرقَ مقابل `merge-base` مع `origin/main`.
2. إن مسّ الفرقُ `templates/` أو `static/` شغّل الحرّاسَ: `tests/test_dead_classes.py` و`tests/test_design_ratchet.py`
   و`tests/test_tailwind_freeze.py`. وهي نصّيّةٌ بلا قاعدةٍ ولا خادم.
3. السقوطُ يمنع (رمز الخروج 1). والنجاحُ لا يغيّر رمزَ الخروج.
4. آخرُ سطرٍ في المخرَج: `identity_ack: <رأس8> نجح` أو `identity_ack: <رأس8> سقط`.
5. إيداعٌ لا يمسّ الواجهة: تُتخطّى الخطوةُ ولا يُطبع إيصال.

## ما ليس هنا

- ربطُ `approval_check` بالإيصال وتسجيلُ الرأس في `identity_ack.py`: عند 0701 و0103.
- تغييرُ الحرّاس نفسها: تبقى في `tests/` كما هي.

انظر أيضاً: `docs/governance/regression_guards.md` (حرّاسُ الهويّة في `make prepush`).
