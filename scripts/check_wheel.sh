#!/usr/bin/env bash
# 설치본 검사(L8-P1): 휠을 만들어 새 가상환경에 설치하고, 저장소 밖 폴더에서 명령이 끝까지 도는지 본다.
# 휠에 기준 데이터(src/danburn/data)가 빠지면 여기서 FileNotFoundError 로 실패한다.
# 사용: scripts/check_wheel.sh   (uv 필요. 합성 예제 내역서만 쓴다)
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/danburn-wheel.XXXXXX")"
trap 'rm -rf "$work"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# 1. 휠 만들기 + 데이터 들어갔는지
uv build --wheel --out-dir "$work/dist" "$root" >/dev/null 2>&1 || fail "uv build"
whl="$(ls "$work"/dist/danburn-*.whl)"
want=$(find "$root/src/danburn/data" -type f -name '*.yaml' | wc -l | tr -d ' ')
got=$(unzip -l "$whl" | grep -c 'danburn/data/.*\.yaml' || true)
[ "$want" = "$got" ] || fail "휠의 데이터 파일 ${got} / 저장소 ${want}"
echo "wheel: $(basename "$whl") — data yaml ${got}개"

# 2. 새 가상환경에 설치(저장소를 가리키지 않음)
uv venv -q --python 3.12 "$work/venv" || fail "uv venv"
uv pip install -q --python "$work/venv/bin/python" "$whl" || fail "uv pip install"
bin="$work/venv/bin/danburn"
[ -x "$bin" ] || fail "danburn 명령 없음"

# 3. 저장소 밖 폴더에서 실행
mkdir -p "$work/run" && cd "$work/run"
"$work/venv/bin/python" "$root/scripts/make_example_boq.py" --out "$work/run/boq.xlsx" >/dev/null || fail "합성 내역서"
cat > answers.yaml <<EOF
내역서: $work/run/boq.xlsx
블록: 나동
발주자_구분: 민간
발주자: 합성개발
공사종류: 건축
총공사비_억원: 850
연면적: 42000
지상층수: 22
건설사업관리_대상: 아니오
공사명: 합성 예시 공동주택
시공자: 합성건설
현장대리인: 합성 갑
품질관리자: 합성 을
EOF
export DANBURN_HOME="$work/home"
"$bin" --help >/dev/null || fail "--help"
"$bin" start --answers answers.yaml --yes --offline --out-dir "$work/run/out" >/dev/null || fail "start --answers"
for f in 품질관리계획서.hwpx 품질관리계획서.json 요약.json project.yaml; do
  [ -s "$work/run/out/$f" ] || fail "start 산출 없음: $f"
done
example="$("$work/venv/bin/python" -c 'from danburn.paths import TEMPLATES_DIR; print(TEMPLATES_DIR / "project.example.yaml")')"
case "$example" in "$root"/*) fail "설치본이 저장소 파일을 가리킴: $example";; esac
"$bin" plan --boq boq.xlsx --block 나동 --project "$example" --revision 0 --date "2026. 01. 05." \
  --offline --out "$work/run/plan/품질관리계획서.hwpx" >/dev/null || fail "plan"
[ -s "$work/run/plan/품질관리계획서.hwpx" ] || fail "plan 산출 없음"
set +e; "$bin" check-basis --offline >"$work/run/basis.json"; rc=$?; set -e
[ "$rc" = 4 ] || fail "check-basis --offline 종료 ${rc}(4 기대)"
grep -q '"number": "2026-360"' "$work/run/basis.json" || fail "check-basis 가 규칙 데이터를 못 읽음"
echo "OK: 휠 설치본으로 start·plan·check-basis --offline 통과 (저장소 밖 폴더)"
