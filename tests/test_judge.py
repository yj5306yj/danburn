"""품질관리계획·품질시험계획 판정(L7-I1, 설계 L7-S1 §1.3) — 경계값·예외·모름·빈틈."""
import pytest

from danburn.judge import EXEMPTED, GAP, NOT_TARGET, QMP, QTP, approval_sentence, judge, number


def J(**kw):
    base = dict(발주자_구분="발주청", 공사종류="건축", 건설사업관리_대상="아니오", 계약_품질관리계획="아니오",
                주용도="공동주택", 지상층수=10, 연면적=1000, 총공사비_억원=10)
    base.update(kw)
    return judge(base)


@pytest.mark.parametrize("cost,cm,plan,grade", [
    (499, "예", QTP, "중급"),                 # 영 89①1: 500억 미만이면 아님(100억 이상 → 중급)
    (500, "예", QMP, "고급"),                 # 500억 이상 + 건설사업관리 → 품질관리계획·고급
    (999, "예", QMP, "고급"),
    (1000, "예", QMP, "특급"),                # 별표5: 1,000억 이상 → 특급
    (1000, "아니오", QTP, "중급"),            # 건설사업관리 대상 아니면 ①1호 아님
])
def test_cost_boundaries(cost, cm, plan, grade):
    r = J(총공사비_억원=cost, 건설사업관리_대상=cm)
    assert (r["계획종류"], r["품질관리_대상등급"]) == (plan, grade) and r["계획종류_확정"]


@pytest.mark.parametrize("area,floors,plan,grade", [
    (29999, 20, QTP, "중급"),                 # 다중이용이지만 3만㎡ 미만 → 품질시험계획, 다중 5천㎡ 이상 → 중급
    (30000, 20, QMP, "고급"),                 # 영 89①2
    (49999, 16, QMP, "고급"),
    (50000, 16, QMP, "특급"),                 # 별표5: 다중이용 5만㎡ 이상 → 특급
    (40000, 15, QTP, "초급"),                 # 15층 공동주택은 다중이용 아님
])
def test_area_floor_boundaries(area, floors, plan, grade):
    r = J(연면적=area, 지상층수=floors)
    assert (r["계획종류"], r["품질관리_대상등급"]) == (plan, grade)


def test_multi_use_by_floor_area():
    assert J(연면적=40000, 지상층수=5, 주용도="판매", 다중용도_바닥면적=6000)["계획종류"] == QMP
    assert J(연면적=40000, 지상층수=5, 주용도="판매", 다중용도_바닥면적=4000)["계획종류"] == QTP


@pytest.mark.parametrize("kind,cost,area,plan", [
    ("건축", 1, 660, QTP), ("건축", 1, 659, NOT_TARGET),          # 영 89②2
    ("토목", 5, 0, QTP), ("토목", 4.9, 0, NOT_TARGET),           # 영 89②1
    ("전문", 2, 0, QTP), ("전문", 1.9, 0, NOT_TARGET),           # 영 89②3
])
def test_quality_test_plan_thresholds(kind, cost, area, plan):
    r = J(공사종류=kind, 총공사비_억원=cost, 연면적=area)
    assert r["계획종류"] == plan
    if plan == QTP:
        assert r["품질관리_대상등급"] == "초급" and r["시험실"] == "18㎡ 이상"


def test_exempt_works_unless_contract():
    r = J(공사종류="철거", 총공사비_억원=50)
    assert r["계획종류"] == EXEMPTED and "시행규칙 제49조" in r["작성근거"]
    assert J(공사종류="조경식재", 계약_품질관리계획="예")["계획종류"] == QMP     # 설계도서·계약이 정하면 수립


def test_contract_only_gap_is_shown_not_guessed():
    r = J(계약_품질관리계획="예", 총공사비_억원=50, 연면적=3000)
    assert r["계획종류"] == QMP and r["품질관리_대상등급"] == GAP
    assert any("별표5" in n for n in r["확인필요"])
    assert "제89조제1항제3호" in r["작성근거"]


def test_unknown_answers_enumerate_and_flag_only_deciding_ones():
    r = judge(dict(공사종류="건축", 총공사비_억원=800, 연면적=40000, 지상층수=10, 계약_품질관리계획="아니오"))
    assert not r["계획종류_확정"] and r["계획종류"] == QMP                      # 넓은 쪽 문서
    assert {x["계획종류"] for x in r["가능한_결과"]} == {QMP, QTP}
    joined = " ".join(r["확인필요"])
    assert "건설사업관리 대상" in joined and "주 용도" in joined
    assert "(해당 호는 확인 필요)" in r["작성근거"]                              # 성립하지 않을 수 있는 호를 쓰지 않음
    r2 = judge(dict(공사종류="건축", 총공사비_억원=800, 연면적=40000, 지상층수=20))
    assert r2["계획종류_확정"] and "제89조제1항제2호" in r2["작성근거"] and "제1호" not in r2["작성근거"]


def test_approval_sentences_are_complete():
    pub, priv, unk = (approval_sentence(x) for x in ("발주청", "민간", "모름"))
    for s in (pub, priv, unk):
        assert s.rstrip().endswith(".") and s.split("(")[0].rstrip().endswith("다")
        assert not s.lstrip()[0].isdigit()
    assert "인·허가기관" not in pub and "제55조제1항 후단" in priv and "발주청이 아니면" in unk


def test_number_parsing():
    assert number("40,000.00㎡(합성 값)") == 40000 and number("-") is None and number(12) == 12


def test_decides_only_when_answer_changes_result():
    from danburn.judge import decides
    decided = dict(공사종류="건축", 총공사비_억원=850, 연면적=42000, 지상층수=22)       # 영 89①2호로 확정
    assert not decides(decided, "건설사업관리_대상") and not decides(decided, "계약_품질관리계획")
    assert not decides(decided, "주용도", ("공동주택", "판매"))
    split = dict(공사종류="건축", 총공사비_억원=850, 연면적=42000, 지상층수=10)
    assert decides(split, "건설사업관리_대상") and decides(split, "주용도", ("공동주택", "판매"))
    assert not decides(dict(split, 총공사비_억원=100), "건설사업관리_대상")          # 500억 미만이면 무관
