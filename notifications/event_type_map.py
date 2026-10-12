"""خريطةُ نوع حدث الـHub إلى النوع المخزَّن في `InAppNotification.event_type`.

انتقلت من `hub.py` (W-20261010-042) لأنّه بلغ سقفَ الحجم؛ السلوكُ كما كان حرفاً: ما ليس في الجدول يُخزَّن `general`.
"""

HUB_TO_STORED_EVENT = {
    "behavior_l1": "behavior",
    "behavior_l2": "behavior",
    "behavior_l3": "behavior",
    "behavior_l4": "behavior",
    "behavior_risk": "behavior",
    "behavior_digest": "behavior",
    "absence": "absence",
    "class_exit": "general",
    "grade": "grade",
    "fail": "fail",
    "clinic": "clinic",
    "sent_home": "sent_home",
    "meeting": "meeting",
    "parent_summon": "parent_summon",
    "plan_update": "plan_update",
    "plan_deadline": "plan_deadline",
    "plan_overdue": "plan_overdue",
    "review_cycle": "review_cycle",
    "observation": "general",
    "appraisal_grievance": "general",
    "teacher_cover": "general",
    "exit_not_returned": "exit_not_returned",
    "session_unmarked": "session_unmarked",
    "general": "general",
}
