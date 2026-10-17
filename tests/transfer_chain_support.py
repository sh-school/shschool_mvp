"""مساعدُ اختبارات سلسلة نموذج 07: يقطع المراحلَ بالوحدة نفسِها لا بكتابة الأعمدة (W-20261001-018)."""

from student_affairs.transfer_chain import REQUIRED_DOCUMENTS, apply_chain_action

ALL_DOCS = [key for key, _ in REQUIRED_DOCUMENTS]
ORDER = ["review", "approved", "place", "enter"]


def advance(transfer, actor, upto: str):
    """ينفّذ مراحلَ السلسلة بترتيبها حتى `upto` شاملةً (review/approved/place/enter)."""
    for step in ORDER[: ORDER.index(upto) + 1]:
        apply_chain_action(transfer, step, "", actor, documents=ALL_DOCS)
    return transfer


def run_full_chain(transfer, actor):
    """السلسلةُ كاملةً ثمّ الإتمام."""
    advance(transfer, actor, "enter")
    apply_chain_action(transfer, "completed", "", actor)
    return transfer
