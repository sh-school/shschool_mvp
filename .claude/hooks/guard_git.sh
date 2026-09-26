#!/usr/bin/env bash
# PreToolUse (Bash|PowerShell) — REP-19: يشغّل guard_git.py ببايثون يعمل فعلاً (مُشغِّلُ متجر ويندوز يخدع: python3 موجودٌ ولا يعمل).
# المدخلُ JSON على stdin يمرّ إلى الحارس كما هو. رمز 2 من الحارس يمنع الأمرَ؛ وإن لم يوجد بايثون يعمل فرمزُ 1 (خطأٌ ظاهرٌ لا يمنع).
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for py in python3 python "py -3"; do
  # shellcheck disable=SC2086
  if $py -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    exec $py "$here/guard_git.py"
  fi
done
echo "guard_git: لا بايثون 3.9+ يعمل — حارسُ الغيت غيرُ فعّالٍ في هذه الجلسة" >&2
exit 1
