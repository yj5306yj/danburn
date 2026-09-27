"""완성된 품질관리계획서 본문에서 기준 인용을 찾아 현행 판과 비교한다(danburn check 1차).

찾는 것: 업무지침 고시 번호, 계획서 최종 날짜, 건설기술 진흥법·시행령·시행규칙 판, KCS·KDS·LHCS 연도판,
폐지·통합된 옛 이름, KS 번호(목록만). 현행 판은 업무지침만 공개 미러로 온라인 확인하고(basis.py 재사용,
실패 시 동봉 기준표 스냅샷), 나머지는 스냅샷(src/danburn/data/standards_snapshot.yaml)과 비교한다.
계획서 글은 네트워크로 보내지 않는다 — 미러 요청에는 공개 법령 경로만 들어간다.
판정은 알림이다. 결과마다 무엇을 현행 무엇으로, 계획서 어디서, 다음에 무엇을 할지와 공식 확인 링크를 준다.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Callable

import yaml

from .basis import MIRROR_URL, OFFICIAL_URL, number_key, read_current_guideline
from .paths import DATA_DIR

SNAPSHOT_PATH = DATA_DIR / "standards_snapshot.yaml"
KCSC_URL = "https://www.kcsc.re.kr"
KS_URL = "https://standard.go.kr"
LAW_URL = "https://www.law.go.kr/법령/"
WHERE_MAX = 80

_WS = r"[ \t 　]"
_ADMRULE_RE = re.compile(r"(?:국토\s*교통부\s*)?고시\s*제\s*(\d{4})\s*-\s*(\d+)\s*호")
_GUIDELINE_RE = re.compile(r"업무\s*지침")
_OTHER_MGMT_RE = re.compile(r"(?<!품질)(?:안전|환경|사업|공정|유지)\s*관리\s*$")         # '안전관리 업무지침' 등 다른 지침
_BIND_GAP = 30                                                                    # 이름과 번호 사이 최대 글자
_BIND_STOP_RE = re.compile(r"「|」|지침|기준|규정|요령|규칙|법|령|및|또는")          # 사이에 다른 이름·나열이 끼면 끊는다
_DATE_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*(?:[.\-/]|년)\s*(\d{1,2})\s*(?:[.\-/]|월)\s*(\d{1,2})(?!\d)\s*(?:일|\.)?")
_HISTORY_RE = re.compile(r"(?:개정|변경|수정)\s*이력|revision\s*history", re.I)
_PLAN_DATE_KEY_RE = re.compile(r"작성|개정|수립|제정|변경|승인|검토|일자|날짜|rev", re.I)
_NOT_PLAN_DATE_RE = re.compile(r"예정|준공|착공|공사\s*기간|공기|만료|유효|기한|까지")          # 날짜 앞 20자에 있으면 작성일 아님
_LAW_MARK_BEFORE_RE = re.compile(r"진흥법|시행령|시행규칙|업무\s*지침|고시|령\s*제\s*\d+\s*호|법률\s*제\s*\d+\s*호|KCS|KDS|LHCS")
_LAW_MARK_AFTER_RE = re.compile(r"^\s*(?:\)|,)?\s*(?:시행|공포)")
_LAW_RE = re.compile(r"건설\s*기술\s*진흥\s*법(?:\s*(시행령|시행규칙))?")
_LAW_NUM_RE = re.compile(r"(법률|대통령령|국토교통부령|국토해양부령|건설교통부령)\s*제\s*(\d+)\s*호")
_LAW_DATE_KEY_RE = re.compile(r"^\s*(?:\)|,)?\s*(개정|공포|시행|일부\s*개정|타법\s*개정)")
_LAW_KIND = {None: ("건설기술 진흥법", "법률"), "시행령": ("건설기술 진흥법 시행령", "대통령령"),
             "시행규칙": ("건설기술 진흥법 시행규칙", "국토교통부령")}
_OLD_MINISTRY = {"국토해양부령", "건설교통부령"}
_CODE_RE = re.compile(
    rf"(?<![A-Za-z])(KCS|KDS|LHCS)\s*(\d{{2}})\s*(\d{{2}})\s*(\d{{2}})(?!\d)(?:{_WS}*(\d{{2}})(?!\d))?"
    rf"(?:(?:\s*[:：\-–—]\s*|\s*\(\s*|{_WS}+)((?:19|20)\d{{2}})(?!\d)\)?)?")
_URL_RE = re.compile(r"https?://[^\s'\")]+")
_ARTICLE_RE = re.compile(r"제\s*\d+\s*조|별표|별지|서식|부칙")
_KS_RE = re.compile(r"(?<![A-Za-z])KS\s*([A-Z])\s*(\d{4})(?!\d)(?:\s*[:：]\s*((?:19|20)\d{2})(?!\d))?")

_STATUS_ORDER = {"outdated": 0, "unknown": 1, "info": 2, "current": 3}
_KIND_ORDER = {"admrule": 0, "plan_date": 1, "law": 2, "code": 3, "obsolete_name": 4, "ks": 5}
_CITATION_KINDS = {"admrule", "law", "code", "obsolete_name"}
_PLAN_MARK_RE = re.compile(r"품\s*질\s*(?:관\s*리|시\s*험)\s*계\s*획")   # 품질관리계획·품질시험계획(띄어쓰기 변형)
NOT_PLAN_NOTE = "품질관리계획서로 보이지 않음 — 맞는 파일인지 확인"


# ---------- 기준표 스냅샷 ----------

def load_snapshot(path: str | Path | None = None) -> dict:
    """동봉 기준표 스냅샷을 읽는다. 형식이 틀리면 ValueError."""
    data = yaml.safe_load(Path(path or SNAPSHOT_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("기준표 스냅샷이 키-값 형식이 아님")
    return data


def _iso(value) -> str | None:
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _to_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _code_norm(prefix: str, a: str, b: str, c: str, d: str | None = None) -> str:
    """정규형: 공백 한 칸, 선택 5단(예: LHCS 14 20 10 05)."""
    return f"{prefix.upper()} {a} {b} {c}" + (f" {d}" if d else "")


def _link(source, fallback: str) -> str:
    """스냅샷 source 문자열(설명이 섞일 수 있음)에서 첫 URL 을 뽑는다."""
    m = _URL_RE.search(str(source or ""))
    return m.group(0) if m else fallback


def _snapshot_codes(snapshot: dict) -> dict[str, dict]:
    out = {}
    for entry in snapshot.get("codes") or []:
        m = _CODE_RE.match(str(entry.get("code") or "").strip())
        if m:
            out[_code_norm(*m.group(1, 2, 3, 4, 5))] = entry
    return out


def _snapshot_laws(snapshot: dict) -> dict[str, dict]:
    return {re.sub(r"\s+", "", str(e.get("name") or "")): e for e in snapshot.get("laws") or []}


# ---------- 추출 ----------

def _where(text: str, start: int, end: int) -> str:
    """일치 부분을 가운데 두고 앞뒤를 붙인 ≤80자 발췌(공백은 한 칸으로)."""
    core = re.sub(r"\s+", " ", text[start:end]).strip()
    room = max(WHERE_MAX - len(core) - 2, 0)
    before = re.sub(r"\s+", " ", text[max(0, start - 60):start]).lstrip()[-(room // 2):] if room // 2 else ""
    after = re.sub(r"\s+", " ", text[end:end + 60]).rstrip()[:room - len(before) - (1 if before else 0)]
    return f"{before}{core}{after}".strip()[:WHERE_MAX]


def _parse_date(m: re.Match) -> date | None:
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _plan_dates(text: str, today: date) -> list[tuple[date, re.Match]]:
    """개정이력·작성일 근처의 날짜만 계획서 날짜 후보로 본다. 법령·고시 판 표시에 붙은 날짜는 뺀다."""
    history_spans = [(m.end(), m.end() + 400) for m in _HISTORY_RE.finditer(text)]
    out = []
    for m in _DATE_RE.finditer(text):
        d = _parse_date(m)
        if d is None or d > today:
            continue
        before = text[max(0, m.start() - 40):m.start()]
        if _LAW_MARK_BEFORE_RE.search(before) or _LAW_MARK_AFTER_RE.match(text[m.end():m.end() + 12]):
            continue
        if _NOT_PLAN_DATE_RE.search(text[max(0, m.start() - 20):m.start()].rsplit("\n", 1)[-1]):
            continue
        near = text[max(0, m.start() - 60):m.end() + 20]
        if _PLAN_DATE_KEY_RE.search(near) or any(a <= m.start() < b for a, b in history_spans):
            out.append((d, m))
    return out


def _tidy_cited(text: str, start: int, end: int) -> str:
    """인용 원문을 「」·() 짝이 맞게 다듬는다: 이름 앞 「 를 붙이고, 열린 ( 가 있으면 닫는 ) 까지 넣는다."""
    if start > 0 and text[start - 1] == "「":
        start -= 1
    if text[start:end].count("「") > text[start:end].count("」"):
        close = re.match(r"\s*」", text[end:end + 4])
        end += close.end() if close else 0
    raw = text[start:end]
    if raw.count("(") > raw.count(")"):
        close = re.match(r"\s*\)", text[end:end + 4])
        raw = raw + ")" if close is None else text[start:end + close.end()]
    if "」" in raw and "「" not in raw:
        raw = "「" + raw
    return re.sub(r"\s+", " ", raw).strip()


def _law_version(text: str, start: int, end: int) -> dict:
    """법령 이름 뒤 60자(다음 법령 이름 전까지)에서 법률/령 번호와 개정·공포·시행 날짜를 찾는다.
    날짜 앞에 조·별표·서식 표시가 있으면 그 날짜는 조문·별표 단위 개정일(article_date)이지 법령 판이 아니다."""
    window = text[end:end + 60]
    nxt = _LAW_RE.search(window)
    if nxt:
        window = window[:nxt.start()]
    ver = {"type": None, "number": None, "date": None, "article_date": None, "raw": ""}
    raw_end = 0
    num = _LAW_NUM_RE.search(window)
    if num:
        ver.update(type=num.group(1), number=int(num.group(2)))
        raw_end = num.end()
    for dm in _DATE_RE.finditer(window):
        key = _LAW_DATE_KEY_RE.match(window[dm.end():dm.end() + 12])
        before = window[max(0, dm.start() - 6):dm.start()]
        if key or re.search(r"(개정|공포|시행)\s*$", before):
            ver["article_date" if _ARTICLE_RE.search(window[:dm.start()]) else "date"] = _parse_date(dm)
            raw_end = max(raw_end, dm.end() + (key.end() if key else 0))
            break
    if ver["type"] or ver["date"] or ver["article_date"]:
        ver["raw"] = _tidy_cited(text, start, end + raw_end)
        ver["end"] = end + raw_end
    return ver


def extract_citations(text: str, snapshot: dict | None = None, *, today: date | None = None) -> list[dict]:
    """본문에서 인용을 찾아 {kind, cited, norm, where, ...} 목록(나온 순서)으로 돌려준다. 같은 인용도 나온 만큼 모두 담는다."""
    text = text or ""
    today = today or date.today()
    snapshot = snapshot or {}
    out: list[dict] = []

    def add(kind, m_start, m_end, cited, norm, **extra):
        out.append({"kind": kind, "cited": re.sub(r"\s+", " ", cited).strip(), "norm": norm,
                    "where": _where(text, m_start, m_end), "pos": m_start, **extra})

    # 업무지침 고시 번호: 이름에 바로 붙은 번호만(이름 뒤 괄호 안, 또는 이름 바로 앞).
    # 사이에 다른 지침·기준·규정 이름이나 '및'이 끼면 결속하지 않는다 — 흩어진 표 칸은 놓쳐도 된다(오경보보다 누락).
    guideline_spans = [(g.start(), g.end()) for g in _GUIDELINE_RE.finditer(text)
                       if not _OTHER_MGMT_RE.search(text[max(0, g.start() - 12):g.start()])]
    bound: dict[int, re.Match] = {}
    for gs, ge in guideline_spans:
        after = _ADMRULE_RE.search(text, ge, ge + _BIND_GAP + 40)
        if after and after.start() - ge <= _BIND_GAP:
            gap = text[ge:after.start()]
            if not _BIND_STOP_RE.search(gap.lstrip("」』 \t\n")):
                bound[after.start()] = after
                continue
        before = [m for m in _ADMRULE_RE.finditer(text, max(0, gs - _BIND_GAP - 40), gs) if gs - m.end() <= _BIND_GAP]
        if before and not _BIND_STOP_RE.search(text[before[-1].end():gs].replace("「", "")):
            bound[before[-1].start()] = before[-1]
    for m in sorted(bound.values(), key=lambda m: m.start()):
        add("admrule", m.start(), m.end(), m.group(0), f"{m.group(1)}-{int(m.group(2))}",
            version=f"{m.group(1)}-{int(m.group(2))}")
    if not bound:                                   # 번호 인용이 하나라도 있으면 이름만 나온 곳은 알리지 않음
        for s in guideline_spans:
            add("admrule", s[0], s[1], "업무지침", "건설공사 품질관리 업무지침", version=None)

    # 계획서 최종 날짜: 후보 중 가장 늦은 것 하나
    dates = _plan_dates(text, today)
    if dates:
        d, m = max(dates, key=lambda x: x[0])
        add("plan_date", m.start(), m.end(), f"계획서 작성·개정일 {re.sub(r'\s+', ' ', m.group(0)).strip()}",
            d.isoformat(), version=d.isoformat())

    # 건설기술 진흥법·시행령·시행규칙
    for m in _LAW_RE.finditer(text):
        name, expected = _LAW_KIND[m.group(1)]
        ver = _law_version(text, m.start(), m.end())
        if ver["type"] or ver["date"] or ver["article_date"]:
            label = " ".join(x for x in (f"{ver['type']} 제{ver['number']}호" if ver["type"] else "",
                                          ver["date"].isoformat() if ver["date"] else "",
                                          f"조문·별표 {ver['article_date'].isoformat()}" if ver["article_date"] else "") if x)
            add("law", m.start(), ver["end"], ver["raw"], name, version=label, law_type=ver["type"],
                law_number=ver["number"], law_date=ver["date"], article_date=ver["article_date"], expected_type=expected)
        else:
            add("law", m.start(), m.end(), _tidy_cited(text, m.start(), m.end()), name, version=None)

    # KCS·KDS·LHCS
    for m in _CODE_RE.finditer(text):
        add("code", m.start(), m.end(), m.group(0), _code_norm(*m.group(1, 2, 3, 4, 5)), version=m.group(6))

    # 폐지·통합된 옛 이름(스냅샷 목록): 글자 사이 띄어쓰기 차이는 허용, 겹치면 긴 이름(예: ~법 시행령)만
    hits = []
    for entry in snapshot.get("obsolete_names") or []:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        pat = r"\s*".join(re.escape(ch) for ch in name if not ch.isspace())
        hits += [(m, name, entry) for m in re.finditer(pat, text)]
    taken: list[tuple[int, int]] = []
    for m, name, entry in sorted(hits, key=lambda h: h[0].start() - h[0].end()):
        if any(m.start() < b and a < m.end() for a, b in taken):
            continue
        taken.append((m.start(), m.end()))
        add("obsolete_name", m.start(), m.end(), m.group(0), name, version=None, entry=entry)

    # KS 번호(목록만)
    for m in _KS_RE.finditer(text):
        add("ks", m.start(), m.end(), m.group(0), f"KS {m.group(1)} {m.group(2)}", version=m.group(3))

    out.sort(key=lambda c: c["pos"])
    return out


# ---------- 판정 ----------

def _current_guideline(fetch, snapshot: dict) -> dict:
    """현행 업무지침: 미러를 먼저 보고, 실패하거나 스냅샷이 더 새 번호면 스냅샷 revisions[0] 을 쓴다."""
    revs = ((snapshot.get("admrules") or {}).get("quality_guideline") or {}).get("revisions") or []
    snap = None
    if revs and revs[0].get("number"):
        try:
            number_key(str(revs[0]["number"]))
            snap = {"number": str(revs[0]["number"]), "effective_date": _iso(revs[0].get("effective")),
                    "source": [revs[0].get("source") or OFFICIAL_URL], "via": "snapshot", "reason": "", "check_error": None,
                    "transition": revs[0].get("transition")}
        except ValueError:
            snap = None
    try:
        cur = read_current_guideline(fetch)
        if cur["in_force"] != "Y":
            raise ValueError(f"미러 문서의 현행여부가 'Y'가 아님({cur['in_force']!r})")
        mirror = {"number": cur["number"], "effective_date": cur["effective_date"],
                  "source": [MIRROR_URL, OFFICIAL_URL], "via": "mirror", "reason": "", "check_error": None, "transition": None}
    except Exception as exc:  # 네트워크·형식 문제 → 스냅샷으로 대체. 예외 이름은 message 가 아니라 check_error 에
        offline = isinstance(exc, OSError) and str(exc) == "offline"      # CLI --offline 이 넣는 fetch
        reason = "인터넷 확인은 하지 않음(--offline)" if offline else "인터넷 확인 실패"
        error = None if offline else f"{type(exc).__name__}: {exc}"
        if snap is None:
            return {"number": None, "effective_date": None, "source": [OFFICIAL_URL], "via": None,
                    "reason": f"{reason}, 내장 기준표에도 없음", "check_error": error, "transition": None}
        snap.update(reason=reason, check_error=error)
        return snap
    if snap and number_key(snap["number"]) > number_key(mirror["number"]):
        snap["reason"] = f"인터넷 사본(제{mirror['number']}호)이 아직 갱신되지 않은 것으로 보임"
        return snap
    if snap and number_key(snap["number"]) == number_key(mirror["number"]):
        mirror["transition"] = snap.get("transition")
    return mirror


def _guideline_label(g: dict) -> str:
    return f"건설공사 품질관리 업무지침 제{g['number']}호(시행 {g['effective_date'] or '미상'})"


def _replan_action(g: dict) -> str:
    t = g.get("transition")
    return (f"개정 업무지침 부칙의 기존 품질관리계획 재수립 기한 확인(기준표: {t})" if t
            else "개정 업무지침 부칙에서 기존 품질관리계획 재수립 기한 확인")


# advice 는 다음 행동과 공식 링크만 담는다. 인용(cited)·현행(current)·위치(where)는 CLI 가 따로 보여 준다.

def _judge_admrule(c: dict, g: dict) -> dict:
    link = _link(g["source"][-1], OFFICIAL_URL)
    if c["version"] is None:
        return {"status": "info", "current": _guideline_label(g) if g["number"] else None,
                "advice": f"판(고시 번호) 표시를 넣는 것을 권함. 공식 확인: {link}"}
    if not g["number"]:
        return {"status": "unknown", "current": None,
                "advice": f"현행 업무지침을 확인하지 못함 — 공식 페이지에서 인용한 번호가 현행인지 직접 대조: {OFFICIAL_URL}"}
    cited, cur = number_key(c["version"]), number_key(g["number"])
    label = _guideline_label(g)
    if cited < cur:
        return {"status": "outdated", "current": label,
                "advice": f"근거 판을 현행으로 고치고, {_replan_action(g)}, 별표2 시험 종목·빈도 변경분을 계획서 해당 절에 반영. 공식 확인: {link}"}
    if cited > cur:
        return {"status": "unknown", "current": label,
                "advice": f"인용 번호가 확인된 현행보다 새 번호 — 내장 기준표·인터넷 사본이 늦게 갱신됐거나 오기일 수 있어 공식 페이지에서 확인: {OFFICIAL_URL}"}
    return {"status": "current", "current": label, "advice": ""}


def _judge_plan_date(c: dict, g: dict, cites_current: bool) -> dict:
    eff = _to_date(g.get("effective_date"))
    if not eff:
        return {"status": "info", "current": None,
                "advice": "현행 업무지침 시행일을 확인하지 못해 계획서 날짜와 비교하지 못함."}
    label = _guideline_label(g)
    if _to_date(c["norm"]) < eff and not cites_current:
        return {"status": "outdated", "current": label,
                "advice": f"계획서 작성 뒤 업무지침이 개정됨 — {_replan_action(g)} 후 계획서를 현행 기준으로 재수립·변경 승인. "
                          f"공식 확인: {_link(g['source'][-1], OFFICIAL_URL)}"}
    if _to_date(c["norm"]) < eff:
        return {"status": "current", "current": label,
                "advice": "현행 시행일 전 날짜지만 현행 고시 번호를 인용하고 있음."}
    return {"status": "current", "current": label, "advice": ""}


def _judge_law(c: dict, laws: dict[str, dict]) -> dict:
    entry = laws.get(c["norm"].replace(" ", ""))
    link = _link((entry or {}).get("source"), LAW_URL + c["norm"].replace(" ", ""))
    cur = (entry or {}).get("current") or {}
    cur_num_m = _LAW_NUM_RE.search(str(cur.get("number") or ""))
    promulgated, effective = _to_date(cur.get("promulgated")), _to_date(cur.get("effective"))
    label = None
    if cur_num_m or promulgated:
        label = " ".join(x for x in (
            f"{c['norm']} {cur_num_m.group(1)} 제{cur_num_m.group(2)}호" if cur_num_m else c["norm"],
            f"(공포 {promulgated.isoformat()}" + (f", 시행 {effective.isoformat()})" if effective else ")") if promulgated else "") if x)
    if c["version"] is None:
        return {"status": "info", "current": label,
                "advice": f"판 표시 없음 — 인용한 조문이 현행과 맞는지 필요하면 확인: {link}"}
    if c.get("law_type") in _OLD_MINISTRY:
        return {"status": "outdated", "current": label,
                "advice": f"{c['law_type']}는 옛 부처 이름 — 판 표시를 현행 {c.get('expected_type')} 번호로 고치고 인용 조문이 현행과 맞는지 확인. 공식 확인: {link}"}
    if c.get("law_type") is None and c.get("law_date") is None:
        return {"status": "unknown", "current": label,
                "advice": f"별표·조문 단위 개정일은 도구가 판정하지 않음 — 법제처 해당 법령의 별표·연혁에서 이 날짜 뒤 개정이 있었는지 확인: {link}"}
    if not label:
        return {"status": "unknown", "current": None,
                "advice": f"기준표에 현행 판이 없어 판정하지 못함 — 공식 확인: {link}"}
    outdated = False
    if c.get("law_number") is not None and cur_num_m and c.get("law_type") == cur_num_m.group(1):
        cited_n, cur_n = c["law_number"], int(cur_num_m.group(2))
        if cited_n > cur_n:
            return {"status": "unknown", "current": label,
                    "advice": f"인용 번호가 기준표의 현행보다 새 번호 — 기준표 갱신 지연일 수 있음. 공식 확인: {link}"}
        outdated = cited_n < cur_n
    elif c.get("law_date") and promulgated:
        outdated = c["law_date"] < promulgated
    else:
        return {"status": "unknown", "current": label,
                "advice": f"판 표시의 종류가 {c.get('expected_type')}가 아니라 비교하지 못함 — 공식 확인: {link}"}
    if outdated:
        return {"status": "outdated", "current": label,
                "advice": f"판 표시를 현행으로 고치고, 인용한 조문(품질관리계획 수립·시험 관련)이 개정으로 바뀌었는지 신구조문대비표로 확인. 공식 확인: {link}"}
    return {"status": "current", "current": label, "advice": ""}


def _judge_code(c: dict, codes: dict[str, dict]) -> dict:
    entry = codes.get(c["norm"])
    if not entry or entry.get("verified") is not True:
        why = "기준표에 없음" if not entry else "기준표에서 공식 출처로 확인되지 않음"
        return {"status": "unknown", "current": None,
                "advice": f"{why} — 국가건설기준센터에서 현행판·폐지 여부 확인: {KCSC_URL}"
                          + (" (LHCS 는 LH 전문시방서 공개본)" if c["norm"].startswith("LHCS") else "")}
    link = _link(entry.get("source"), KCSC_URL)
    cur_year = str(entry.get("current") or "").strip() or None
    label = f"{c['norm']} : {cur_year}" if cur_year else c["norm"]
    if entry.get("title"):
        label += f" {entry['title']}"           # 번호가 다른 이름으로 다시 쓰인 코드는 제목으로 구분
    if str(entry.get("status") or "current") == "withdrawn":
        repl = entry.get("replaced_by")
        return {"status": "outdated", "current": f"폐지 → {repl}" if repl else f"{label} 폐지",
                "advice": "인용을 " + ("이어받은 코드로" if repl else "현행 기준으로")
                          + f" 바꾸고 해당 절 시험·검사 내용을 새 기준과 대조. 공식 확인: {link}"}
    if c["version"] is None:
        return {"status": "info", "current": label,
                "advice": f"연도판 없이 코드만 인용됨 — 판 표시를 넣으려면 연도 추가. 공식 확인: {link}"}
    if not cur_year or not cur_year.isdigit():
        return {"status": "unknown", "current": label, "advice": f"기준표에 현행 연도판이 없음 — 공식 확인: {link}"}
    if int(c["version"]) < int(cur_year):
        return {"status": "outdated", "current": label,
                "advice": f"연도판을 고치고, 개정 내용(시험·검사 기준)이 계획서 해당 절에 영향이 있는지 확인. 공식 확인: {link}"}
    if int(c["version"]) > int(cur_year):
        return {"status": "unknown", "current": label,
                "advice": f"인용 연도판이 기준표의 현행보다 새 판 — 기준표 갱신 지연일 수 있음. 공식 확인: {link}"}
    return {"status": "current", "current": label, "advice": ""}


def _judge_obsolete(c: dict) -> dict:
    e = c["entry"]
    repl, since, link = e.get("replaced_by"), _iso(e.get("since")), _link(e.get("source"), OFFICIAL_URL)
    return {"status": "outdated", "current": repl,
            "advice": ("" if not since else f"{since}부터 폐지·통합된 이름 — ")
                      + f"이름과 근거 조문을 현행 기준으로 고침. 공식 확인: {link}"}


def looks_like_plan(text: str) -> bool:
    """본문에 '품질관리계획'·'품질시험계획' 표현이 있으면 품질관리계획서로 본다(공문·양식 등 엉뚱한 파일 가려내기)."""
    return bool(_PLAN_MARK_RE.search(text or ""))


def _guideline_line(g: dict, snapshot: dict, notes: list[str]) -> str:
    """message 한 줄: 현행 업무지침 번호·시행일과 그 출처."""
    snap_day = _iso(snapshot.get("checked_at")) or "미상"
    if not g["number"]:
        line = f"현행 업무지침을 확인하지 못함({g.get('reason') or '출처 없음'}) — 공식 페이지에서 확인: {OFFICIAL_URL}"
    elif g["via"] == "mirror":
        line = f"현행 업무지침 제{g['number']}호(시행 {g['effective_date'] or '미상'}) — 인터넷(공개 법령 사본)으로 확인"
    else:
        why = f" — {g['reason']}" if g.get("reason") else ""
        line = f"현행 업무지침 제{g['number']}호(시행 {g['effective_date'] or '미상'}) — 내장 기준표(확인일 {snap_day})로 판정{why}"
    return " · ".join([line] + notes)


def check_plan(text: str, *, snapshot: dict | None = None, fetch: Callable[[str], str] | None = None,
               today: date | None = None) -> dict:
    """계획서 본문의 인용을 현행과 비교한다. 네트워크·스냅샷 문제는 예외 대신 결과(status·message)에 담는다.
    결과는 JSON 으로 바로 직렬화된다(날짜는 ISO 문자열). 요약 문장은 CLI 가 만든다."""
    today = today or date.today()
    notes = []
    snapshot_error = None
    if snapshot is None:
        try:
            snapshot = load_snapshot()
        except Exception as exc:
            snapshot = {}
            notes.append("내장 기준표를 읽지 못함")
            snapshot_error = f"{type(exc).__name__}: {exc}"

    citations = extract_citations(text, snapshot, today=today)
    is_plan = looks_like_plan(text)
    need_guideline = any(c["kind"] in ("admrule", "plan_date") for c in citations)
    g = _current_guideline(fetch, snapshot)
    laws, codes = _snapshot_laws(snapshot), _snapshot_codes(snapshot)
    cites_current = bool(g["number"]) and any(
        c["kind"] == "admrule" and c["version"] and number_key(c["version"]) == number_key(g["number"]) for c in citations)

    groups: dict[tuple, dict] = {}
    for c in citations:
        key = (c["kind"], c["norm"], c["version"])
        if key in groups:
            groups[key]["count"] += 1
            continue
        if c["kind"] == "admrule":
            verdict = _judge_admrule(c, g)
        elif c["kind"] == "plan_date" and not is_plan:     # 계획서가 아닌 문서의 날짜로는 재수립 판정을 하지 않는다
            verdict = {"status": "info", "current": None,
                       "advice": "품질관리계획서로 보이지 않아 이 날짜로 업무지침 개정 여부를 판정하지 않음."}
        elif c["kind"] == "plan_date":
            verdict = _judge_plan_date(c, g, cites_current)
        elif c["kind"] == "law":
            verdict = _judge_law(c, laws)
        elif c["kind"] == "code":
            verdict = _judge_code(c, codes)
        elif c["kind"] == "obsolete_name":
            verdict = _judge_obsolete(c)
        else:
            verdict = {"status": "info", "current": None,
                       "advice": f"KS 개정·폐지는 이 도구가 판정하지 않음 — e-나라표준인증에서 확인: {KS_URL}"}
        groups[key] = {"kind": c["kind"], "cited": c["cited"], "norm": c["norm"], "version": c["version"],
                       "current": verdict["current"], "status": verdict["status"], "where": c["where"],
                       "count": 1, "advice": verdict["advice"]}

    findings = sorted(groups.values(), key=lambda f: (_STATUS_ORDER[f["status"]], _KIND_ORDER[f["kind"]], f["norm"]))
    counts = {s: sum(f["status"] == s for f in findings) for s in ("outdated", "unknown", "info", "current")}
    counts["citations"] = sum(f["count"] for f in findings if f["kind"] in _CITATION_KINDS)
    counts["ks"] = sum(f["kind"] == "ks" for f in findings)

    if counts["outdated"]:
        status = "outdated"
    elif counts["citations"] == 0 or (need_guideline and not g["number"]):
        status = "unknown"
    else:
        status = "current"

    return {
        "status": status,
        "checked_at": today.isoformat(),
        "snapshot_checked_at": _iso(snapshot.get("checked_at")),
        "current_guideline": {k: g.get(k) for k in ("number", "effective_date", "source", "via", "check_error")},
        "snapshot_error": snapshot_error,
        "findings": findings,
        "counts": counts,
        "looks_like_plan": is_plan,
        "message": ("" if is_plan else NOT_PLAN_NOTE + " · ") + _guideline_line(g, snapshot, notes),
    }
