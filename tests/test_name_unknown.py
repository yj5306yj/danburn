"""다른 자재 이름 아래 가려지는 행(L7-E8): 품명에 색인 종별이 없고 규격에서만 걸린 행은 그 종별로 확정하지 않는다."""
from __future__ import annotations

import json

import openpyxl
import pytest

from danburn.cli import main
from danburn.index import coverage, is_cost, line_keys
from danburn.model import BoqLine

PIPE = "수도용 닥타일 주철직관(KP식 2종)"


def _xlsx(path, extra_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "내역(건)"
    for r in [["품명", "규격", "단위", "수량"], ["레미콘", "25-24-15", "M3", 500], ["포틀랜드시멘트", "1종", "포", 200],
              *extra_rows]:
        ws.append(r)
    wb.save(path)
    return path


def _run(tmp_path, capsys, extra_rows, *args):
    src = _xlsx(tmp_path / "b.xlsx", extra_rows)
    out = tmp_path / "o.hwpx"
    assert main(["build", "--boq", str(src), "--out", str(out), "--offline", *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_first_nail_pipe_not_hidden_under_cement(tmp_path, capsys):
    """재현: 규격 '시멘트라이닝' 때문에 주철관 행이 포틀랜드 시멘트(이미 행 있음)로 묶여 어디에도 안 나왔다."""
    summary = _run(tmp_path, capsys, [[PIPE, "시멘트라이닝", "M", 120]])
    assert any(PIPE in w and w.startswith("품명으로 자재를 알 수 없음") and "시멘트" in w for w in summary["warnings"])
    ask = [x for x in summary["ask"] if x["kind"] == "name_unknown"]
    assert [x["label"] for x in ask] == [PIPE]
    assert all(x["label"] != "포틀랜드 시멘트" for x in summary["ask"])
    nu = {x["name"]: x for x in summary["name_unknown"]}
    assert nu[PIPE]["spec_word"] == "시멘트" and nu[PIPE]["guess"]["key"] == "portland_cement"


def test_name_identified_rows_unchanged():
    line = BoqLine("건축", "x", 1, "포틀랜드시멘트", "1종", "포", 1.0, "", "사급")
    assert line_keys(line) == ["portland_cement"]
    cov = coverage([line], matched=lambda ln: False)
    assert [u["key"] for u in cov["unmatched_in_covered"] + cov["uncovered"]] == ["portland_cement"]
    assert cov["name_unknown"] == []


def test_spec_only_rows_bucketed_even_when_rule_key_exists():
    line = BoqLine("건축", "x", 1, PIPE, "시멘트라이닝", "M", 1.0, "", "사급")
    assert line_keys(line) == []                       # 규격만으로는 종별 확정 안 함(현장 확인 강제 매칭에도 안 쓰임)
    cov = coverage([line], covered_keys=frozenset({"portland_cement"}), matched=lambda ln: False)
    assert cov["unmatched_in_covered"] == [] and cov["uncovered"] == [] and cov["labor_only"] == []
    assert [(u["name"], u["spec_word"]) for u in cov["name_unknown"]] == [(PIPE, "시멘트")]


def test_ks_number_in_spec_is_still_trusted():
    line = BoqLine("건축", "x", 1, "벽체용 제품", "KS F 4004", "EA", 1.0, "", "사급")
    assert line_keys(line) == ["concrete_brick"]
    cov = coverage([line], matched=lambda ln: False)
    assert cov["name_unknown"] == [] and [u["key"] for u in cov["uncovered"] + cov["unmatched_in_covered"]] == ["concrete_brick"]


def test_rule_matched_rows_untouched(tmp_path, capsys):
    # 규칙이 실제로 잡은 행(규격 매칭 포함)은 그대로 — 거푸집 + 규격 합판
    summary = _run(tmp_path, capsys, [["거푸집 (합성공종)", "합판6회, 간단", "M2", 30]])
    assert not summary["name_unknown"]


@pytest.mark.parametrize("name,cost", [
    ("콘크리트 양생비", True), ("고속도로 통행료(철근,공장⇒현장)", True), ("강관동바리 손료", True),
    ("자재 운반비", True), ("품질 시험비", True), ("용수비", True), ("현장 잡비", True),
    ("경비실 출입문", False), ("레미콘", False), ("섬유보강재(투입비포함)", False),
])
def test_cost_words(name, cost):
    assert is_cost(name) is cost


def test_cost_rows_not_asked_or_warned(tmp_path, capsys):
    summary = _run(tmp_path, capsys, [["콘크리트 양생비", "", "M3", 500], ["고속도로 통행료(철근)", "", "회", 3]])
    assert not [x for x in summary["ask"] if "양생비" in x["label"] or "통행료" in str(x["examples"])]
    assert not any("양생비" in w or "통행료" in w for w in summary["warnings"])


def test_answers_for_name_unknown(tmp_path, capsys):
    key = f"name:{PIPE}"
    summary = _run(tmp_path, capsys, [[PIPE, "시멘트라이닝", "M", 120]], "--confirm", f"{key}=예")
    assert any(x["name"] == PIPE for x in summary["name_unknown_confirmed"])
    assert not any(w.startswith("품명으로 자재를 알 수 없음") for w in summary["warnings"])
    assert any(w.startswith("발주처 기준 필요") and PIPE in w for w in summary["warnings"])
    summary = _run(tmp_path, capsys, [[PIPE, "시멘트라이닝", "M", 120]], "--confirm", f"{key}=아니오")
    assert [x["key"] for x in summary["confirmed_excluded"]] == [key]
    assert not any(PIPE in w for w in summary["warnings"])
    assert not [x for x in summary["ask"] if x["kind"] == "name_unknown"]


def test_name_item_answered_with_material_key(tmp_path, capsys):
    """사용자 결정(E7): '섬유보강재가 강섬유인가' — 품명 확인 행은 고른 종별 규칙으로 넣을 수 있다."""
    row = ["콘크리트 섬유보강재(투입비포함)", "(셀룰로오스,나일론,강섬유)", "M3", 40]
    summary = _run(tmp_path, capsys, [row])
    ask = {x["label"]: x for x in summary["ask"] if x["kind"] == "name_unknown"}
    assert "steel_fiber" in ask[row[0]]["choices"]
    summary = _run(tmp_path, capsys, [row], "--confirm", f"name:{row[0]}=steel_fiber")
    assert {"key": f"name:{row[0]}", "rule": "steel_fiber", "lines": 1} in summary["confirmed_included"]
    assert not any(row[0] in w for w in summary["warnings"])
    rows = json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))
    assert [r["note"] for r in rows if r["material"] == "steel_fiber"] and "현장 확인으로 포함" in \
        [r["note"] for r in rows if r["material"] == "steel_fiber"][0]


def test_key_answer_does_not_pull_spec_only_rows(tmp_path, capsys):
    """'portland_cement=예' 가 규격 '시멘트라이닝' 주철관을 시멘트로 끌어오지 않는다."""
    summary = _run(tmp_path, capsys, [[PIPE, "시멘트라이닝", "M", 120]], "--confirm", "portland_cement=예")
    assert any(PIPE in w for w in summary["warnings"] if w.startswith("품명으로 자재를 알 수 없음"))


def test_spec_only_install_row_still_visible():
    line = BoqLine("건축", "x", 1, "화장실칸막이 설치", "파티클보드", "M2", 1.0, "", "사급")
    cov = coverage([line], matched=lambda ln: False)
    assert cov["name_unknown"] and cov["name_unknown"][0]["install"] is True


def test_install_name_item_hidden_when_guess_already_in_811(tmp_path, capsys):
    """설치 행뿐인 품명은 추정 종별이 이미 8.11 에 있으면 묻지 않는다(요약에는 shown=False 로 남음)."""
    summary = _run(tmp_path, capsys, [["벽체 보강 설치", "시멘트", "M2", 10], ["칸막이 설치", "파티클보드", "M2", 10]])
    nu = {u["name"]: u for u in summary["name_unknown"]}
    assert nu["벽체 보강 설치"]["install"] and nu["벽체 보강 설치"]["shown"] is False     # 시멘트는 이미 산출됨
    assert nu["칸막이 설치"]["shown"] is True                                             # 파티클보드는 행 없음
    asked = {x["label"] for x in summary["ask"] if x["kind"] == "name_unknown"}
    assert asked == {"칸막이 설치"}


def test_rule_miss_asked_only_when_no_811_row(tmp_path, capsys):
    """L7-E9: 이미 8.11 행이 있는 종별(시멘트)의 나머지 규칙 밖 행은 묻지 않고 요약에만."""
    summary = _run(tmp_path, capsys, [["포틀랜드시멘트 특수포장", "1종", "EA", 5]])     # 단위가 규칙 밖 → 규칙 밖 행
    miss = {u["key"]: u for u in summary["unmatched_in_covered"]}
    assert miss["portland_cement"]["produced"] is True
    assert "portland_cement" not in {x["key"] for x in summary["ask"]}


def test_all_spec_matches_become_guesses(tmp_path, capsys):
    """L7-E9: 규격에 종별이 여럿이면 추정 목록·선택지에 모두. 하나라도 8.11 에 없으면 설치 행도 묻는다."""
    summary = _run(tmp_path, capsys, [["조립식 프레임 설치", "연강판 1.2T, 방청도료 2회", "M2", 10]])
    nu = {u["name"]: u for u in summary["name_unknown"]}["조립식 프레임 설치"]
    keys = [g["key"] for g in nu["guesses"]]
    assert {"hot_rolled_mild_sheet", "anticorrosive_paint"} <= set(keys) and nu["guess"]["key"] == keys[0]
    ask = {x["label"]: x for x in summary["ask"] if x["kind"] == "name_unknown"}["조립식 프레임 설치"]
    assert "hot_rolled_mild_sheet" in ask["choices"]          # 규칙이 있는 추정만 '넣기' 선택지
    assert {"예", "아니오", "나중에"} <= set(ask["choices"])


def test_same_guess_items_grouped_and_one_answer_covers_all(tmp_path, capsys):
    """L7-E9: 추정 종별이 같은 품명들은 한 질문, 묶음 key 로 답하면 모두에 적용."""
    rows = [["합성 트렌치", "강판 3T", "M", 10], ["합성 집수정", "강판 5T", "개소", 2]]
    summary = _run(tmp_path, capsys, rows)
    ask = [x for x in summary["ask"] if x["kind"] == "name_unknown"]
    assert len(ask) == 1 and ask[0]["names"] == ["합성 트렌치", "합성 집수정"] and ask[0]["label"] == "합성 트렌치 외 1품명"
    gkey = ask[0]["key"]
    assert len([w for w in summary["warnings"] if w.startswith("품명으로 자재를 알 수 없음")]) == 1
    summary = _run(tmp_path, capsys, rows, "--confirm", f"{gkey}=아니오")
    assert {x["label"] for x in summary["confirmed_excluded"]} == {"합성 트렌치", "합성 집수정"}
    assert not [x for x in summary["ask"] if x["kind"] == "name_unknown"]
    material = [k for k in ask[0]["choices"] if k not in ("예", "아니오", "나중에")][0]
    summary = _run(tmp_path, capsys, rows, "--confirm", f"{gkey}={material}")
    inc = {x["key"]: x for x in summary["confirmed_included"]}
    assert sum(x["lines"] for x in inc.values()) == 2
