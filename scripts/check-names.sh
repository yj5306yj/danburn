#!/usr/bin/env bash
# 추적·새 파일(무시 대상 제외)에 실제 현장·시공사·개인 식별어가 없는지 검사한다.
# 식별어 목록은 로컬 전용 _private/blocklist.txt (한 줄에 하나). 목록이 없으면 실패.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"; cd "$root"
list="_private/blocklist.txt"
[ -s "$list" ] || { echo "FAIL: $list 없음(로컬 전용 식별어 목록 필요)"; exit 2; }
hits=0
while IFS= read -r w; do
  [ -z "$w" ] && continue
  out="$(git grep --untracked -n -I -F -- "$w" -- . ':!.gitignore' 2>/dev/null)"
  if [ -n "$out" ]; then hits=$((hits+1)); printf 'HIT %s\n%s\n' "$w" "$(printf '%s\n' "$out" | head -5)"; fi
done < "$list"
# 비밀 키 모양 검사(공개 저장소): 법제처 OC(공개 예시 OC=test 제외)·공공데이터 serviceKey·GitHub·Anthropic·OpenAI·AWS·Slack 토큰·개인키
secret_re='(OC=[A-Za-z0-9_]{2,}|serviceKey=[A-Za-z0-9%+/=]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|xox[bpa]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
sec="$(git grep --untracked -n -I -E -- "$secret_re" -- . ':!.gitignore' ':!scripts/check-names.sh' 2>/dev/null | grep -v 'OC=test' )"
if [ -n "$sec" ]; then hits=$((hits+1)); printf 'SECRET-LIKE\n%s\n' "$(printf '%s\n' "$sec" | head -5)"; fi
[ $hits -eq 0 ] && echo "check-names: 0 hits" || { echo "check-names: $hits words found"; exit 1; }
