"""엔진 단계 사이의 공용 자료형. 워커들은 이 계약에 맞춰 입력·출력을 만든다.

흐름: 도급내역서 → BoqLine(원행) → MaterialQty(자재·규격별 합계) → Rule 적용 → PlanRow(8.11 한 행)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoqLine:
    """도급내역서의 한 행(정규화 전 원값 보존)."""
    discipline: str        # "건축" | "토목" | "기계"
    sheet: str             # 원본 시트 이름 (예: "지급(건)")
    row: int               # 원본 행 번호(1부터)
    name: str              # 품명
    spec: str              # 규격(원문)
    unit: str              # 단위(원문)
    qty: float             # 수량
    block: str             # 블록·공구 열 이름 (단일 열이면 "")
    supply: str            # "지급" | "사급" | "품질관리비"
    section: str = ""      # 이 행이 속한 공종·부위 머리 경로(예: "아파트 > 골조공사 > 기초"). 부위 추정용


@dataclass(frozen=True)
class MaterialQty:
    """자재·규격별 합계 — 규칙 매칭과 계산의 입력."""
    material: str          # 규칙 키 (예: "ready_mixed_concrete", "rebar")
    spec: str              # 정규화 규격 (예: 레미콘 "25-24-150", 철근 "SD400 D13")
    unit: str              # 정규화 단위 ("m3", "ton", "m2", "ea" ...)
    qty: float
    block: str
    discipline: str
    sources: tuple[tuple[str, int], ...] = ()   # (시트, 행) 추적
    from_install: bool = False                   # 자재 행 없이 시공 행(설치·깔기 등)에서 추정한 물량
    work: str = ""                               # 내역서 구분(section)에서 뽑은 공종(수량 가중 다수결). 없으면 ""


@dataclass(frozen=True)
class Frequency:
    """시험빈도. per_qty 단위 물량마다 1회. per_qty 가 None 이면 문구형(예: 공급원별 1회)."""
    per_qty: float | None
    unit: str | None
    text: str              # 계획서에 적을 빈도 문구 (예: "120㎥마다")
    minimum: int = 1       # 물량이 있으면 최소 횟수
    lot: bool = False      # True면 per_qty 는 '로트' 크기. 계획횟수 = 로트 수 × 로트당 조 수
    default_sets: int | None = None   # 로트당 기본 조 수(기준+관행). 거푸집 해체용 조는 따로 더한다
    sets_basis: str = ""   # 기본 조 수의 근거


@dataclass(frozen=True)
class TestRule:
    test_type: str         # 시험종류 (예: "슬럼프", "압축강도")
    method: str            # 시험방법 (예: "KS F 2402")
    frequency: Frequency
    basis: str             # 근거 (예: "건설공사 품질관리 업무지침 별표2 …")
    where: str = "현장"    # 계획횟수 칸: "현장" | "외부" | "KS"
    conditions: str = ""   # 원문 조건 요약·해석 필요 표시
    optional: bool = False # 조건부 시험(예: 콘크리트포장에 한함) — 기본 산출에서 빼고 목록으로 알린다
    display: str = ""      # 계획서에 적는 실무 이름(예: 슬럼프). 비면 test_type
    # KS 인증 제품일 때 이 종목의 처리(발주처 시험기준 비고 — 예: LHCS 10 40 00 V2026.04 부록4). 비면 지금 동작(규칙 ks_count).
    ks_substitute: str = ""   # "certificate" = KS 인증업체가 공인기관에 의뢰한 시험성적서 확인으로 갈음(계획 0회, 비고 '성적서대체')
    ks_still_test: bool = False  # True = KS 인증 제품이어도 이 종목은 시험한다(면제·갈음 안 됨)
    eco_substitute: bool = False # True = 친환경 항목(TVOC·폼알데하이드·톨루엔 등) — 공인기관 성적서·환경표지인증서를 내면 시험 면제(LHCS 10 40 00 1.5.1(9))
    ks_substitute_below: int | None = None  # KS 제품이고 규격 수량이 이 값 미만이면 성적서로 갈음, 이상이면 시험(LHCS 하수도용 관 "소량 10개 미만")


@dataclass(frozen=True)
class Rule:
    material: str
    label: str             # 계획서 시험항목 머리 (예: "레미콘")
    tests: tuple[TestRule, ...]
    basis_version: str     # 기준 판 (예: "국토교통부고시 제2022-30호")
    match_names: tuple[str, ...] = ()   # 도급내역서 품명에 들어가면 이 자재로 본다 (YAML match.names)
    match_units: tuple[str, ...] = ()   # 정규화 단위 제한 (YAML match.units, 비면 제한 없음)
    match_exclude: tuple[str, ...] = () # 품명에 들어 있으면 이 자재가 아님(예: 철근 가공·조립 노무 행) (YAML match.exclude)
    match_names_generic: tuple[str, ...] = ()  # 품명에 이 말이 있고 규격에 spec_names 가 있으면 이 자재(예: 거푸집 + 합판) (YAML match.names_generic)
    match_spec_names: tuple[str, ...] = ()     # names_generic 과 짝으로 규격 칸에서 찾는 말 (YAML match.spec_names)
    ks_mark: bool = False  # KS 인증 자재면 계획횟수 KS 칸에 ◎ (사용자 확인 09-26)
    order: int = 50        # 8.11 표에서 자재 순서(작을수록 위)
    index_keys: tuple[str, ...] = ()    # 별표2 색인(data/byeolpyo2_index.yaml) 종별 key — 색인 대조·동의어 연결
    unit_factors: tuple[tuple[str, str, float], ...] = ()  # (내역 단위, 환산 단위, 곱) 예: ("천매","ea",1000), ("포","ton",0.04)
    extra_keys: tuple[str, ...] = ()    # data/extra_catalog.yaml 항목 중 이 규칙이 다루는 것(“발주처 기준 필요” 경고에서 뺀다)
    accept_install_rows: bool = False   # 자재 행이 없고 시공 행(“…설치”)만 있으면 그 물량으로 받는다(비고 “시공 행 추정”)
    install_units: tuple[str, ...] = () # 시공 행에서만 허용할 추가 단위(예: 개소)
    owner: str = ""                     # 발주처 전용 규칙(예: "LH" — LHCS 10 40 00 부록). 비면 모든 현장(별표2)
    makers_label: str = "제조회사"        # 묶음 행 산출근거의 주체 이름(예: 골재원, 공급원)
    warn_if_missing: bool = False       # 입력에 0행이면 경고할 핵심 자재(레미콘·철근)
    ks_count: str = "makers"            # 묶음 행 KS 제품: "makers"=제조사 수×1회(철근 관행), "none"=시험 없이 ◎만(시행령 91조 면제)
    group_tests: bool = False           # True면 시험들을 규격당 한 행으로 묶어 출력 (YAML group_tests)
    group_frequency: str = ""           # 묶음 행 빈도 문구 (YAML group.frequency, KS/비KS 두 줄)
    group_basis: str = ""               # 묶음 행 근거 (YAML group.basis)
    spec_group: str = ""                # 규격 묶음: ""=규격별(기본) | "all"=한 행 | "pattern"=정규식 그룹별 (YAML spec_group, L4-D2)
    spec_group_pattern: str = ""        # pattern 모드 정규식(규격 먼저, 없으면 품명에서 찾는다)
    spec_group_label: str = ""          # 묶은 행 규격 표시. pattern 모드는 {1}{2}… 로 그룹을 넣는다
    spec_group_other: str = ""          # pattern 모드에서 규격·품명 모두 안 맞을 때 표시(기본 '기타')
    work: str = ""                      # 8.11 공종 칸 기본값(YAML work). 내역서 구분에서 공종을 못 찾을 때만 쓴다


@dataclass
class PlanRow:
    """8.11 표 한 행."""
    discipline: str
    work: str              # 공종
    item: str              # 시험항목(자재·규격)
    test_type: str
    qty: float
    unit: str
    frequency: str
    calc_basis: str        # 산출근거 (예: "1,000㎥/120㎥")
    count_site: int = 0
    count_external: int = 0
    count_ks: str = ""
    note: str = ""
    basis: str = ""
    detail: str = ""       # 비고에 다 못 적는 설명(조 구성·생략 가능 근거 등). JSON·요약에만
    material: str = ""     # 규칙 키 (채점 짝 맞추기용)
    spec: str = ""         # 정규화 규격
    sources: list[tuple[str, int]] = field(default_factory=list)
    method: str = ""       # 시험방법(예: "KS F 2402"). 규칙 TestRule.method 에서 채운다
