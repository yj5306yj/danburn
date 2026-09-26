# 예제 — 합성 도급내역서로 먼저 돌려 보기

내 도급내역서 없이 `danburn`을 시험해 보는 예제입니다. 예제 내역서는 **완전 합성**입니다(실제 현장·회사·수량과 무관). 실제 도급내역서의 모양만 흉내 냅니다.

- 시트: `지급(건)`·`지급(토)`(지급자재 레미콘), `내역(건)`·`내역(토)`·`내역(기)`(사급 내역), 읽지 않는 `원가계산서`
- 머리 두 줄: 블록 열 `가동`·`나동`·`합 계` 아래 `수량`·`금액`
- 1열 표시: `목차`·`구분`(번호 제목 `1-1. 아파트 > 1-1 01. 상부공사 > 1-1 0101. 철근콘크리트공사`)·`소계` 행
- 자재: 레미콘 여러 규격, 철근(`이형봉강(SD500)`·`H-13`·TON), 벽돌·블록·시멘트·건조 모르타르, 방수·단열·유리·창호(부호 `WW1` 등), 타일·도료·석고보드, 아스콘·경계블록·보도블록·흄관·부직포·터파기·되메우기, PVC관(지름별), 보온재, 시공 행(`PVC지수판 설치`), 노무 행(`철근 가공조립`·`벽돌 쌓기`·`보통인부`), 별표2 밖 자재(`실링재`·`주방가구`)

## 실행

저장소 폴더에서(설치는 루트 [`README.md`](../README.md)의 “처음 한 번 준비 3단계”, Windows는 `.venv/bin/` 대신 `.venv\Scripts\`):

```bash
.venv/bin/python scripts/make_example_boq.py                 # → examples/out/example_boq.xlsx
.venv/bin/danburn inspect --boq examples/out/example_boq.xlsx
.venv/bin/danburn plan --boq examples/out/example_boq.xlsx --block 나동 \
  --project data/templates/project.example.yaml --revision 0 --date "2026. 01. 05." \
  --offline --out examples/out/품질관리계획서.hwpx
.venv/bin/hwpx-validate examples/out/품질관리계획서.hwpx
```

`--date`는 `project.example.yaml`의 제정일자(Rev.0)와 같아야 합니다(다르면 개정 모순으로 멈춤). `examples/out/`의 파일은 매번 다시 만드는 산출물이라 커밋하지 않습니다.

## 기대 결과 (대략)

- `inspect`: `supported: true`, 블록 `가동`·`나동` 각 50행, `원가계산서`는 건너뜀.
- `plan`(나동): 종료 0, 내역 50행 → 규격 묶음 약 40개 → 8.11 행 약 90행(규칙이 늘면 달라짐). `hwpx-validate` 통과.
- 계획서는 약 140쪽: 표지·목차·개정이력, 1~10장 33절마다 개요 칸·업무 분장표·업무 흐름표, 부표, 기록 양식 42종(8.11 품질검사 실시대장은 가로 쪽), 5.2 조직도, 8.11 품질시험계획표.
- 8.11에 레미콘(건축·토목 규격별)·철근(SD500 D13·D16, SD400 D10)·조적·방수·단열·유리·창호·타일·도장·토공·포장·PVC관 등이 나옵니다. `PVC지수판 설치`는 자재 행이 없어 시공 행으로 받아 비고에 `시공 행 추정`.
- 요약의 확인할 항목:
  - `warnings`: `발주처 기준 필요 — 시험계획 미작성: 건축용 실링재`, `… 수납·주방·욕실 가구` (계획서 8.11 뒤 ‘시험계획 미작성 자재’ 표에도 실림)
  - `missing_common_specs`: 흔한 철근 규격(SD400 D13·D16) 누락 추정 → 필요하면 `--add-spec`
  - `member_inferred`: 레미콘 부위 단서가 없어 `confirm: true`(사용자 확인) → 필요하면 `--formwork-sets`
  - `site_measurements_to_confirm`: 실내공기질·바닥충격음 측정을 넣을지 확인

요약의 항목 이름 뜻은 루트 README의 “용어 풀이”에 있습니다. 결과는 초안입니다. 한글(또는 한글 Viewer)에서 열어 모양을 확인해 보세요(확인 목록은 루트 README “한컴에서 확인하기”).

내 현장으로 돌릴 때는 `project.example.yaml`을 복사해 값만 고친 현장 정보 파일을 `--project`로 줍니다(루트 README “현장 정보 파일 만들기”).
