"""خدماتُ مركز القيادة — الطبقةُ التي يستدعيها العرضُ (المنطقُ في `refresh` و`collectors`).

العرضُ يستقبل ويردّ (سقّاطةُ الطبقات): فلا يبلغ دوالَّ الجمع بنفسه بل يمرّ من هنا.
"""

from command_center.refresh import ensure_fresh

__all__ = ["ensure_fresh"]
