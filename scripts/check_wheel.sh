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
# 품질시험계획서 단독본(L14-G): start 산출 폴더의 project.yaml 하나로(질문 없음) 한글·엑셀·JSON.
# 수록본(품질관리계획서.json)과 단독본(품질시험계획서.json)의 8.11 행이 같아야 한다(같은 compute)
"$bin" test-plan --project "$work/run/out/project.yaml" --offline --json >"$work/run/tp.json" || fail "test-plan"
"$bin" test-plan --project "$work/run/out/project.yaml" --offline --format xlsx --out-dir "$work/run/tp2" >"$work/run/tp.txt" || fail "test-plan 결과 화면"
grep -q '^단번 품질시험계획서' "$work/run/tp.txt" && grep -q '^다음 할 일' "$work/run/tp.txt" || fail "test-plan 결과 화면 모양"
for f in 품질시험계획서.hwpx 품질시험계획서.xlsx 품질시험계획서.json; do
  [ -s "$work/run/out/$f" ] || fail "test-plan 산출 없음: $f"
done
"$work/venv/bin/hwpx-validate" "$work/run/out/품질시험계획서.hwpx" >/dev/null || fail "test-plan hwpx 스키마"
"$work/venv/bin/python" - "$work/run/out" "$work/run/tp.json" <<'PY' || fail "test-plan 행·엑셀 대조"
import json, sys
from pathlib import Path
import openpyxl
out = Path(sys.argv[1])
plan = json.loads((out / "품질관리계획서.json").read_text(encoding="utf-8"))
tp = json.loads((out / "품질시험계획서.json").read_text(encoding="utf-8"))
summary = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert plan == tp and summary["test_plan"]["rows"] == len(tp) > 0, "수록본·단독본 행이 다름"
assert summary["xlsx"] and Path(summary["xlsx"]).name == "품질시험계획서.xlsx"
wb = openpyxl.load_workbook(out / "품질시험계획서.xlsx")
assert any(n.startswith("2.시험계획-") for n in wb.sheetnames), wb.sheetnames
PY
example="$("$work/venv/bin/python" -c 'from danburn.paths import TEMPLATES_DIR; print(TEMPLATES_DIR / "project.example.yaml")')"
case "$example" in "$root"/*) fail "설치본이 저장소 파일을 가리킴: $example";; esac
"$bin" plan --boq boq.xlsx --block 나동 --project "$example" --revision 0 --date "2026. 01. 05." \
  --offline --out "$work/run/plan/품질관리계획서.hwpx" >/dev/null || fail "plan"
[ -s "$work/run/plan/품질관리계획서.hwpx" ] || fail "plan 산출 없음"
set +e; "$bin" check-basis --offline >"$work/run/basis.json"; rc=$?; set -e
[ "$rc" = 4 ] || fail "check-basis --offline 종료 ${rc}(4 기대)"
grep -q '"number": "2026-360"' "$work/run/basis.json" || fail "check-basis 가 규칙 데이터를 못 읽음"
# 기존 계획서 검사(L9, danburn check): 방금 만든 계획서를 설치본으로 읽어 기준표와 대조한다(0·3·4 중 하나, 2=못 읽음은 실패)
set +e; "$bin" check "$work/run/plan/품질관리계획서.hwpx" --offline --json >"$work/run/plan.json"; rc=$?; set -e
case "$rc" in 0|3|4) ;; *) fail "check 종료 ${rc}";; esac
grep -q '"snapshot_checked_at": "20' "$work/run/plan.json" || fail "check 가 기준표를 못 읽음"
echo "OK: 휠 설치본으로 start·test-plan·plan·check-basis·check --offline 통과 (저장소 밖 폴더)"
