# 고지 (NOTICE)

danburn
Copyright 2026 danburn contributors
Licensed under the Apache License, Version 2.0 (`LICENSE`).

이 파일은 danburn이 참고한 문서 형식, 쓰는 오픈소스·글꼴, 인용하는 기준 데이터의 출처를 적는다.
**§1 문구는 표시 의무다**(표시 위치는 §6).

---

## 1. 문서 형식 — 한글 문서(.hwp / .hwpx)

> **본 제품은 한글과컴퓨터의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.**

한글과컴퓨터는 HWP 바이너리 포맷과 마크업 언어(OWPML) 문서를 공개했다. 공개 문서의 이용 조건에 따라
공개 문서를 참고하여 개발한 결과물의 저작권은 개발한 개인 또는 단체에 있으며, 상업적 이용에 제한이 없다.
위 고지 문구를 제품의 사용자 인터페이스·매뉴얼·도움말·소스에 기재해야 한다.

- danburn은 한컴오피스 소프트웨어를 사용하지도 포함하지도 않는다. HWPX(ZIP + XML)를 코드로 직접 만든다.
- 기재 위치: 이 파일, `README.md` "법적 고지", 명령 도움말(`danburn build|plan --help` 의 `--notice-footer` 설명), 소스(`src/danburn/hwpx_out.py` `NOTICE`).
  생성되는 HWPX(발주처에 내는 계획서)에는 기본으로 넣지 않는다. `--notice-footer` 를 주면 모든 쪽 아래에 넣는다.
- 출처: 한컴 HWP/OWPML 공개 문서 다운로드 센터 <https://www.hancom.com/support/downloadCenter/hwpOwpml>

## 2. 표준

| 표준 | 내용 |
|---|---|
| KS X 6101 | 개방형 워드프로세서 마크업 언어(OWPML) 문서 구조 — `.hwpx` 산출물 |
| ECMA-376 / ISO/IEC 29500 | Office Open XML — `.xlsx` 입력(도급내역서) |

## 3. 오픈소스 소프트웨어

danburn은 아래 패키지를 설치 시 받아 쓴다(저장소에 소스를 포함하지 않는다). 각 라이선스 전문은 해당 배포본에 있다.

### 실행 의존성 (`pyproject.toml`)

| 소프트웨어 | 버전 | 라이선스 | 용도 |
|---|---|---|---|
| python-hwpx | 6.5.0 | Apache-2.0 | HWPX 생성·검증(`hwpx-validate`) |
| lxml | 6.x (python-hwpx 의존) | BSD-3-Clause | XML 처리 |
| openpyxl | ≥ 3.1 (확인 3.1.5) | MIT | 도급내역서 xlsx 읽기 |
| et-xmlfile | 2.0.0 (openpyxl 의존) | MIT | (openpyxl 의존) |
| PyYAML | ≥ 6 (확인 6.0.3) | MIT | 규칙·현장 정보 yaml 읽기 |
| olefile | ≥ 0.47 | BSD-3-Clause | HWP 5.x OLE 컨테이너 읽기 |
| pypdf | ≥ 5 | BSD-3-Clause | PDF 본문 추출 |

### 개발·테스트 도구 (배포물에 포함하지 않음)

| 소프트웨어 | 라이선스 | 용도 |
|---|---|---|
| pytest (+ pluggy, iniconfig, packaging, Pygments) | MIT (packaging: Apache-2.0 OR BSD-2-Clause, Pygments: BSD-2-Clause) | 테스트 |
| Pillow | MIT-CMU (HPND) | 디자인 비교 스크립트·테스트(`scripts/dev/design_diff.py`) |
| uv | Apache-2.0 OR MIT | 가상환경·설치 |
| rhwp (선택) | MIT | 개발 중 HWPX 렌더 확인 |

**Apache License 2.0** 적용 구성요소(python-hwpx, 그리고 danburn 자신):

```
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
```

새 의존성을 더하면 이 표에 이름·버전·라이선스·용도를 추가한다.

## 4. 글꼴

danburn은 **글꼴 파일을 저장소·산출물에 포함하거나 배포하지 않는다.** 산출물은 글꼴 이름만 참조하며,
실제 표시는 사용자 컴퓨터에 설치된 글꼴이 맡는다.

| 글꼴 | 권리 | 사용 방식 |
|---|---|---|
| 함초롬체(함초롬돋움·함초롬바탕) | 한글과컴퓨터. 무료 배포 | HWPX 산출물에서 이름 참조 |

## 5. 기준 데이터 출처

시험종목·시험빈도·계획횟수의 산출 근거로 다음 공개 자료를 **인용**한다.
법령·고시는 저작권법 제7조에 따라 보호받지 못하는 저작물이다. 그래도 규칙 데이터(`data/rules/*.yaml`)에는
조문 전문을 옮기지 않고 번호·항목명·요약과 쪽 번호만 적는다.
표준·시방은 **번호·명칭·개정일·해당 위치만 인용**하며 조문 전문을 싣지 않는다.

| 근거 | 출처 | 인용 범위 |
|---|---|---|
| 「건설공사 품질관리 업무지침」(국토교통부 고시, 현행 제2026-360호) 별표1·별표2 | 국토교통부 / 법제처 국가법령정보센터 | 별표2 종별·시험종목·시험방법 번호·시험빈도 요약, 별표1 작성기준의 장·절 구성 |
| 건설기술 진흥법·시행령·시행규칙 | 법제처 국가법령정보센터 | 조항 번호(예: 품질관리계획 수립 대상, KS 제품 시험 면제) |
| KCS·KDS 건설기준 | 국가건설기준센터(KCSC) | 번호·명칭 |
| LHCS 전문시방서 | 한국토지주택공사 / 국가건설기준센터 | 번호·명칭(“발주처 기준 필요” 안내에서 언급) |
| KS 한국산업표준 | 국가표준인증통합정보시스템 | 시험방법 번호(예: KS F 4004) |

- 산출물에는 근거 기준 판(고시 번호·시행일)을 함께 표시한다.
- `danburn check-basis`는 현행 고시 번호를 공개 법령 미러(GitHub `legalize-kr/admrule-kr`)의 머리말에서 읽어 비교한다.
  실행 중 조회만 하며 그 내용을 저장소에 포함하지 않는다. 결과는 알림이고, 규칙 갱신은 사람이 공식 PDF로 확인한 뒤 한다.

## 6. 표시 위치

| 위치 | 표시 |
|---|---|
| 산출물(HWPX) | 넣지 않음(사용자 결정 — `--notice-footer` 로 선택), 8.11 표에 근거 기준 판 |
| CLI 도움말 | `--notice-footer` 설명에 §1 문구 |
| README | §1 문구 + 이 파일 링크 |
| 소스 | 이 파일 유지 |

---

*최종 갱신: 2026-09-26*
