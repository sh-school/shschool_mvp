# فحصٌ محلّيٌّ مطابقٌ لـCI (W-20261003-008)

الأمرُ الواحد من جذر أيّ شجرة:

    bash scripts/ci_parity.sh        # أو: make ci-parity

يشغّل `docker-compose.check.yml`: حاويةُ المشروع (صورة `shschool_mvp-web`) + postgres 16 على tmpfs تُعاد فارغةً بكلّ تشغيل، ثمّ يثبّت أدواتِ البوّابة بإصداراتها
(`requirements-mypy.txt` وruff 0.4.4 وradon 6.0.1) ويشغّل `ruff format --check` ثمّ `scripts/quality_numbers.py --strict` (mypy ratchet وruff وradon، ويخرج 1 إن زاد رقمٌ).
فحوصُ git (detect-secrets وحرّاس الهويّة وتصادم الهجرات) لا تعمل داخل شجرة عملٍ مربوطة، فتبقى `make prepush` على المضيف وتُطبع «غير مقيس هنا».

آخرُ سطرٍ يطبعه: `أرقام الجودة: mypy=… · ruff=… · CC≥31=…` — وهو السطرُ نفسُه الذي تطبعه وظيفةُ mypy في CI (خطوة «أرقام الجودة في سطر واحد»)، فتُقارَن الأرقامُ حرفيّاً.
ما تعذّر قياسُه يُطبع «غير مقيس» (لا Docker ⇒ خروج 3). الفروقُ المعلومة: الحاويةُ Debian لا Ubuntu، ولا توازيَ شظايا.
