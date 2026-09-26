"""레미콘 규격별 부위 추정 → 거푸집 존치 판단용 조 구성(parse_sets 형식 문자열).

도급내역서에서만 추정한다(승인 계획서 정답지를 쓰지 않는다). 결과는 사용자에게 보여 주고 커스텀할지 묻는다.
조 구성(사용자 실무 설명 09-26, LHCS 14 20 10 05:2020 3.12.5.1(4)): 수직부재만(기초·기둥·벽) → 수직+예비,
수평 강도까지(슬래브·보) → 수직+수평+예비, 거푸집 판단 없음(무근·버림·말뚝류) → 추가 없음.

추정 순서(루프 2, opus L2-T1 실자료 조사 제안을 채택):
1. 강도 ≤ 18 → 비구조 → 없음
2. 토목: section 에 흙막이·CIP·직접구매 → 없음, 옹벽 → 수직, 그 밖 → 추정 안 함(사용자 확인)
3. 건축: 지급 레미콘에는 부위가 없으므로, 같은 분야·블록의 사급 '철근…타설' 행을 슬럼프 구간(≤120mm↔S12 이하, 그 이상↔S15)으로
   짝지어 그 section 의 상부공사/기초공사 물량을 본다. 상부공사 물량이 더 많으면 수직+수평, 기초공사가 더 많으면 수직.
4. 키워드(data/member_keywords.yaml)로 품명·section 을 보는 방식은 위에서 정하지 못했을 때의 보조.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import yaml

from .model import BoqLine
from .paths import DATA_DIR

DEFAULT_KEYWORDS = DATA_DIR / "member_keywords.yaml"
_SLUMP_POUR = re.compile(r"S\s*(\d{1,2})", re.I)


def load_keywords(path: str | Path = DEFAULT_KEYWORDS) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _in_block(ln: BoqLine, block: str | None) -> bool:
    return block is None or not ln.block or block in ln.block


def _pour_bucket(ln: BoqLine) -> int | None:
    """사급 철근 콘크리트 타설 행이면 슬럼프 구간(12 또는 15), 아니면 None."""
    text = f"{ln.name} {ln.spec}"
    if "타설" not in text or "무근" in text or "철근" not in ln.name:
        return None
    m = _SLUMP_POUR.search(text)
    if not m:
        return None
    return 12 if int(m.group(1)) <= 12 else 15


def infer_members(lines: list[BoqLine], block: str | None = None, keywords: dict | None = None) -> dict[str, dict]:
    """반환: {'건축:25-24-150': {'parts': '수직+수평+예비', 'evidence': [...], 'confirm': bool}}."""
    from .boq import normalize_concrete_spec

    kw = keywords or load_keywords()
    spare = kw.get("spare_default", True)
    specs: dict[str, list[BoqLine]] = defaultdict(list)
    pours: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for ln in lines:
        if not _in_block(ln, block):
            continue
        b = _pour_bucket(ln)
        if b is not None:
            zone = "상부" if "상부공사" in ln.section else "기초" if "기초공사" in ln.section else "기타"
            pours[(ln.discipline, b)][zone] += ln.qty
            continue
        spec = normalize_concrete_spec(ln.spec)
        if spec is not None and ("레미콘" in ln.name or "콘크리트" in ln.name):
            specs[f"{ln.discipline}:{spec}"].append(ln)
    out: dict[str, dict] = {}
    for key, lns in sorted(specs.items()):
        disc, spec = key.split(":", 1)
        strength, slump = int(spec.split("-")[1]), int(spec.split("-")[2])
        text = " ".join(f"{ln.section} {ln.name}" for ln in lns).replace(" ", "")
        parts: list[str] | None = None
        ev: list[str] = []
        if strength <= 18:
            parts, ev = [], [f"강도 {strength} ≤ 18 — 비구조"]
        elif disc == "토목":
            if any(w in text for w in ("흙막이", "CIP", "직접구매")):
                parts, ev = [], ["토목 흙막이·CIP"]
            elif "옹벽" in text:
                parts, ev = ["수직"], ["토목 옹벽"]
        else:
            zones = pours.get((disc, 12 if slump <= 120 else 15), {})
            if zones:
                ev = [f"S{12 if slump <= 120 else 15} 철근 타설: " + ", ".join(f"{z} {q:,.0f}" for z, q in zones.items())]
                up, base = zones.get("상부", 0.0), zones.get("기초", 0.0)
                # 물량이 많은 쪽으로 판정(상부 1㎥ 같은 잡음에 흔들리지 않게 — 루프 2 실자료에서 발견)
                parts = ["수직", "수평"] if up and up >= base else ["수직"] if base else None
        if parts is None:   # 보조: 키워드
            hits = {p for p, words in (("수직", kw["vertical"]), ("수평", kw["horizontal"])) if any(w in text for w in words)}
            if hits:
                parts = ["수직", "수평"] if "수평" in hits else ["수직"]
                ev.append("키워드: " + "·".join(sorted(hits)))
        confirm = parts is None
        parts = parts or []
        if parts and spare:
            parts = parts + ["예비"]
        out[key] = {"parts": "+".join(parts), "evidence": ev or ["단서 없음 — 사용자 확인"], "confirm": confirm}
    return out


def to_formwork_arg(inferred: dict[str, dict]) -> str:
    """추정 결과를 --formwork-sets 문자열로(부위 없음은 뺀다)."""
    return ",".join(f"{k}={v['parts']}" for k, v in inferred.items() if v["parts"])
