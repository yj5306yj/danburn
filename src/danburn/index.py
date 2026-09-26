"""별표2 전체 종별 색인(data/byeolpyo2_index.yaml) — 도급내역서 품명에서 종별을 찾고, 규칙이 없는 종별을 알린다.

규칙(data/rules)은 레미콘·철근뿐이라 다른 자재가 경고 없이 빠진다. 이 모듈은 산출이 아니라 '빠진 자재 식별'만 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_INDEX = Path(__file__).resolve().parents[2] / "data" / "byeolpyo2_index.yaml"
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# 노무·장비 행: 자재 이름을 뺀 나머지 품명에 이 말이 있으면 자재 행이 아니다(예: '레미콘 타설', '조립식맨홀 설치').
LABOR_WORDS = ("시공", "설치", "운반", "타설", "조립", "인건", "노무", "인력", "가공", "하차", "절단",
               "해체", "철거", "장비", "손료", "선별", "펌프카", "기계경비",
               "뽑기", "부설", "박기", "천공")   # L7-E5: 말뚝 박기·뽑기·천공, 관 부설. '접합'은 '접합부위'·'접합유리' 때문에 넣지 않음
# 붙이기·깔기·쌓기·바르기는 '자재 포함 시공 행'(타일 붙이기·장판 깔기 등) 판정과 얽혀 넣지 않는다(L7-E5 영향 조사).
LABOR_UNITS = ("인", "인일", "man-day")
# 비자재 비용 행(L7-E8): 자재가 아니라 경비라 누락 경고·현장 확인 질문에서 뺀다. '경비실' 같은 실 이름에 걸리지 않게 '경비' 단독은 넣지 않는다.
COST_WORDS = ("양생비", "통행료", "손료", "운반비", "시험비", "잡비", "용수비", "제경비", "전력비", "수수료", "보험료",
              "임차료", "사용료", "검사비", "측량비")


@dataclass(frozen=True)
class IndexEntry:
    key: str
    label: str             # 별표2 종별 이름
    part: str              # 대분류 (예: "1. 공통")
    section: str           # 중분류 (예: "나. 철근콘크리트공사")
    subsection: str        # 소분류 (도로공사만, 예: "(2) 아스팔트 포장")
    ks: str | None         # 종별 괄호 안 KS 번호
    page: int              # PDF 시작 쪽
    names: tuple[str, ...] # 품명 동의어
    rule: str | None       # data/rules material 키
    order: int = 0         # 색인 안 순서(동률 정렬용)
    exclude: tuple[str, ...] = ()  # 품명에 있으면 이 종별이 아님(예: 타일 ← '덕타일', 철근 ← '철근 간격재')


def _squash(s: str) -> str:
    """공백·가운뎃점·하이픈을 지우고 영문은 대문자로."""
    return re.sub(r"[\s·・‧\-_]", "", s or "").upper()


INCLUDED_RE = re.compile(r"[(\[][^()\[\]]*포함[^()\[\]]*[)\]]")


def _prep(s: str) -> tuple[str, tuple[bool, ...]]:
    """비교용 글자열과 글자별 '괄호 안 포함 자재' 표시. 괄호 기호는 지운다(예: '단열재(PUR)' → '단열재PUR').

    '타일붙이기(건조모르타르 포함)'처럼 괄호 안에 '포함'이 있으면 그 안의 자재는 부자재라 후순위로 둔다."""
    text = _squash(s)
    inside = [False] * len(text)
    for m in INCLUDED_RE.finditer(text):
        inside[m.start():m.end()] = [True] * (m.end() - m.start())
    keep = [i for i, c in enumerate(text) if c not in "()[]"]
    return "".join(text[i] for i in keep), tuple(inside[i] for i in keep)


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[IndexEntry, ...]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    entries: list[IndexEntry] = []
    seen: set[str] = set()
    for sec in raw.get("sections") or ():
        for e in sec.get("entries") or ():
            key = e.get("key") or ""
            ctx = f"{Path(path).name} [{key or '?'}]"
            if not KEY_RE.match(key):
                raise ValueError(f"{ctx}: key 는 영문 소문자 식별자여야 함")
            if key in seen:
                raise ValueError(f"{ctx}: key 중복")
            seen.add(key)
            names = tuple(e.get("names") or ())
            if not 1 <= len(names) <= 12 or not all(isinstance(n, str) and n.strip() for n in names):
                raise ValueError(f"{ctx}: names 는 비지 않은 이름 1~12개")
            exclude = tuple(e.get("exclude") or ())
            if not all(isinstance(x, str) and x.strip() for x in exclude):
                raise ValueError(f"{ctx}: exclude 는 비지 않은 이름 목록")
            page = int(e.get("page") or 0)
            if page < 1:
                raise ValueError(f"{ctx}: page 가 없음")
            entries.append(IndexEntry(
                key=key, label=str(e.get("label") or "").strip() or key,
                part=sec.get("part") or "", section=sec.get("section") or "",
                subsection=sec.get("subsection") or "", ks=e.get("ks") or None, page=page,
                names=names, rule=e.get("rule") or None, order=len(entries),
                exclude=tuple(_squash(x) for x in exclude),
            ))
    return tuple(entries)


def load_index(path: str | Path = DEFAULT_INDEX) -> list[IndexEntry]:
    return list(_load(str(path)))


def _best_spans(text: str, entries: list[IndexEntry]) -> list[tuple[IndexEntry, int, int]]:
    """종별마다 가장 긴 일치 구간 (entry, 시작, 끝). 동의어와 KS 번호(예: KSF4004)로 찾는다."""
    found = []
    for e in entries:
        if any(x in text for x in e.exclude):
            continue
        best = None
        for word in (*e.names, *((e.ks,) if e.ks else ())):
            w = _squash(word)
            i = text.find(w)
            if w and i >= 0 and (best is None or len(w) > best[2] - best[1]):
                best = (e, i, i + len(w))
        if best:
            found.append(best)
    return found


def _match(raw: str, entries: list[IndexEntry]) -> list[tuple[IndexEntry, int, int]]:
    """원 품명(또는 규격)에서 종별 일치 구간. 순서: 괄호 안 '포함' 자재는 뒤로 → 긴 일치 먼저 → 색인 순서."""
    text, inside = _prep(raw)
    spans = _best_spans(text, entries)
    # 긴 이름 우선: 더 긴 일치 구간 안에 들어가는 짧은 일치는 버린다(예: '점토벽돌' 안의 '벽돌').
    kept = [s for s in spans
            if not any(o[2] - o[1] > s[2] - s[1] and o[1] <= s[1] and s[2] <= o[2] for o in spans)]
    kept.sort(key=lambda s: (inside[s[1]], -(s[2] - s[1]), s[0].order))
    return kept


def _tier(text: str, span: tuple[IndexEntry, int, int]) -> tuple[bool, int]:
    """1순위 비교용 (괄호 안 포함 여부, 일치 길이)."""
    return _prep(text)[1][span[1]], span[2] - span[1]


def identify(name: str, spec: str = "", index: list[IndexEntry] | None = None) -> list[IndexEntry]:
    """품명(공백 무시)으로 종별을 찾는다. 긴 일치가 먼저, 동률은 색인 순서. 품명에 없으면 규격에서 찾는다."""
    entries = index if index is not None else load_index()
    for text in (name, spec):
        hits = _match(text, entries)
        if hits:
            return [h[0] for h in hits]
    return []


def _field(line, attr: str) -> str:
    if isinstance(line, dict):
        return str(line.get(attr) or "")
    return str(getattr(line, attr, "") or "")


def is_labor(name: str, unit: str = "", index: list[IndexEntry] | None = None) -> bool:
    """노무·장비 행인가. 자재 이름으로 일치한 부분을 지운 나머지 품명에서 노무 말을 찾는다."""
    if unit.strip() in LABOR_UNITS:
        return True
    text = _prep(name)[0]
    entries = index if index is not None else load_index()
    keep = [True] * len(text)
    for _, start, end in _match(name, entries):
        keep[start:end] = [False] * (end - start)
    rest = "".join(c if k else " " for c, k in zip(text, keep))
    return any(w in rest for w in LABOR_WORDS)


def is_cost(name: str) -> bool:
    """비자재 비용 행인가(양생비·통행료·손료·운반비 등)."""
    text = _squash(name)
    return any(w in text for w in COST_WORDS)


def _hit(line, entries: list[IndexEntry]):
    """(1순위 일치 목록, 일치한 글, 규격에서만 걸림, 걸린 말, 믿을 만함). 품명 먼저, 없으면 규격.
    규격에서만 걸린 일치는 KS 번호일 때만 믿는다(L7-E8: '시멘트라이닝' 규격 → 주철관을 시멘트로 보던 결함)."""
    name, spec = _field(line, "name"), _field(line, "spec")
    for text, from_spec in ((name, False), (spec, True)):
        matched = _match(text, entries)
        if matched:
            top = _tier(text, matched[0])
            top_hits = [m for m in matched if _tier(text, m) == top]
            word = _prep(text)[0][top_hits[0][1]:top_hits[0][2]]
            trusted = not from_spec or any(m[0].ks and word == _squash(m[0].ks) for m in top_hits)
            return top_hits, text, from_spec, word, trusted
    return [], "", False, "", True


def line_keys(line, index: list[IndexEntry] | None = None) -> list[str]:
    """한 행이 색인에서 1순위로 걸린 종별 key(coverage 와 같은 판정). 규격에서만 걸린 행은 KS 번호가 아니면 [] (L7-E8)."""
    entries = index if index is not None else load_index()
    top_hits, _, _, _, trusted = _hit(line, entries)
    return [m[0].key for m in top_hits] if trusted else []


def coverage(lines, index: list[IndexEntry] | None = None, max_examples: int = 5,
             covered_keys: frozenset[str] = frozenset(), matched=None) -> dict:
    """입력 행(BoqLine 또는 name/spec/unit 을 가진 dict)을 종별로 모은다.

    한 행은 1순위와 같은 순위(괄호 안 포함 여부·일치 길이)로 걸린 종별 모두에 센다(예: 레미콘 → 굳지 아니한·굳은 콘크리트).
    covered: 규칙이 있는 종별, uncovered: 규칙이 없는(rule null) 종별. 노무·장비 행은 뺀다.
    labor_only: 노무·설치 행에만 나오고 자재 행은 없는 종별(예: 'PVC지수판 설치'만 있음) — 자재가 설치 행에
    묶여 있을 수 있으니 사람이 확인한다. 규칙 유무와 상관없이 모은다.
    matched(행) → bool 을 주면 판정을 행 단위로 한다(L7-E4 조용한 누락): 어떤 규칙에 걸린 행은 uncovered 에서 빼고,
    규칙이 있는 종별인데 규칙에 걸리지 않은 행은 unmatched_in_covered 로 모은다(규칙 파일이 있다고 행이 덮이지 않는다).
    """
    entries = index if index is not None else load_index()
    hits: dict[str, dict] = {}
    miss_hits: dict[str, dict] = {}
    labor_hits: dict[str, dict] = {}

    def add(target: dict, e: IndexEntry, name: str, unit: str) -> None:
        h = target.setdefault(e.key, {"entry": e, "lines": 0, "examples": [], "units": []})
        h["lines"] += 1
        if name and name not in h["examples"] and len(h["examples"]) < max_examples:
            h["examples"].append(name)
        if unit and unit not in h["units"]:
            h["units"].append(unit)

    unknown: dict[str, dict] = {}
    for line in lines:
        name, spec, unit = _field(line, "name"), _field(line, "spec"), _field(line, "unit")
        if is_cost(name):                                  # 비용 행은 자재가 아니다(L7-E8)
            continue
        labor = is_labor(name, unit, entries)
        top_hits, text, from_spec, word, trusted = _hit(line, entries)
        if not top_hits:
            continue
        if not trusted and not (matched is not None and matched(line)):
            # 품명으로 자재를 알 수 없음(L7-E8): 규격 말로 종별을 정하지 않고 품명 그대로 따로 모은다.
            # 설치 행도 넣는다(install=True) — 규격에만 자재가 있는 시공 행('화장실칸막이 / 파티클보드')이 조용히 빠지지 않게
            g = top_hits[0][0]
            u = unknown.setdefault(name, {"name": name, "spec_word": word, "specs": [], "lines": 0, "units": [],
                                          "install": labor, "guess": {"key": g.key, "label": g.label, "rule": g.rule},
                                          "guesses": []})
            # 규격에서 걸린 종별 전부(L7-E9): '연강판·방청' 처럼 여럿이면 모두 추정 목록에 — 첫째(guess)는 가장 긴 일치
            for e, _, _ in [*top_hits, *_match(text, entries)]:
                if all(x["key"] != e.key for x in u["guesses"]):
                    u["guesses"].append({"key": e.key, "label": e.label, "rule": e.rule})
            u["lines"] += 1
            u["install"] = u["install"] and labor
            if spec and spec not in u["specs"] and len(u["specs"]) < max_examples:
                u["specs"].append(spec)
            if unit.strip() and unit.strip() not in u["units"]:
                u["units"].append(unit.strip())
            continue
        missed = matched is not None and not labor and not matched(line)
        for m in top_hits:
            add(labor_hits if labor else hits, m[0], name, unit.strip())
            if missed:
                add(miss_hits, m[0], name, unit.strip())

    def row(h: dict) -> dict:
        e = h["entry"]
        return {"key": e.key, "label": e.label, "section": f"{e.part} {e.section} {e.subsection}".strip(),
                "ks": e.ks, "page": e.page, "rule": e.rule, "lines": h["lines"], "examples": h["examples"],
                "units": h["units"]}

    has_rule = lambda h: bool(h["entry"].rule or h["entry"].key in covered_keys)  # noqa: E731
    ordered = sorted(hits.values(), key=lambda h: h["entry"].order)
    missed_ordered = sorted(miss_hits.values(), key=lambda h: h["entry"].order)
    if matched is None:
        uncovered = [row(h) for h in ordered if not has_rule(h)]
        unmatched_in_covered = []
    else:
        uncovered = [row(h) for h in missed_ordered if not has_rule(h)]
        unmatched_in_covered = [row(h) for h in missed_ordered if has_rule(h)]
    return {
        "covered": [row(h) for h in ordered if has_rule(h)],
        "uncovered": uncovered,
        "unmatched_in_covered": unmatched_in_covered,
        "labor_only": [row(h) for h in sorted(labor_hits.values(), key=lambda h: h["entry"].order)
                       if h["entry"].key not in hits],
        "name_unknown": list(unknown.values()),
    }
