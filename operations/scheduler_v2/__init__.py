"""محرّكُ توليد الجدول V2 (CP-SAT) — ADR-0008.

الواجهةُ التي تعتمد عليها الجلساتُ الشقيقة (ثابتةٌ):

    from operations.scheduler_v2.model import build_model, add_soft_terms, BuiltModel, ModelOptions

  · `model.py`            نواةُ النموذج (هذه الجلسة، V2-S3a)
  · `hard_constraints.py` القيودُ الصلبةُ وفحصُ الإسناد AS-1..AS-5
  · `objective.py`        الهدفُ المرن (V2-S3b) — يستدعي `add_soft_terms`
  · `runner.py`           التشغيلُ والمهلةُ والبذرة (V2-S4)
"""
