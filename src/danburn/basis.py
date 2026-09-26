"""근거 고시 판 확인: 규칙의 basis_version 고시 번호를 현행 「건설공사 품질관리 업무지침」과 비교한다.

현행 판은 공개 미러 legalize-kr/admrule-kr 의 본문.md 머리말(발령번호·시행일자·현행여부)에서 읽는다.
요청에는 공개 법령 경로만 넣고 사용자 파일·경로는 넣지 않는다.
미러에 오기가 있었던 적이 있으므로(R3 §5) 결과는 알림일 뿐, 규칙 갱신은 사람이 공식 PDF로 확인한 뒤 한다.
"""
from __future__ import annotations

import re
import urllib.request
from datetime import date
from typing import Callable
from urllib.parse import quote

import yaml

from .model import Rule

MIRROR_PATH = "국토교통부/_본부/고시/건설공사 품질관리 업무지침/본문.md"
MIRROR_URL = "https://raw.githubusercontent.com/legalize-kr/admrule-kr/main/" + quote(MIRROR_PATH)
OFFICIAL_URL = "https://www.law.go.kr/행정규칙/건설공사품질관리업무지침"
TIMEOUT_SECONDS = 5

_NUMBER_RE = re.compile(r"고시\s*제\s*(\d{4})\s*-\s*(\d+)\s*호")
_BARE_NUMBER_RE = re.compile(r"^(\d{4})-(\d+)$")

OUTDATED_ADVICE = (
    "업무지침 부칙(기존 품질관리계획은 개정 시행 후 60일 내 재수립) 확인, "
    "별표2 레미콘·철근 행 변경 여부는 사람이 공식 별표2 PDF로 확인한 뒤 src/danburn/data/rules 갱신"
)


def _default_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "danburn-check-basis"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8")


def _parse_front_matter(text: str) -> dict:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("머리말(---)로 시작하지 않음")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise ValueError("머리말 끝(---)이 없음") from None
    meta = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(meta, dict):
        raise ValueError("머리말이 키-값 형식이 아님")
    return meta


def _number_key(number: str) -> tuple[int, int]:
    m = _BARE_NUMBER_RE.match(number)
    if not m:
        raise ValueError(f"고시 번호 형식이 아님: {number!r}")
    return int(m.group(1)), int(m.group(2))


def _ours(rules: dict[str, Rule]) -> list[dict]:
    """규칙마다 basis_version 에서 첫 고시 번호(현재 판)를 뽑는다. 뒤따르는 번호는 비교 대상 판이라 쓰지 않는다."""
    out = []
    for key in sorted(rules):
        if rules[key].owner:            # 발주처 규칙(예: LHCS)은 업무지침 고시 번호 비교 대상이 아니다
            continue
        m = _NUMBER_RE.search(rules[key].basis_version)
        out.append({"material": key, "number": f"{m.group(1)}-{m.group(2)}" if m else None})
    return out


def check_basis(rules: dict[str, Rule], *, fetch: Callable[[str], str] | None = None,
                today: date | None = None) -> dict:
    """규칙 근거 판이 현행 고시와 같은지 본다. 네트워크·형식 문제는 예외 대신 status='unknown' 으로 돌려준다."""
    result = {
        "status": "unknown",
        "current": {"number": None, "effective_date": None, "source": [MIRROR_URL, OFFICIAL_URL]},
        "ours": _ours(rules),
        "checked_at": (today or date.today()).isoformat(),
        "message": "",
    }

    try:
        text = (fetch or _default_fetch)(MIRROR_URL)
        meta = _parse_front_matter(text)
        number = str(meta.get("발령번호") or "").strip()
        current_key = _number_key(number)
        effective = meta.get("시행일자")
        effective = effective.isoformat() if isinstance(effective, date) else (str(effective) if effective else None)
        in_force = str(meta.get("현행여부") or "").strip()
    except Exception as exc:  # 네트워크 실패·시간 초과·형식 이상 모두 unknown
        result["message"] = f"현행 판을 확인하지 못함({type(exc).__name__}: {exc}). 공식 페이지에서 직접 확인: {OFFICIAL_URL}"
        return result

    result["current"].update(number=number, effective_date=effective)
    if in_force != "Y":
        result["message"] = f"미러 문서의 현행여부가 'Y'가 아님({in_force!r}). 공식 페이지에서 직접 확인: {OFFICIAL_URL}"
        return result

    ours = result["ours"]
    missing = [o["material"] for o in ours if o["number"] is None]
    if not ours or missing:
        result["message"] = f"basis_version 에서 고시 번호를 찾지 못한 규칙: {missing or '(규칙 없음)'}"
        return result

    older = [o for o in ours if _number_key(o["number"]) < current_key]
    newer = [o for o in ours if _number_key(o["number"]) > current_key]
    current_label = f"제{number}호(시행 {effective})"
    if older:
        names = ", ".join(f"{o['material']}(제{o['number']}호)" for o in older)
        result["status"] = "outdated"
        result["message"] = f"개정됨 — 현행 {current_label}, 규칙 {names}. {OUTDATED_ADVICE}."
    elif newer:
        names = ", ".join(f"{o['material']}(제{o['number']}호)" for o in newer)
        result["message"] = f"규칙 {names} 이 미러의 현행 {current_label}보다 새 번호임 — 미러 갱신 지연 또는 오기일 수 있어 공식 페이지 확인: {OFFICIAL_URL}"
    else:
        result["status"] = "current"
        result["message"] = f"현행 판과 같음 — {current_label}."
    return result
