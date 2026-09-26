"""규칙 적용: BoqLine → MaterialQty(자재·규격별 합계) → PlanRow(8.11 행).

계산은 결정론적이다. 물량 비례 빈도는 올림(물량 ÷ 빈도물량)으로 횟수를 낸다.
물량 비례가 아닌 빈도(공급원별·필요시 등)는 최소 횟수만 넣고 산출근거에 원문 빈도를 적는다.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
from collections import defaultdict

from .model import BoqLine, MaterialQty, PlanRow, Rule
from .paths import DATA_DIR

SMALL_CONCRETE_M3 = 40   # LHCS 14 20 10 05:2020 3.12.5.1(5): 전체 사용량 40㎥ 미만이면 강도시험 생략 가능(감독자 판단)
UNIT_LABEL = {"m3": "㎥", "m2": "㎡", "ton": "ton", "m": "m", "ea": "개"}


def _squash(s: str) -> str:
    return re.sub(r"\s", "", s or "")


def normalize_rebar_spec(spec: str) -> str | None:
    """'SD400, D13' · 'D13(SD400)' · 'HD13 SD400' → 'SD400 D13'. 철근 규격이 아니면 None."""
    s = (spec or "").upper()
    grade = re.search(r"SD\s*(\d{3})(W)?", s)
    dia = re.search(r"(?<![A-Z])H?D\s*(\d{2})(?!\d)", s)
    if not (grade and dia):
        return None
    return f"SD{grade.group(1)}{grade.group(2) or ''} D{dia.group(1)}"


def _spec_for(material: str, spec: str, name: str = "") -> str | None:
    if material == "ready_mixed_concrete":
        from .boq import normalize_concrete_spec
        return normalize_concrete_spec(spec)
    if material == "rebar":
        from .boq import normalize_rebar_spec as from_boq
        return from_boq(name, spec)          # 사급 내역: 강종은 품명, 지름은 규격(H-13 등)
    return _squash(spec) or "(규격 없음)"


def group_spec(rule: Rule, spec: str, name: str = "") -> str:
    """규칙의 spec_group 에 따라 규격을 묶음 이름으로 바꾼다(L4-D2). 없으면 그대로.
    all → 한 이름(기본 '규격별'). pattern → 규격 먼저, 없으면 품명에서 정규식을 찾아 label 의 {n} 에 그룹을 넣는다(대문자로 맞춤)."""
    if rule.spec_group == "all":
        return rule.spec_group_label or "규격별"
    if rule.spec_group != "pattern":
        return spec
    rx = re.compile(rule.spec_group_pattern, re.IGNORECASE)
    for text in (spec, _squash(name)):
        hit = rx.search(text or "")
        if hit:
            label = re.sub(r"\{(\d+)\}", lambda k: (hit.group(int(k.group(1))) or "").upper(), rule.spec_group_label)
            return label or rule.spec_group_other or "기타"
    return rule.spec_group_other or "기타"


INSTALL_WORDS = ("설치", "깔기", "붙이기", "삽입", "시공")
NO_QTY_SPEC = "자재 포함 시공 행"
_INCLUDED = re.compile(r"\([^()]*포함[^()]*\)")   # '…쌓기(3.6M 이하, 건조모르타르 포함)' — 괄호 안 포함 자재(L7-E5)


def _included_only(name: str, word: str) -> bool:
    """word 가 name 에서 '(…포함)' 괄호 안에만 나오는가(공백 지운 글 기준)."""
    spans = [(m.start(), m.end()) for m in _INCLUDED.finditer(name)]
    starts = [m.start() for m in re.finditer(re.escape(word), name)]
    return bool(starts) and all(any(a <= i and i + len(word) <= b for a, b in spans) for i in starts)

# 공종 칸(L6-E1). 내역서 구분 경로에서 공종 제목을 찾는다. 분야·부위·동·블록·사업명 같은 구분은 공종이 아니다.
NOT_WORK = {"건축공사", "토목공사", "기계공사", "기계설비공사", "설비공사", "전기공사", "통신공사", "소방공사",
            "본공사", "공통공사", "직접공사", "상부공사", "기초공사"}
FILLER = {"이하", "상기", "기타", "위", "각종", "별도", "추가", "※"}   # 제목 앞 설명어(L6-E2: '이하 제거식앵커 공사')
_PLACE = re.compile(r"\d+\s*(동|층|단지|공구|블록|BL)|BL$|아파트|주차장|근린생활|복리시설|주민공동|건설공사|신축공사|공구")


def work_title(text: str) -> str:
    """구분 제목 하나 → 공종 이름('1-1 0101. 철근콘크리트공사' → '철근콘크리트공사'). 공종이 아니면 ''."""
    t = re.sub(r"^\s*(?:\d+(?:[-.]\d+)*\s*)+\.?\s*", "", text or "")
    t = re.sub(r"^\s*[가-하]\.\s*", "", t)
    words = t.strip("=- ").split()
    if len(words) > 1 and not all(len(w) == 1 for w in words):
        while len(words) > 1 and words[0].strip(":·,") in FILLER:    # 앞 설명어를 뗀다('기타공사'처럼 붙은 것은 그대로)
            words = words[1:]
        if len(words) > 1 and words[-1] in ("공사", "공"):          # '방수 공사' → '방수공사'
            words = words[:-2] + [words[-2] + words[-1]]
    t = "".join(words) if all(len(w) == 1 for w in words) else " ".join(words)   # 자간 띄운 제목('방 수 공 사')만 붙인다
    if not t or len(t) > 12 or not re.search(r"공(사)?$", t) or t in NOT_WORK or _PLACE.search(t):
        return ""
    return t


def work_from_section(section: str) -> str:
    """구분 경로에서 가장 깊은 공종 제목(없으면 '')."""
    from .boq import SECTION_SEP
    for part in reversed((section or "").split(SECTION_SEP)):
        w = work_title(part)
        if w:
            return w
    return ""


def match_rule(line: BoqLine, rules: dict[str, Rule]) -> Rule | None:
    rule, _ = match_rule_kind(line, rules)
    return rule


def match_candidates(line: BoqLine, rules: dict[str, Rule]) -> list[tuple[int, Rule, bool]]:
    """맞는 규칙 전부 → [(맞은 이름 길이, 규칙, 시공 행 여부)], 긴 이름(구체적) 순. hate(루프 4): 첫 규칙만 조용히 이기지 않게."""
    from .boq import normalize_unit
    name = _squash(line.name)
    spec = _squash(line.spec).upper()
    unit = normalize_unit(line.unit)
    install = any(w in name for w in INSTALL_WORDS)
    out = []
    for rule in rules.values():
        words = [_squash(n) for n in rule.match_names if _squash(n) and _squash(n) in name]
        if not words and rule.match_spec_names and any(_squash(s).upper() in spec for s in rule.match_spec_names if _squash(s)):
            # 일반 이름 + 규격(L7-E6): 품명은 '거푸집'뿐이고 규격에 '합판6회' 처럼 자재가 있는 행
            words = [_squash(n) for n in rule.match_names_generic if _squash(n) and _squash(n) in name]
        if not words:
            continue
        # 괄호 '(…포함)' 안에만 나온 자재(L7-E5): 시공 행을 받는 규칙이면 '자재 포함 시공 행'으로 받는다.
        # 괄호 밖 제외어(쌓기·바르기 등)는 그 시공 행의 공종 말이라 보지 않고, 괄호 밖에서 맞은 규칙보다 뒤로 둔다.
        included = rule.accept_install_rows and all(_included_only(name, w) for w in words)
        seg = "".join(m.group(0) for m in _INCLUDED.finditer(name)) if included else name
        hit_ex = [x for x in rule.match_exclude if _squash(x) in seg]
        if hit_ex and not (rule.accept_install_rows and all(any(w in _squash(x) for w in INSTALL_WORDS) for x in hit_ex)):
            continue
        units_ok = not rule.match_units or unit in rule.match_units
        inst = bool(hit_ex) or ((install or included) and rule.accept_install_rows)
        if (units_ok and not included) or (inst and unit in (*rule.match_units, *rule.install_units)):
            out.append((max(len(w) for w in words), rule, inst, included))
    out.sort(key=lambda x: (x[3], -x[0], 0 if x[1].owner else 1))   # 괄호 밖 먼저 → 긴 이름 우선 → 켜진 발주처 규칙 우선
    return [(n, r, inst) for n, r, inst, _ in out]


def match_rule_kind(line: BoqLine, rules: dict[str, Rule]) -> tuple[Rule | None, bool]:
    """(규칙, 시공 행 여부) — 가장 구체적으로(긴 이름으로) 맞은 규칙."""
    c = match_candidates(line, rules)
    return (c[0][1], c[0][2]) if c else (None, False)


def is_composite(line: BoqLine) -> bool:
    """‘보온틀(경질우레탄폼 단열재+석고보드)’처럼 두 자재를 +로 묶은 복합 항목."""
    return "+" in (line.name or "")


def ambiguous(line: BoqLine, rules: dict[str, Rule]) -> list[str]:
    """같은 길이로 맞은 규칙이 둘 이상이면 그 목록(복합 항목 제외)."""
    c = match_candidates(line, rules)
    if len(c) < 2 or is_composite(line) or c[0][0] != c[1][0]:
        return []
    return [r.material for n, r, _ in c if n == c[0][0]]


# 설비 배관 토공(L7-E3, 사용자 결정 09-26): 기계·전기 등 내역의 터파기·되메우기는 따로 시험하지 않고 토목 토공 로트에 넣는다.
EARTHWORK_WORK = "토공사"            # 규칙 work 가 이 값인 자재를 토공으로 본다
EARTHWORK_TO = "토목"
EARTHWORK_KEEP = ("건축", "토목")     # 건축 터파기는 건축 기초 토공이라 옮기지 않는다


def _earthwork_discipline(ln: BoqLine, rule: Rule) -> str:
    if rule.work == EARTHWORK_WORK and ln.discipline not in EARTHWORK_KEEP:
        return EARTHWORK_TO
    return ln.discipline


def aggregate(lines: list[BoqLine], rules: dict[str, Rule], block: str | None = None,
              all_blocks_for: frozenset[str] = frozenset(),
              moved: list[dict] | None = None,
              forced: dict[int, tuple[Rule, bool, bool]] | None = None) -> tuple[list[MaterialQty], list[BoqLine]]:
    """규칙에 걸린 행을 (자재, 규격, 단위, 블록, 분야)로 합산. 두 번째 값은 자재는 맞지만 규격을 못 읽은 행.
    moved 를 주면 토목으로 옮긴 설비 토공을 [{from, material, spec, qty, unit, lines}] 로 채운다."""
    from .boq import normalize_unit
    sums: dict[tuple, float] = defaultdict(float)
    srcs: dict[tuple, list] = defaultdict(list)
    works: dict[tuple, dict[str, float]] = defaultdict(dict)   # 공종별 수량(다수결)
    unread: list[BoqLine] = []
    kinds = {id(ln): match_rule_kind(ln, rules) for ln in lines}
    forced = forced or {}
    for ln in lines:                                    # 현장 확인으로 넣은 행(L7-E7): 규칙에 안 걸린 행을 그 종별 규칙으로
        if id(ln) in forced and kinds[id(ln)][0] is None:
            kinds[id(ln)] = forced[id(ln)][:2]

    def _key_spec(ln: BoqLine, rule: Rule):
        s = _spec_for(rule.material, ln.spec, ln.name)
        return None if s is None else group_spec(rule, s, ln.name)

    # 같은 분야·같은 자재·같은 규격이 지급 시트에 있으면 사급 재료 행은 중복이므로 뺀다
    # (예: 토목 레미콘 25-21-150 이 지급·사급 양쪽에 나옴). 규격이 다르면(지급 문 ≠ 사급 방화문) 둘 다 산다.
    supplied = {(r.material, ln.discipline, _key_spec(ln, r), ln.block) for ln in lines
                for r, _ in [kinds[id(ln)]] if ln.supply == "지급" and r is not None}   # 블록까지 같아야 중복(L4-T4)
    material_keys = {(r.material, ln.discipline, _key_spec(ln, r), ln.block) for ln in lines
                     for r, inst in [kinds[id(ln)]] if r and not inst}              # 시공 행 중복도 (자재·규격·블록) 단위(L4-T4)
    has_material = {(r.material, ln.discipline, ln.block) for ln in lines
                    for r, inst in [kinds[id(ln)]] if r and not inst}      # 자재 행이 있는 (자재·분야·블록)
    install_only: set = set()
    zero_ok: set = set()                                    # 수량 없이도 행을 남길 키(수량 환산 없는 시공 행)
    moves: dict[tuple, list] = {}
    expanded: list[tuple[BoqLine, Rule, bool]] = []
    for ln in lines:
        if is_composite(ln):
            seen: set[str] = set()
            for _, r, inst in match_candidates(ln, rules):     # 복합 항목: 맞은 자재마다 한 번씩
                if r.material not in seen:
                    seen.add(r.material)
                    expanded.append((ln, r, inst))
            if not seen:
                expanded.append((ln, None, False))
        else:
            r, inst = kinds[id(ln)]
            expanded.append((ln, r, inst))
    for ln, rule, inst in expanded:
        # 블록을 지정해도 블록 구분 없는 공구 공통 행(예: 토목 지급자재)은 포함한다.
        if block is not None and ln.block and block not in ln.block and ln.discipline not in all_blocks_for:
            continue
        if rule is None:
            continue
        if inst:                                  # 시공 행: 같은 분야에 자재 행이 있으면 중복이므로 버린다
            if (rule.material, ln.discipline, _key_spec(ln, rule), ln.block) in material_keys:
                continue
        if ln.supply != "지급" and ((rule.material, ln.discipline, _key_spec(ln, rule), ln.block) in supplied
                                   or (rule.material, ln.discipline, _key_spec(ln, rule), "") in supplied):   # 공구 공통 지급도 중복
            continue
        spec = _spec_for(rule.material, ln.spec, ln.name)
        if spec is None:
            unread.append(ln)
            continue
        spec = group_spec(rule, spec, ln.name)             # 규격 묶음(spec_group): 단위는 키에 남아 단위별로 나뉜다
        disc = _earthwork_discipline(ln, rule)             # 중복 판정은 원래 분야로, 합산은 옮긴 분야로
        blk = "" if disc in all_blocks_for else ln.block     # 공구 합계 분야는 블록을 합친다
        unit, qty = normalize_unit(ln.unit), ln.qty
        no_qty = False
        fq = forced.get(id(ln)) if kinds[id(ln)][0] is rule else None
        if fq and fq[2]:                                    # 현장 확인 행인데 단위가 규칙 단위로 환산 안 됨 → 수량 없이(E5 방식)
            unit, qty, no_qty = (rule.match_units or (unit,))[0], 0.0, True
            unit = next((dst for src, dst, f in rule.unit_factors if normalize_unit(src) == unit and f), unit)   # 자재 행과 같은 단위 키로
        for src, dst, factor in (() if no_qty else rule.unit_factors):          # 단위 환산(L4-G1 제안): 천매→ea, 포→ton 등
            if unit == normalize_unit(src):
                unit, qty = dst, qty * factor
                no_qty = factor == 0                        # 곱 0 = 이 단위 행은 자재 포함만 알리고 수량은 환산하지 않는다(L7-E5)
                break
        if no_qty and inst:
            if (rule.material, ln.discipline, ln.block) in has_material or (rule.material, ln.discipline, "") in has_material:
                continue                                    # 자재 행이 있으면 수량 없는 시공 행은 버린다
            spec = NO_QTY_SPEC                              # 시공 행 규격(두께·높이 등)마다 행이 생기지 않게 한 행으로
        k = (rule.material, spec, unit, blk, disc)
        if inst:
            install_only.add(k)
        if no_qty:
            zero_ok.add(k)
        sums[k] += qty
        srcs[k].append((ln.sheet, ln.row))
        if disc != ln.discipline:
            mv = moves.setdefault((ln.discipline, rule.material, spec, unit), [0.0, 0])
            mv[0] += qty
            mv[1] += 1
            continue                                        # 설비 구분(오배수공사 등)은 토목 행의 공종 투표에 넣지 않는다
        w = work_from_section(ln.section)
        if w:
            works[k][w] = works[k].get(w, 0.0) + abs(qty)
    if moved is not None:
        moved.extend({"from": d, "material": mat, "spec": sp, "qty": round(q, 3), "unit": u, "lines": n}
                     for (d, mat, sp, u), (q, n) in moves.items())
    out = [MaterialQty(material=k[0], spec=k[1], unit=k[2], qty=round(v, 3), block=k[3], discipline=k[4], sources=tuple(srcs[k]),
                       from_install=k in install_only, work=_vote(works.get(k)))
           for k, v in sums.items() if v > 0 or (k in zero_ok and v == 0)]
    out.sort(key=lambda m: (m.discipline, m.material, m.spec))
    return out, unread


def _vote(weights: dict[str, float] | None) -> str:
    """수량이 가장 큰 공종. 같으면 먼저 나온 것."""
    return max(weights.items(), key=lambda kv: kv[1])[0] if weights else ""


def rule_for_key(key: str, rules: dict[str, Rule]) -> Rule | None:
    """색인 종별 key 로 이어진 규칙(index_keys 또는 규칙 키). 둘 이상이면 켜진 발주처 규칙 먼저."""
    cands = [r for r in rules.values() if key in r.index_keys or r.material == key]
    cands.sort(key=lambda r: (0 if r.owner else 1, r.material))
    return cands[0] if cands else None


def forced_matches(lines: list[BoqLine], rules: dict[str, Rule], keys: set[str],
                   by_name: dict[str, str] | None = None) -> dict[int, tuple[Rule, bool, bool]]:
    """현장 확인 '예'(L7-E7): 어떤 규칙에도 안 걸린 행 중 색인이 그 종별로 본 행 → {id(행): (규칙, 시공 행, 수량 없음)}.
    사용자에게 보인 목록과 같게: 그 종별에 자재 행(노무·설치 아님)이 있으면 그 행만('규칙 밖 행'), 없으면 설치 행('설치 행에만 있음').
    설치·시공 행은 자재 포함 시공 행으로 받고, 단위가 규칙 단위(또는 환산)로 안 맞으면 수량 없이 넣는다(지어내지 않음)."""
    from .boq import normalize_unit
    from .index import is_cost, is_labor, line_keys
    out: dict[int, tuple[Rule, bool, bool]] = {}
    by_name = by_name or {}
    if not keys and not by_name:
        return out
    by_key: dict[str, list[tuple[BoqLine, Rule, bool]]] = defaultdict(list)
    named: list[tuple[BoqLine, Rule, bool]] = []
    for ln in lines:
        if is_composite(ln) or is_cost(ln.name) or match_rule(ln, rules) is not None:
            continue
        if ln.name in by_name:                               # 품명 확인 행을 사용자가 고른 종별 규칙으로(L7-E8)
            rule = rule_for_key(by_name[ln.name], rules)
            if rule:
                named.append((ln, rule, is_labor(ln.name, ln.unit)))
            continue
        for k in (k for k in line_keys(ln) if k in keys):   # line_keys 는 규격만으로 걸린 행을 주지 않는다(L7-E8)
            rule = rule_for_key(k, rules)
            if rule:
                by_key[k].append((ln, rule, is_labor(ln.name, ln.unit)))
                break
    chosen = list(named)
    for items in by_key.values():
        material = [x for x in items if not x[2]]
        chosen += material or items                         # 보인 목록과 같게: 자재 행이 있으면 그것만, 없으면 설치 행
    for ln, rule, labor in chosen:
        unit = normalize_unit(ln.unit)
        convertible = (not rule.match_units or unit in rule.match_units or unit in rule.install_units
                       or any(normalize_unit(src) == unit and factor for src, _, factor in rule.unit_factors))
        install = labor or any(w in _squash(ln.name) for w in INSTALL_WORDS)
        out[id(ln)] = (rule, install or not convertible, not convertible)
    return out


def work_missing(rows: list[PlanRow]) -> int:
    """공종 칸이 빈 행 수(요약 JSON work_missing)."""
    return sum(1 for r in rows if not r.work)


def _fmt_qty(q: float) -> str:
    return f"{q:,.0f}" if abs(q - round(q)) < 1e-9 else f"{q:,.2f}"


FORMWORK_PARTS = ("수직", "수평", "예비")   # 거푸집 해체용 조: 수직부재 1, 수평부재 1, 예비 1


def parse_sets(spec: str | None) -> dict[str, int]:
    """'25-24-150=7,*=4' → {'25-24-150': 7, '*': 4}.
    값에 부위 이름을 쓰면 개수로 센다: '25-24-150=수직+수평+예비' → 3, '25-24-80=수직+예비' → 2.
    (기둥·기초처럼 수직부재만이면 수직+예비, 슬래브·보까지 받으면 수직+수평+예비 풀세트 — 사용자 실무 설명 09-26)"""
    out: dict[str, int] = {}
    for part in filter(None, (spec or "").split(",")):
        k, _, v = part.partition("=")
        v = v.strip()
        if v.isdigit():
            out[k.strip()] = int(v)
        else:
            parts = [p.strip() for p in v.split("+") if p.strip()]
            bad = [p for p in parts if p not in FORMWORK_PARTS]
            if bad or not parts:
                raise ValueError(f"조 구성 '{v}' 을 읽을 수 없습니다. 숫자 또는 {'+'.join(FORMWORK_PARTS)} 조합으로 적으세요.")
            out[k.strip()] = len(set(parts))
    return out


def _lookup(table: dict, m: MaterialQty, default=None):
    """'분야:규격' → '규격' → '*' 순으로 찾는다."""
    for k in (f"{m.discipline}:{m.spec}", m.spec, "*"):
        if k in table:
            return table[k]
    return default


def sort_by_work(mats: list[MaterialQty], rules: dict[str, Rule]) -> list[MaterialQty]:
    """분야 안에서 공종별로 모은다(L6-E2). 공종 순서 = 그 공종 자재의 규칙 order 최소값, 같으면 먼저 나온 공종.
    공종 안은 들어온 순서 그대로(안정 정렬). 공종이 빈 자재는 분야 끝."""
    work = lambda m: m.work or rules[m.material].work  # noqa: E731
    rank: dict[tuple[str, str], tuple[int, int]] = {}
    for i, m in enumerate(mats):
        k = (m.discipline, work(m))
        o = rules[m.material].order
        rank[k] = (min(rank[k][0], o), rank[k][1]) if k in rank else (o, i)
    return sorted(mats, key=lambda m: (_DISC_ORDER.get(m.discipline, 9), m.discipline, not work(m), rank[(m.discipline, work(m))]))


_DISC_ORDER = {"건축": 0, "토목": 1, "기계": 2}


def plan_rows(mats: list[MaterialQty], rules: dict[str, Rule], sets_per_lot: dict[str, int] | None = None,
              formwork_sets: dict[str, int] | None = None, include_optional: bool = False,
              makers: dict[str, int] | None = None, non_ks: bool = False) -> list[PlanRow]:
    """sets_per_lot: 로트당 조 수를 통째로 지정(규칙 기본값보다 우선). formwork_sets: 거푸집 해체용 조를 기본값에 더한다."""
    sets_per_lot = sets_per_lot or {}
    formwork_sets = formwork_sets or {}
    rows: list[PlanRow] = []
    makers = makers or {}
    disc_order = {"건축": 0, "토목": 1, "기계": 2}

    def spec_key(spec: str):
        return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", spec)]

    mats = sorted(mats, key=lambda m: (disc_order.get(m.discipline, 9), rules[m.material].order, spec_key(m.spec)))
    mats = sort_by_work(mats, rules)
    for m in mats:
        rule = rules[m.material]
        if rule.group_tests:
            row = group_row(m, rule, ks=not non_ks, makers=_lookup(makers, m))
            if rule.ks_mark and not non_ks:
                row.count_ks = "◎"
            if m.from_install:
                row.note = (row.note + "; " if row.note else "") + ("시공 행 추정(수량 환산 없음)" if not m.qty else "시공 행 추정")
            rows.append(row)
            continue
        ul = UNIT_LABEL.get(m.unit, m.unit)
        for t in rule.tests:
            if t.optional and not include_optional:
                continue
            f = t.frequency
            note = detail = ""
            if f.per_qty and m.from_install and not m.qty:   # 수량 없는 시공 행 추정(L7-E5)
                count, basis, note = 0, "수량 없음(자재 포함 시공 행) — 수량 확인 필요", "수량 확인 필요"
            elif f.per_qty:
                if f.unit and f.unit != m.unit:
                    count, basis = 0, f"단위 불일치: 물량 {m.unit}, 빈도 {f.unit}"
                    note = "확인 필요"
                elif f.lot:
                    lots = max(f.minimum, math.ceil(m.qty / f.per_qty))
                    n = _lookup(sets_per_lot, m)
                    detail = ""
                    if n is None and f.default_sets:
                        extra = _lookup(formwork_sets, m, 0)
                        n = f.default_sets + extra
                        detail = "조 구성: 28일3+7일1" + (f"+거푸집용{extra}" if extra else "(거푸집 해체용 조 없음)")
                    per = f"{_fmt_qty(f.per_qty)}{UNIT_LABEL.get(f.unit or '', f.unit or '')}"
                    if n:
                        count, basis = lots * n, f"{_fmt_qty(m.qty)}{ul}/{per}당{n}조"
                    else:
                        count, basis, note = lots, f"{_fmt_qty(m.qty)}{ul}/{per} = {lots}로트", "조 수 확인"
                else:
                    count = max(f.minimum, math.ceil(m.qty / f.per_qty))
                    basis = f"{_fmt_qty(m.qty)}{ul}/{_fmt_qty(f.per_qty)}{UNIT_LABEL.get(f.unit or '', f.unit or '')}당1회"
            else:
                count, basis = f.minimum, f.text
            if f.lot and m.unit == "m3" and 0 < m.qty < SMALL_CONCRETE_M3:
                note = (note + "; " if note else "") + "생략 가능"
                detail = (detail + "; " if detail else "") + f"전체 {SMALL_CONCRETE_M3}㎥ 미만 — 감독자 판단으로 강도시험 생략 가능(발주처 시방 예: LHCS 14 20 10 05:2020 3.12.5.1(5) — 공사 시방 확인)"
            row = PlanRow(discipline=m.discipline, work=m.work or rule.work, item=f"{rule.label}({m.spec})", test_type=t.display or t.test_type,
                          qty=m.qty, unit=ul, frequency=f.text, calc_basis=basis, note=note,
                          basis=t.basis, material=m.material, spec=m.spec, sources=list(m.sources),
                          detail=detail if f.lot else "")
            if rule.ks_mark:
                row.count_ks = "◎"
            if t.where == "외부":
                row.count_external = count
            elif t.where == "KS":
                row.count_ks = "KS"
            else:
                row.count_site = count
            rows.append(row)
    return rows


def group_row(m: MaterialQty, rule: Rule, ks: bool = True, makers: int | None = None) -> PlanRow:
    """규격당 한 행(시험 묶음). KS 제품: ks_count='none' 이면 시험 없이 ◎(시행령 91조 면제, 산출근거 'KS자재'),
    'makers' 면 제조사 수×1회(철근 관행). 비KS: 물량 빈도가 있으면 ⌈물량/빈도⌉×제조사 수, 없으면 제조사 수×1회."""
    ks = ks and rule.ks_mark                    # KS 종별이 아니면 KS 경로로 가지 않는다(L4-G1 제안)
    if rule.material == "rebar" or rule.ks_count == "makers" or not ks:
        return rebar_group_row(m, rule, ks=ks, makers=makers)
    tests = [t for t in rule.tests if not t.optional]
    ul = UNIT_LABEL.get(m.unit, m.unit)
    return PlanRow(discipline=m.discipline, work=m.work or rule.work, item=f"{rule.label}({m.spec})",
                   test_type=",".join(t.display or t.test_type for t in tests), qty=m.qty, unit=ul,
                   frequency=rule.group_frequency, calc_basis="KS자재", count_ks="◎",
                   basis=rule.group_basis, material=m.material, spec=m.spec, sources=list(m.sources))


def rebar_group_row(m: MaterialQty, rule: Rule, ks: bool = True, makers: int | None = None) -> PlanRow:
    """철근 규격(강종·지름)당 한 행. 시험들을 ','로 묶고, 빈도는 KS/비KS 두 줄 문구.
    KS: 제조회사 수 × 1회(외부) — 별표2 ※주석(p.52)의 KS 시험 제외에 따른 실무 표기.
    비KS: ⌈톤/50⌉ × 제조회사 수(외부). makers 를 안 주면 1곳으로 보고 '제조회사 수 확인 필요'를 남긴다."""
    note = "제조사 수 확인" if makers is None else ""
    makers = 1 if makers is None else makers
    if makers < 1:
        raise ValueError("제조회사 수는 1 이상이어야 합니다.")
    tests = [t for t in rule.tests if not t.optional]
    ul = UNIT_LABEL.get(m.unit, m.unit)
    if ks:
        count, basis = makers, "KS자재 - 제조회사 및 제품규격별 1회"
    else:
        per_t = next((t for t in tests if t.frequency.per_qty), None)
        who = rule.makers_label
        if per_t is None:                        # 문구형 빈도(제조회사별·규격별 등): 제조사 수×1회 (L4-G1 제안)
            count = makers
            basis = f"{rule.group_frequency or who + '별'} — {who} {makers}곳"
        elif per_t.frequency.unit and per_t.frequency.unit != m.unit:   # 단위 불일치: 조용히 계산하지 않는다(L4-G1b 제안)
            count = makers
            basis = f"단위 확인: 물량 {m.unit}, 빈도 {per_t.frequency.unit}"
            note = (note + "; " if note else "") + "단위 확인"
        elif m.from_install and not m.qty:        # 시공 행에 자재 수량이 없음(L7-E5): 물량 빈도 횟수를 지어내지 않는다
            count = 0
            basis = "수량 없음(자재 포함 시공 행) — 수량 확인 필요"
            note = (note + "; " if note else "") + "수량 확인 필요"
        else:
            per = per_t.frequency.per_qty
            count = max(1, math.ceil(m.qty / per)) * makers
            basis = f"{_fmt_qty(m.qty)}{ul}/{_fmt_qty(per)}{ul}×{who}{makers}곳"
    return PlanRow(discipline=m.discipline, work=m.work or rule.work, item=f"{rule.label}({m.spec})",
                   test_type=",".join(t.test_type for t in tests), qty=m.qty, unit=ul,
                   frequency=rule.group_frequency, calc_basis=basis, count_external=count, note=note,
                   basis=rule.group_basis, material=m.material, spec=m.spec, sources=list(m.sources))


COMMON_SPECS = DATA_DIR / "common_specs.yaml"


def missing_common_specs(mats: list[MaterialQty], path: Path = COMMON_SPECS) -> list[str]:
    """흔한 규격 중 도급내역서에 없는 것 → ['건축:rebar:SD400 D10', ...]."""
    import yaml
    table = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    have = {(m.discipline, m.material, m.spec) for m in mats}
    return [f"{d}:{mat}:{s}" for d, by in table.items() for mat, specs in by.items() for s in specs if (d, mat, s) not in have]


def added_spec_rows(specs: list[str], rules: dict[str, Rule], makers: dict[str, int] | None = None) -> list[PlanRow]:
    """사용자가 고른 누락 추정 규격을 수량 없이(“-”) 넣는다. 형식 '분야:자재:규격'."""
    rows = []
    for item in specs:
        disc, material, spec = item.split(":", 2)
        rule = rules[material]
        m = MaterialQty(material, spec, (rule.match_units or ("",))[0], 0.0, "", disc)
        if rule.group_tests:
            row = group_row(m, rule, makers=_lookup(makers or {}, m))
        else:
            row = plan_rows([m], rules)[0]
        row.note = "도급내역서 누락 추정 — 임시 계상" + (f"; {row.note}" if row.note else "")
        rows.append(row)
    return rows


def optional_tests(rules: dict[str, Rule]) -> list[str]:
    """기본 산출에서 뺀 조건부 시험 — 사용자에게 '해당 시 추가'로 알린다."""
    return [f"{r.label} {t.test_type}: {t.conditions}" for r in rules.values() for t in r.tests if t.optional]


def rows_to_json(rows: list[PlanRow]) -> list[dict]:
    """채점기 형식(JSON)."""
    keys = ("discipline", "work", "item", "material", "spec", "test_type", "qty", "unit", "frequency",
            "calc_basis", "count_site", "count_external", "count_ks", "note", "detail", "basis")
    return [{k: getattr(r, k) for k in keys} for r in rows]
