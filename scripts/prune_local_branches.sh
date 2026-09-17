#!/bin/bash
# scripts/prune_local_branches.sh — فروعٌ محلّيّةٌ محتواها في main فعلاً، ولو باسمٍ آخر.
#
# `delete_branch_on_merge` مفعَّلةٌ على المستودع فعلاً — GitHub يحذف فرع طلب
# الدمج نفسه تلقائيّاً. لكنّ هذا لا يغني عن شيء حين يُنشأ فرعٌ محلّيّاً، ثمّ
# يُعاد العمل نفسه (أو الفرعُ نفسه بدفعةٍ إلى اسمٍ آخر) ويُدمج تحت اسمٍ مختلف:
# الأصليُّ يبقى محلّيّاً إلى الأبد، لأنّ GitHub لا يعرف عنه شيئاً أصلاً.
#
# وهذا وقع بالفعل: أحد عشر فرعاً محلّيّاً اكتُشفت 2026-09-17 محتواها حرفٌ
# بحرفٍ في main عبر فروعٍ أخرى — راجع project_swot_git_push.
#
# الفحصُ هنا يطابق ما فعلناه يدويّاً: فرعٌ صفرُ الفرق عن نقطة تفرّعه آمنٌ فوراً،
# وفرعٌ له فرقٌ لكنّ كلَّ ملفٍّ لمسه **يطابق حرفيّاً** ما في main الآن (ولو عبر
# تاريخٍ مختلف تماماً) آمنٌ أيضاً — الباقي يحتاج عيناً بشريّة.
#
# الاستخدام:
#   scripts/prune_local_branches.sh          # عرضٌ فقط، لا حذف
#   scripts/prune_local_branches.sh --apply  # يحذف ما صُنِّف "آمن" فقط
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

MAIN="${MAIN_BRANCH:-main}"
checked_out=$(git worktree list --porcelain | awk '/^branch /{print $2}' | sed 's#refs/heads/##')

safe=()
review=()

for branch in $(git for-each-ref --format='%(refname:short)' refs/heads/); do
  [ "$branch" = "$MAIN" ] && continue
  grep -qxF "$branch" <<<"$checked_out" && continue  # شجرةُ عملٍ نشطة — لا تُمسّ

  base=$(git merge-base "$MAIN" "$branch")
  if git merge-base --is-ancestor "$branch" "$MAIN"; then
    safe+=("$branch  — مندمجٌ فعلاً (سلفٌ لِـ $MAIN)")
    continue
  fi

  # طابور الدمج يدمج بسحقٍ (squash) — فرعُ طلبٍ مدموجٍ لا يصير سلفاً لِـ main
  # أبداً مهما نجح، ويشيخ محتواه عن main بعدها بلا أن يعني ذلك شيئاً. حالة
  # GitHub («مدموج») أوثق من مقارنة الملفّات هنا.
  if command -v gh >/dev/null 2>&1; then
    merged=$(gh pr list --head "$branch" --state merged --json number --jq 'length' 2>/dev/null || echo 0)
    if [ "$merged" -gt 0 ]; then
      safe+=("$branch  — طلبُ دمجه على GitHub مدموجٌ فعلاً (سحق)")
      continue
    fi
  fi

  files=$(git diff --name-only "$base" "$branch" -- .)
  if [ -z "$files" ]; then
    safe+=("$branch  — صفرُ فرقٍ عن نقطة تفرّعه")
    continue
  fi

  all_match=1
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    git diff --quiet "$MAIN" "$branch" -- "$f" 2>/dev/null || { all_match=0; break; }
  done <<<"$files"

  if [ "$all_match" = 1 ]; then
    safe+=("$branch  — كلُّ ملفٍّ لمسه يطابق main الآن حرفيّاً")
  else
    review+=("$branch  — يختلف عن main فعليّاً في: $(echo "$files" | tr '\n' ' ')")
  fi
done

echo "── آمنةٌ للحذف (${#safe[@]}) ──"
printf '  %s\n' "${safe[@]}"
echo
echo "── تحتاج مراجعةً بشريّة (${#review[@]}) ──"
printf '  %s\n' "${review[@]}"

if [ "$APPLY" = 1 ] && [ "${#safe[@]}" -gt 0 ]; then
  echo
  echo "── حذفٌ آمن ──"
  for entry in "${safe[@]}"; do
    branch="${entry%%  *}"
    git branch -D "$branch"
  done
fi
