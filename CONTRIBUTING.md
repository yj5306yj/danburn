# 기여 안내

danburn에 가장 도움이 되는 기여는 **자재 규칙 추가**와 **읽지 못하는 내역서 양식 제보(합성 자료로)**입니다.

## 개발 환경

맥·리눅스(bash·zsh):

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q                  # 전체 테스트(네트워크 없이)
DANBURN_NETWORK=1 .venv/bin/python -m pytest -q -m network   # 공개 법령 조회 테스트(선택)
scripts/check_wheel.sh                         # 설치본 검사: 휠 → 새 가상환경 → 저장소 밖에서 start·plan·check-basis(데이터 파일을 옮기거나 더하면)
```

Windows(PowerShell — 명령을 한 줄씩 실행합니다. PowerShell 5.1은 `&&`를 받지 않습니다):

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
$env:DANBURN_NETWORK = "1"; .venv\Scripts\python.exe -m pytest -q -m network; Remove-Item Env:DANBURN_NETWORK
```

`scripts/check_wheel.sh`는 bash 스크립트라 Windows에서는 Git Bash 등에서 실행합니다.

**선택 도구와 건너뜀.** `pillow`와 Poppler(`pdftoppm`·`pdftotext`)는 개발용 디자인 대조 검사(`scripts/dev/design_diff.py`)에만 씁니다. 없으면 테스트는 멈추지 않고 그 검사만 이유를 보이며 건너뜁니다(`pytest -rs`로 이유 확인). HWPX 스키마 검사기 `hwpx-validate`(Windows는 `hwpx-validate.exe`)는 런타임 의존성 python-hwpx에 들어 있어 따로 설치하지 않습니다 — 찾지 못하면 건너뛰지 않고 실패합니다.

파일은 UTF-8, LF 줄바꿈입니다. Windows 결과는 아직 부분 검증입니다 — 결과를 알려 주시면 도움이 됩니다.

## 자재 규칙 추가

규칙은 `src/danburn/data/rules/<material>.yaml` 한 파일이 한 자재입니다. 별표2 기반 규칙은 항상 적용되고, 발주처 전용 규칙(예: `lh_*.yaml`)은 `--owner`로 켤 때만 적용됩니다(`docs/rules-authoring.md` 참고). **파일을 추가하면 자동 등록**됩니다. 자세한 형식은 [`docs/rules-authoring.md`](docs/rules-authoring.md)를 따르고, 요점은 다음과 같습니다.

1. **출처는 별표2 원문만.** 시험종목·시험방법·시험빈도는 「건설공사 품질관리 업무지침」 별표2 원문에서 가져오고 `basis`에 항목과 쪽 번호를 적습니다. 조문 전문은 옮기지 않습니다(번호·항목명·요약만). 실무 관행은 `basis`를 `"실무 관행 — …"`으로 시작해 구분합니다.
2. **색인과 연결.** `index_keys`에 `src/danburn/data/byeolpyo2_index.yaml`의 종별 key를 적으면 그 동의어로 내역서 행을 찾습니다. 필요하면 `match`(품명·단위·제외어)와 `unit_factors`(단위 환산)를 씁니다.
3. **시험 빠짐없이.** 그 종별의 별표2 시험종목을 모두 `tests`에 적습니다. KS 제품 면제면 `ks_mark: true`, `ks_count: none`.
4. **테스트.** 합성 내역 행(색인 동의어 품명 + 올바른 단위)이 규칙에 잡혀 8.11 행이 나오는지, KS 면제·물량 빈도 계산이 맞는지 `tests/rules/`에 테스트를 추가합니다.

별표2에 없는 자재는 규칙 대신 `src/danburn/data/extra_catalog.yaml`에 일반 명칭을 더합니다. 내역서에서 찾으면 “발주처 기준 필요”로 표시됩니다.

## 올리기 전에 확인

- [ ] `.venv/bin/python -m pytest -q`(Windows `.venv\Scripts\python.exe -m pytest -q`) 전체 통과
- [ ] 새 의존성이 있으면 `NOTICE.md` 표에 추가
- [ ] **식별어 검사**: 실제 현장명·시공사·사람 이름이 없는지. 저장소의 `scripts/check-names.sh`는 로컬 전용 목록 `_private/blocklist.txt`(한 줄에 한 단어, git 무시)를 읽어 추적·새 파일을 검사합니다. 내가 다룬 실자료의 식별어로 목록을 만들고 `scripts/check-names.sh`가 `0 hits`인지 확인하세요.

## 금지 — 공개 저장소 안전

- **실자료 금지.** 실제 도급내역서·계획서·현장명·블록명·시공사·발주처 담당자·개인정보·회사 이메일, 그리고 **실제 현장 자료의 수량·횟수**를 넣지 않습니다. 테스트·예시는 합성 자료로 만듭니다(`src/danburn/data/templates/project.example.yaml` 참고).
- **타사 문서 복제 금지.** 다른 회사 계획서의 문장·승인본 수치를 옮기지 않습니다. 규칙은 법령·고시 원문에서 도출합니다.
- **표준 전문 금지.** KS·KCS·LHCS 조문 전문을 싣지 않습니다.
- **파일 금지.** 글꼴 파일, 한컴 소프트웨어, 실물 양식(hwp·hwpx·pdf·xlsx·zip), 회사 로고를 넣지 않습니다.
- **오피스 프로그램 금지.** 산출물 생성에 LibreOffice·UNO·한컴을 쓰지 않습니다. 파일 형식은 코드로 직접 만듭니다.
- `_private/`(로컬 실자료)와 `.cache/`의 내용은 커밋하지 않습니다.

## 라이선스

기여한 내용은 이 저장소의 [Apache License 2.0](LICENSE)으로 배포됩니다.
