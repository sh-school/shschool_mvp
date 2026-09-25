"""مساعداتٌ مشتركةٌ بين وحدات نماذج operations — تشير إليها الهجرات (`operations.models._uuid`)."""

import uuid


def _uuid():
    return uuid.uuid4()
