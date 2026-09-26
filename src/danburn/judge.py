"""품질관리계획·품질시험계획 대상 판정(순수 함수). 설계: 조사 L7-S1 §1.3.

근거(법제처 원문, 2026-09-26 조회 — L7-S1 §1):
- 「건설기술 진흥법」 제55조제1항(계획 수립·발주자 승인, 발주청이 아닌 발주자는 사본을 인·허가기관의 장에게 제출)
- 같은 법 시행령 제89조제1항(품질관리계획 대상) 1호 건설사업관리 대상 + 총공사비 500억원 이상,
  2호 다중이용 건축물 + 연면적 3만㎡ 이상, 3호 계약에 품질관리계획 수립이 정해진 공사
- 같은 영 제89조제2항(품질시험계획 대상, 제1항 대상이 아닐 때) 1호 총공사비 5억원 이상 토목공사,
  2호 연면적 660㎡ 이상 건축물의 건축공사, 3호 총공사비 2억원 이상 전문공사
- 같은 영 제89조제3항·같은 법 시행규칙 제49조(원자력시설공사, 조경식재공사, 철거공사 — 설계도서에서 정하면 수립)
- 「건축법 시행령」 제2조제17호(다중이용 건축물: 16층 이상, 또는 정해진 용도 바닥면적 합계 5천㎡ 이상)
- 같은 법 시행규칙 제50조제4항·별표5(품질관리 건설기술인·시험실 배치기준: 특급·고급·중급·초급)

"모름"(None)은 추측하지 않는다: 가능한 값을 모두 넣어 결과를 모으고, 결과가 갈리면 그 답을 `확인필요`로 드러낸다.
"""
from __future__ import annotations

import itertools
import re

LAW = "「건설기술 진흥법」"
DECREE = "같은 법 시행령"
MULTI_USES = ("문화집회", "종교", "판매", "여객운수", "종합병원", "관광숙박")   # 건축법 시행령 제2조제17호가목
EXEMPT = ("조경식재", "철거", "원자력")
YES, NO = "예", "아니오"

GRADES = {   # 시행규칙 별표5
    "특급": ("50㎡ 이상", "품질관리 경력 3년 이상 특급 1명 + 중급 이상 1명 + 초급 이상 1명"),
    "고급": ("50㎡ 이상", "품질관리 경력 2년 이상 고급 이상 1명 + 중급 이상 1명 + 초급 이상 1명"),
    "중급": ("18㎡ 이상", "품질관리 경력 1년 이상 중급 이상 1명 + 초급 이상 1명"),
    "초급": ("18㎡ 이상", "초급 이상 1명"),
}
GAP = "별표5에 직접 해당 줄 없음 — 계약·발주자 요구 확인"
NOT_APPLICABLE = "해당 없음"

QMP, QTP = "품질관리계획", "품질시험계획"
EXEMPTED = "수립하지 않을 수 있음"
NOT_TARGET = "법정 대상 아님"
ORDER = [QMP, QTP, EXEMPTED, NOT_TARGET]          # 넓은 쪽부터(모르면 넓은 쪽 문서를 만든다)

# 모르는 숫자는 판정 경계 사이 대표값으로 모두 넣어 본다
COST_BANDS = [1, 3, 50, 200, 700, 1500]            # 억원: 2·5·100·500·1000 경계
AREA_BANDS = [100, 1000, 10000, 40000, 60000]      # ㎡: 660·5천·3만·5만 경계
FLOOR_BANDS = [1, 20]                              # 층: 16 경계


