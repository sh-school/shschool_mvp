"""
core/audit_repr.py — وصفٌ لسجلّ التدقيق بلا اسمٍ شخصيّ (W-20261003-019).

سجلُّ التدقيق ملحقٌ لا يُعدَّل، فما يُكتب فيه من أسماءٍ يبقى بعد محو صاحبه. والمدقّقُ لا يحتاج
الاسم: يكفيه نوعُ الكائن ومعرّفُه. فكلُّ كاتبٍ في `AuditLog.object_repr` يمرّ من هنا بدل
`str(instance)` الذي قد يعرض الاسمَ (CustomUser.__str__ يُرجعه كاملاً).
"""

from typing import Any


def masked_repr(instance: Any) -> str:
    """«النموذج + بداية المعرّف» — مثال: `CustomUser 3f2a91bc`."""
    return f"{instance._meta.object_name} {str(instance.pk)[:8]}"
