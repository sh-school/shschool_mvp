"""مساعداتٌ مشتركةٌ بين وحدات نماذج quality — تشير إليها الهجرات (`quality.models._uuid`)."""

import uuid


def _uuid():
    return uuid.uuid4()