def number(v) -> float | None:
    """'40,000.00㎡(합성 값)'·'1,200'·1200 → 숫자. 빈 값·'-'·'모름'은 None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(v))
    return float(m.group(0).replace(",", "")) if m else None


def tri(v) -> bool | None:
    """예/아니오/모름 → True/False/None."""
    if isinstance(v, bool):
        return v
    s = str(v or "").strip()
    if s in (YES, "Y", "y", "yes", "true", "True", "1"):
        return True
    if s in (NO, "N", "n", "no", "false", "False", "0"):
        return False
    return None


def _kinds(v) -> set[str]:
    s = str(v or "").strip()
    if not s:
        return set()
    return {k for k in ("건축", "토목", "전문", *EXEMPT) if k in s}


def _outcome(cost, area, floors, multi_use, multi_area, cm, contract, kinds, exempt):
    """모든 답이 정해졌을 때 (계획, 등급, 근거 목록)."""
    multi = floors >= 16 or (multi_use and multi_area >= 5000)
    qmp1 = cm and cost >= 500
    qmp2 = multi and area >= 30000
    reasons = []
    if exempt and not contract:
        return EXEMPTED, NOT_APPLICABLE, [f"{DECREE} 제89조제3항·같은 법 시행규칙 제49조({exempt} 공사)"]
    if qmp1 or qmp2 or contract:
        plan = QMP
        if qmp1:
            reasons.append(f"{DECREE} 제89조제1항제1호(건설사업관리 대상, 총공사비 500억원 이상)")
        if qmp2:
            why = "16층 이상" if floors >= 16 else "다중이용 용도 바닥면적 5천㎡ 이상"
            reasons.append(f"{DECREE} 제89조제1항제2호(다중이용 건축물 — {why}, 연면적 3만㎡ 이상)")
        if contract:
            reasons.append(f"{DECREE} 제89조제1항제3호(계약에 품질관리계획 수립이 정해진 공사)")
    else:
        hits = []
        if "토목" in kinds and cost >= 5:
            hits.append(f"{DECREE} 제89조제2항제1호(총공사비 5억원 이상 토목공사)")
        if "건축" in kinds and area >= 660:
            hits.append(f"{DECREE} 제89조제2항제2호(연면적 660㎡ 이상 건축공사)")
        if "전문" in kinds and cost >= 2:
            hits.append(f"{DECREE} 제89조제2항제3호(총공사비 2억원 이상 전문공사)")
        if not hits:
            return NOT_TARGET, NOT_APPLICABLE, []
        plan, reasons = QTP, hits
    if (qmp1 or qmp2) and (cost >= 1000 or (multi and area >= 50000)):
        grade = "특급"
    elif qmp1 or qmp2:
        grade = "고급"
    elif cost >= 100 or (multi and area >= 5000):
        grade = "중급"
    elif plan == QTP:
        grade = "초급"
    else:
        grade = GAP
    return plan, grade, reasons


def judge(ans: dict) -> dict:
    """판정. ans 키: 발주자_구분·공사종류·총공사비_억원·연면적·지상층수·주용도·다중용도_바닥면적·
    건설사업관리_대상·계약_품질관리계획(예/아니오/모름). 없는 답은 모름으로 본다.

    반환: 계획종류·계획종류_확정·가능한_결과·근거·작성근거·품질관리_대상등급·시험실·인력기준·
    승인절차_문장·확인필요.
    """
    cost, area, floors = number(ans.get("총공사비_억원")), number(ans.get("연면적")), number(ans.get("지상층수"))
    multi_area = number(ans.get("다중용도_바닥면적"))
    use = str(ans.get("주용도") or "").strip()
    kinds = _kinds(ans.get("공사종류"))
    exempt = next((k for k in EXEMPT if k in kinds), "")
    if exempt:
        kinds -= {exempt}
    axes = {   # 이름 → 가능한 값들(모르면 여럿)
        "총공사비_억원": [cost] if cost is not None else COST_BANDS,
        "연면적": [area] if area is not None else AREA_BANDS,
        "지상층수": [floors] if floors is not None else FLOOR_BANDS,
        "주용도": [any(u in use for u in MULTI_USES)] if use else [False, True],
        "다중용도_바닥면적": [multi_area] if multi_area is not None else [None],
        "건설사업관리_대상": [tri(ans.get("건설사업관리_대상"))] if tri(ans.get("건설사업관리_대상")) is not None
        else [False, True],
        "계약_품질관리계획": [tri(ans.get("계약_품질관리계획"))] if tri(ans.get("계약_품질관리계획")) is not None
        else [False, True],
        "공사종류": [frozenset(kinds)] if kinds or exempt else [frozenset({"건축"}), frozenset({"토목"}), frozenset({"전문"})],
    }
    names = list(axes)
    results = {}
    for combo in itertools.product(*axes.values()):
        v = dict(zip(names, combo))
        m_area = v["다중용도_바닥면적"] if v["다중용도_바닥면적"] is not None else v["연면적"]   # 모르면 연면적까지로 본다
        results[combo] = _outcome(v["총공사비_억원"], v["연면적"], v["지상층수"], v["주용도"], m_area,
                                  v["건설사업관리_대상"], v["계약_품질관리계획"], v["공사종류"], exempt)
    outcomes = {(p, g) for p, g, _ in results.values()}
    plans = sorted({p for p, _ in outcomes}, key=ORDER.index)
    plan = plans[0]
    grades = sorted({g for p, g in outcomes if p == plan}, key=lambda g: list(GRADES).index(g) if g in GRADES else 9)

    # 결과를 가르는 답(나머지를 고정했을 때 이 답만 바꿔 결과가 달라지면)
    need = []
    labels = {"총공사비_억원": "총공사비(억원, 관급자재 포함·보상비 제외)", "연면적": "연면적(㎡)",
              "지상층수": "지상 최고 층수", "주용도": "주 용도(판매·문화집회·종합병원·관광숙박 등인지)",
              "건설사업관리_대상": "감독 권한대행 등 건설사업관리 대상인지",
              "계약_품질관리계획": "계약서·설계도서에 품질관리계획 수립 조항이 있는지", "공사종류": "공사 종류"}
    for i, n in enumerate(names):
        if len(axes[n]) < 2:
            continue
        groups: dict = {}
        for combo, (p, g, _) in results.items():
            groups.setdefault(combo[:i] + combo[i + 1:], set()).add((p, g))
        if any(len(s) > 1 for s in groups.values()):
            need.append(f"{labels[n]} — 답에 따라 판정이 달라짐")
    if use and any(u in use for u in MULTI_USES) and multi_area is None and floors is not None and floors < 16:
        need.append("다중이용 용도 바닥면적 합계가 5천㎡ 이상인지(연면적으로 대신 판정함)")
    if kinds >= {"건축", "토목"} and plan == QTP:
        need.append("건축+토목 복합 공사: 품질시험계획 기준은 공종별 — 발주자 확인 권장")

    confirmed = len(outcomes) == 1
    # 근거는 모든 경우에 공통인 조항만(모르는 답이 '예'일 때만 성립하는 조항은 쓰지 않는다)
    same = [set(rs) for p, g, rs in results.values() if (p, g) == (plan, grades[0])]
    reasons = sorted(set.intersection(*same)) if confirmed and same else []
    grade = grades[0] if len(grades) == 1 else f"확인 필요(가능: {'·'.join(grades)})"
    room, staff = GRADES.get(grades[0], ("", "")) if len(grades) == 1 else ("확인 필요", "확인 필요")
    if grade == GAP:
        need.append("배치등급: " + GAP)
    if plan == QTP:
        need.append("품질시험계획 대상 — 표지 제목은 '품질시험계획서'로 하되 본문은 품질관리계획서 구성(1~10장)으로 작성됨"
                    "(영 별표9의 개요·시험계획·시험시설·인력 배치계획보다 넓음)")
    if not confirmed:
        need.append("가능한 결과: " + " / ".join(f"{p}·{g}" for p, g in sorted(outcomes, key=lambda x: ORDER.index(x[0]))))

    if plan == EXEMPTED:
        basis = f"{DECREE} 제89조제3항·같은 법 시행규칙 제49조 — 수립하지 않을 수 있는 공사이나 계약·설계도서 요구로 작성"
    elif confirmed and reasons:
        basis = f"{LAW} 제55조제1항, " + ", ".join(reasons)
    elif plan in (QMP, QTP):
        basis = f"{LAW} 제55조제1항, {DECREE} 제89조(해당 호는 확인 필요)"
    else:
        basis = f"{LAW} 제55조제1항의 법정 대상은 아니나 계약·발주자 요구에 따라 작성"
    return {
        "계획종류": plan, "계획종류_확정": confirmed and len(plans) == 1,
        "가능한_결과": [{"계획종류": p, "품질관리_대상등급": g} for p, g in sorted(outcomes, key=lambda x: ORDER.index(x[0]))],
        "근거": reasons, "작성근거": basis, "품질관리_대상등급": grade,
        "시험실": room or NOT_APPLICABLE, "인력기준": staff or NOT_APPLICABLE,
        "승인절차_문장": approval_sentence(ans.get("발주자_구분")), "확인필요": need,
    }


def decides(ans: dict, key: str, values=("예", "아니오")) -> bool:
    """key 의 답을 values 로 바꿔 볼 때 계획 종류·배치 등급(가능한 결과 전체)이 달라지면 True.

    danburn start 가 조건부 질문을 '답에 따라 결과가 달라질 때만' 묻는 데 쓴다(다른 모르는 답은 모두 열거한 채로 비교)."""
    seen = set()
    for v in values:
        r = judge({**ans, key: v})
        seen.add(frozenset((x["계획종류"], x["품질관리_대상등급"]) for x in r["가능한_결과"]))
    return len(seen) > 1


def approval_sentence(kind) -> str:
    """발주청/민간/모름에 따른 승인 절차 문장(법 제55조제1항, 영 제90조제1항).

    템플릿(L7-C5)이 문장 사이에 넣으므로 번호·글머리 없이 '다.'로 끝나는 완결 문장(들)로 쓴다."""
    base = ("본 계획서는 착공 전에 공사감독자 또는 건설사업관리기술인의 검토·확인을 받아 발주자의 승인을 받으며, "
            f"내용을 변경할 때도 같다({LAW} 제55조제1항, {DECREE} 제90조제1항).")
    s = str(kind or "").strip()
    if s in ("민간", "아니오", "발주청 아님"):
        return base + f" 발주자가 발주청이 아니므로 계획서 사본을 미리 인·허가기관의 장에게 제출한다({LAW} 제55조제1항 후단)."
    if s in ("발주청", "예", "공공"):
        return base
    return base + f" 발주자가 발주청이 아니면 계획서 사본을 미리 인·허가기관의 장에게 제출한다({LAW} 제55조제1항 후단)."
