"""danburn check 인용 추출·판정(L9-C1). 본문·기준표·미러 응답은 모두 합성이며 번호·연도는 가상의 값이다."""
import json
from datetime import date

import pytest

from danburn.basis import MIRROR_URL
from danburn.plancheck import check_plan, extract_citations, load_snapshot

TODAY = date(2030, 6, 1)

SNAP = {
    "checked_at": date(2030, 5, 1),
    "admrules": {"quality_guideline": {"name": "건설공사 품질관리 업무지침", "revisions": [
        {"number": "2030-50", "effective": date(2030, 3, 1), "source": "https://example.org/guideline"},
        {"number": "2029-10", "effective": date(2029, 2, 1), "source": "https://example.org/guideline-old"},
    ]}},
    "laws": [
        {"name": "건설기술 진흥법", "current": {"number": "법률 제30000호", "promulgated": date(2030, 1, 10),
                                         "effective": date(2030, 4, 10)}, "source": "https://example.org/act", "mirror_path": None},
        {"name": "건설기술 진흥법 시행령", "current": {"number": "대통령령 제40000호", "promulgated": date(2030, 2, 1),
                                             "effective": date(2030, 2, 1)}, "source": "https://example.org/decree", "mirror_path": None},
    ],
    "codes": [
        {"code": "KCS 14 20 10", "title": "합성 콘크리트", "current": "2029", "status": "current", "replaced_by": None,
         "source": "https://example.org/kcs1", "verified": True},
        {"code": "KCS 99 10 10", "title": "합성 폐지 코드", "current": "2020", "status": "withdrawn",
         "replaced_by": "KCS 99 20 10", "source": "https://example.org/kcs2", "verified": True},
        {"code": "KDS 88 10 10", "title": "합성 미확인", "current": "2028", "status": "current", "replaced_by": None,
         "source": "https://example.org/kds", "verified": False},
        {"code": "LHCS 10 40 00", "title": "합성 시험", "current": "2029", "status": "current", "replaced_by": None,
         "source": "https://example.org/lhcs", "verified": True},
    ],
    "obsolete_names": [
        {"name": "가상기술관리법", "replaced_by": "건설기술 진흥법", "since": date(2014, 5, 23), "source": "https://example.org/old"},
    ],
}


def _front(number="2030-50", effective="2030-03-01", in_force="Y"):
    return f"---\n발령번호: '{number}'\n시행일자: {effective}\n현행여부: '{in_force}'\n---\n본문\n"


def mirror(number="2030-50", effective="2030-03-01"):
    return lambda url: _front(number, effective)


def offline(url):
    raise TimeoutError("timed out")


def run(text, **kw):
    kw.setdefault("snapshot", SNAP)
    kw.setdefault("fetch", mirror())
    kw.setdefault("today", TODAY)
    return check_plan(text, **kw)


def only(res, kind):
    return [f for f in res["findings"] if f["kind"] == kind]


# ---------- 업무지침 ----------

@pytest.mark.parametrize("text", [
    "근거: 건설공사 품질관리 업무지침(국토교통부고시 제2029-10호)",
    "건설공사 품질관리 업무지침 국토교통부 고시 제 2029 - 10 호",
    "국토교통부고시제2029-10호 건설공사 품질관리 업무 지침",
])
def test_admrule_variants_outdated(text):
    res = run(text)
    [f] = only(res, "admrule")
    assert f["status"] == "outdated" and f["norm"] == "2029-10"
    assert res["status"] == "outdated"
    assert "2030-50" in f["current"]
    assert "부칙" in f["advice"] and "재수립" in f["advice"]
    assert "공식 확인" in f["advice"]


def test_admrule_current_and_mirror_url_only():
    seen = []
    res = run("건설공사 품질관리 업무지침(고시 제2030-50호) 비밀본문", fetch=lambda url: seen.append(url) or _front())
    assert seen == [MIRROR_URL]                        # 계획서 글은 요청에 들어가지 않는다
    assert res["status"] == "current"
    assert res["current_guideline"]["via"] == "mirror"


def test_admrule_far_from_guideline_ignored():
    text = "건설공사 품질관리 업무지침 준수." + "가" * 200 + "다른 규정 고시 제2001-1호"
    res = run(text)
    [f] = only(res, "admrule")
    assert f["status"] == "info"                       # 이름만 있음
    assert "2001-1" not in json.dumps(res, ensure_ascii=False)


def test_admrule_numeric_compare_and_newer():
    assert only(run("업무지침 고시 제2030-9호"), "admrule")[0]["status"] == "outdated"
    assert only(run("업무지침 고시 제2030-100호"), "admrule")[0]["status"] == "unknown"


def test_advice_has_no_invented_deadline():
    f = only(run("업무지침(고시 제2029-10호)"), "admrule")[0]
    assert "부칙" in f["advice"] and "60일" not in f["advice"]
    snap = json.loads(json.dumps(SNAP, default=str))
    snap["admrules"]["quality_guideline"]["revisions"][0]["transition"] = "합성 기한 문구"
    f = only(run("업무지침(고시 제2029-10호)", snapshot=snap), "admrule")[0]
    assert "합성 기한 문구" in f["advice"]


def test_mirror_fail_falls_back_to_snapshot():
    res = run("업무지침(고시 제2029-10호)", fetch=offline)
    assert res["status"] == "outdated"
    assert res["current_guideline"]["via"] == "snapshot"
    assert res["current_guideline"]["number"] == "2030-50"
    assert res["message"].endswith("— 내장 기준표(확인일 2030-05-01)로 판정 — 인터넷 확인 실패")
    assert "TimeoutError" not in res["message"] and "TimeoutError" in res["current_guideline"]["check_error"]


def test_snapshot_newer_than_mirror_wins():
    res = run("업무지침(고시 제2029-10호)", fetch=mirror("2029-10", "2029-02-01"))
    assert res["current_guideline"]["number"] == "2030-50"
    assert only(res, "admrule")[0]["status"] == "outdated"


def test_guideline_total_failure_is_unknown():
    res = run("업무지침(고시 제2029-10호) KCS 14 20 10 : 2029", fetch=offline, snapshot={"codes": SNAP["codes"]})
    assert res["status"] == "unknown"
    assert res["current_guideline"]["number"] is None
    assert only(res, "admrule")[0]["status"] == "unknown"


# ---------- 계획서 날짜 ----------

@pytest.mark.parametrize("stamp,iso", [
    ("2029. 01. 05.", "2029-01-05"),
    ("2029-01-05", "2029-01-05"),
    ("2029년 1월 5일", "2029-01-05"),
    ("2029.1.5", "2029-01-05"),
])
def test_plan_date_formats(stamp, iso):
    res = run(f"품질관리계획서\n작성일: {stamp}")
    [f] = only(res, "plan_date")
    assert f["norm"] == iso
    assert f["status"] == "outdated"                   # 2030-03-01 시행 전 작성
    assert "재수립" in f["advice"] and "부칙" in f["advice"]


def test_plan_date_latest_future_ignored_law_dates_skipped():
    text = ("품질관리계획서 개정 이력\nRev.0 2029. 04. 01. 최초 작성\nRev.1 2030. 04. 02. 변경\nRev.2 2031. 01. 01. 예정\n"
            "건설기술 진흥법(법률 제30000호, 2030. 05. 20. 개정)")
    [f] = only(run(text), "plan_date")
    assert f["norm"] == "2030-04-02"                   # 미래(2031)·법령 판 날짜(2030-05-20) 제외
    assert f["status"] == "current"


def test_plan_date_before_effective_but_cites_current():
    res = run("품질시험계획 작성일 2030. 02. 01.\n업무지침(고시 제2030-50호)")
    assert only(res, "plan_date")[0]["status"] == "current"
    assert res["status"] == "current"


def test_no_plan_date():
    assert only(run("업무지침(고시 제2030-50호) 날짜 없음"), "plan_date") == []


# ---------- 법령 ----------

def test_law_versions():
    text = ("건설기술 진흥법(법률 제29000호)\n"
            "건설기술 진흥법 시행령(대통령령 제40000호)\n"
            "건설기술 진흥법 시행규칙(국토해양부령 제100호)\n"
            "건설기술 진흥법 제55조에 따라 수립")
    res = run(text)
    law = {(f["norm"], f["status"]) for f in only(res, "law")}
    assert ("건설기술 진흥법", "outdated") in law
    assert ("건설기술 진흥법 시행령", "current") in law
    assert ("건설기술 진흥법 시행규칙", "outdated") in law   # 옛 부처령
    assert ("건설기술 진흥법", "info") in law                 # 이름만
    old = [f for f in only(res, "law") if f["norm"] == "건설기술 진흥법" and f["status"] == "outdated"][0]
    assert "법률 제30000호" in old["current"] and "example.org/act" in old["advice"]


def test_law_date_only_and_no_snapshot_entry():
    res = run("건설기술 진흥법 (2029. 12. 1. 개정)\n건설기술 진흥법 시행규칙(국토교통부령 제5호)")
    fs = {f["norm"]: f for f in only(res, "law")}
    assert fs["건설기술 진흥법"]["status"] == "outdated"
    assert fs["건설기술 진흥법 시행규칙"]["status"] == "unknown"
    assert "law.go.kr" in fs["건설기술 진흥법 시행규칙"]["advice"]


def test_law_unrelated_date_not_version():
    [f] = only(run("건설기술 진흥법에 따라 2020. 1. 1. 수립한 계획"), "law")
    assert f["status"] == "info"


# ---------- 코드 ----------

@pytest.mark.parametrize("cited", ["KCS 14 20 10 : 2022", "KCS 14 20 10:2022", "KCS 14 20 10(2022)",
                                   "KCS14 20 10 2022", "KCS 142010 : 2022"])
def test_code_variants_outdated(cited):
    [f] = only(run(cited), "code")
    assert f["norm"] == "KCS 14 20 10" and f["version"] == "2022"
    assert f["status"] == "outdated"
    assert "2029" in f["current"] and "example.org/kcs1" in f["advice"]


def test_code_dedupe_and_count():
    res = run("KCS 14 20 10 : 2029 본문 KCS 14 20 10:2029 또 KCS 14 20 10(2029)")
    [f] = only(res, "code")
    assert f["count"] == 3 and f["status"] == "current"
    assert res["counts"]["citations"] == 3
    assert res["status"] == "current"


def test_code_no_year_withdrawn_unknown():
    res = run("KCS 14 20 10 적용\nKCS 99 10 10\nKDS 88 10 10 : 2028\nKCS 77 77 77 : 2020\nLHCS 10 40 00 : 2029")
    fs = {f["norm"]: f for f in only(res, "code")}
    assert fs["KCS 14 20 10"]["status"] == "info"
    assert fs["KCS 99 10 10"]["status"] == "outdated" and "KCS 99 20 10" in fs["KCS 99 10 10"]["current"]
    assert fs["KDS 88 10 10"]["status"] == "unknown"          # verified: false
    assert fs["KCS 77 77 77"]["status"] == "unknown"          # 기준표에 없음
    assert "기준표에 없음" in fs["KCS 77 77 77"]["advice"]
    assert fs["LHCS 10 40 00"]["status"] == "current"
    assert res["status"] == "outdated"


def test_unknown_code_alone_does_not_fail():
    res = run("KCS 77 77 77 : 2020")
    assert res["status"] == "current"
    assert res["counts"]["unknown"] == 1


# ---------- 옛 이름·KS ----------

def test_obsolete_name():
    res = run("가상기술 관리법 제24조에 따라")
    [f] = only(res, "obsolete_name")
    assert f["status"] == "outdated" and f["current"] == "건설기술 진흥법"
    assert "2014-05-23" in f["advice"]
    assert res["status"] == "outdated"


def test_ks_listed_only():
    res = run("KS F 2405 및 KS D 3504:2021, KS F 2405 KCS 14 20 10 : 2029")
    ks = only(res, "ks")
    assert {f["norm"] for f in ks} == {"KS F 2405", "KS D 3504"}
    assert all(f["status"] == "info" and "e-나라표준인증" in f["advice"] for f in ks)
    assert res["status"] == "current"
    assert all(f["norm"] != "KS C 14" for f in ks)            # KCS 는 KS 로 잡지 않는다


# ---------- 전체 ----------

def test_empty_text_is_unknown():
    for text in ("", "   \n", "인용이 없는 합성 본문"):
        res = run(text, fetch=offline)
        assert res["status"] == "unknown"
        assert res["findings"] == [] or all(f["kind"] == "plan_date" for f in res["findings"])
        assert res["counts"]["citations"] == 0


def test_where_excerpt_bounded():
    text = "가" * 300 + " KCS 14 20 10 : 2022 " + "나" * 300
    f = only(run(text), "code")[0]
    assert "KCS 14 20 10" in f["where"] and len(f["where"]) <= 80


def test_extract_citations_shape():
    cs = extract_citations("업무지침(고시 제2030-50호) KCS 14 20 10 : 2029", SNAP, today=TODAY)
    assert [c["kind"] for c in cs] == ["admrule", "code"]
    assert all({"kind", "cited", "norm", "where"} <= set(c) for c in cs)


def test_result_is_json_serializable():
    text = ("개정 이력 2029. 01. 05. 작성\n업무지침(고시 제2029-10호)\n건설기술 진흥법(법률 제29000호)\n"
            "KCS 14 20 10 : 2022\nKCS 99 10 10\n가상기술관리법\nKS F 2405")
    for fetch in (mirror(), offline):
        res = run(text, fetch=fetch)
        back = json.loads(json.dumps(res, ensure_ascii=False))
        assert back == res
        assert res["snapshot_checked_at"] == "2030-05-01"
        assert isinstance(res["current_guideline"]["effective_date"], str)


def test_load_snapshot(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("checked_at: 2030-05-01\ncodes: []\n", encoding="utf-8")
    assert load_snapshot(p)["checked_at"] == date(2030, 5, 1)
    p.write_text("- a\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_snapshot(p)


def test_missing_snapshot_file_is_reported(monkeypatch, tmp_path):
    import danburn.plancheck as pc
    monkeypatch.setattr(pc, "SNAPSHOT_PATH", tmp_path / "none.yaml")
    res = check_plan("KCS 14 20 10 : 2022", fetch=offline, today=TODAY)
    assert "내장 기준표를 읽지 못함" in res["message"] and "FileNotFoundError" not in res["message"]
    assert res["snapshot_error"].startswith("FileNotFoundError")
    assert only(res, "code")[0]["status"] == "unknown"


# ---------- L9-C2 검수 수정 ----------

ARTICLE_TEXT = "품질관리계획은 「건설기술 진흥법 시행규칙」 제50조제4항·별표5(2024. 7. 10. 개정)에 따라 작성한다."


def test_f1_article_level_date_is_not_law_version():
    snap = dict(SNAP, laws=SNAP["laws"] + [{"name": "건설기술 진흥법 시행규칙", "current": {
        "number": "국토교통부령 제2000호", "promulgated": date(2030, 1, 1), "effective": date(2030, 1, 1)},
        "source": "https://example.org/rule"}])
    res = run(ARTICLE_TEXT, snapshot=snap)
    [f] = only(res, "law")
    assert f["status"] == "unknown"                    # 수정 전: 공포일(2030-01-01)과 비교해 outdated
    assert "별표·조문 단위 개정일은 도구가 판정하지 않음" in f["advice"] and "example.org/rule" in f["advice"]
    assert res["status"] == "current"


def test_f1_law_level_date_and_number_still_judged():
    fs = only(run("「건설기술 진흥법」(2029. 12. 1. 개정) 제55조"), "law")
    assert [f["status"] for f in fs] == ["outdated"]
    fs = only(run("「건설기술 진흥법 시행령」(대통령령 제39000호) 별표1(2029. 1. 1. 개정)"), "law")
    assert [f["status"] for f in fs] == ["outdated"]    # 번호는 법령 판


def test_f2_five_level_code():
    snap = dict(SNAP, codes=SNAP["codes"] + [
        {"code": "LHCS 14 20 10", "title": "합성 4단", "current": "2030", "status": "current", "verified": True, "source": "x"},
        {"code": "LHCS 14 20 10 05", "title": "합성 5단", "current": "2020", "status": "current", "verified": True, "source": "x"}])
    fs = {f["norm"]: f for f in only(run("LHCS 14 20 10 05:2020 3.12.5 및 LHCS 14 20 10 10:2020", snapshot=snap), "code")}
    assert fs["LHCS 14 20 10 05"]["status"] == "current"   # 수정 전: 4단 키로 2030 과 비교해 outdated
    assert "합성 5단" in fs["LHCS 14 20 10 05"]["current"]
    assert fs["LHCS 14 20 10 10"]["status"] == "unknown"   # 5단이 기준표에 없으면 4단으로 판정하지 않음
    assert only(run("LHCS 10 40 00 1.5.1(6)"), "code")[0]["norm"] == "LHCS 10 40 00"   # 조항 번호는 5단이 아님


def test_f3_cited_brackets_balanced():
    [f] = only(run(ARTICLE_TEXT), "law")
    assert f["cited"] == "「건설기술 진흥법 시행규칙」 제50조제4항·별표5(2024. 7. 10. 개정)"
    [f] = only(run("「건설기술 진흥법 시행령」 제90조제1항"), "law")
    assert f["cited"] == "「건설기술 진흥법 시행령」"


def test_f4_advice_is_action_and_link_only():
    res = run("업무지침(고시 제2029-10호)\n건설기술 진흥법(법률 제29000호)\nKCS 14 20 10 : 2022\n가상기술관리법")
    for f in res["findings"]:
        if f["status"] in ("outdated", "unknown"):
            assert f["cited"] not in f["advice"] and f["where"] not in f["advice"], f
            assert (f["current"] or "\0") not in f["advice"], f
            assert "http" in f["advice"], f
    code = only(res, "code")[0]
    assert code["current"] == "KCS 14 20 10 : 2029 합성 콘크리트"   # 제목은 current 에


def test_f4_link_extracted_from_source_text():
    snap = dict(SNAP, codes=[{"code": "KCS 14 20 10", "title": "t", "current": "2029", "status": "current", "verified": True,
                              "source": "KCSC https://example.org/list/1 (최종 제·개정 2029-01-01)"}])
    f = only(run("KCS 14 20 10 : 2020", snapshot=snap), "code")[0]
    assert f["advice"].endswith("https://example.org/list/1")


def test_f5_plan_date_cited_is_labelled():
    [f] = only(run("작성일: 2029. 01. 05."), "plan_date")
    assert f["cited"] == "계획서 작성·개정일 2029. 01. 05."


def test_f6_message_is_one_guideline_line():
    res = run("품질관리계획서 업무지침(고시 제2029-10호) KCS 14 20 10 : 2022")
    assert "\n" not in res["message"]
    assert res["message"] == "현행 업무지침 제2030-50호(시행 2030-03-01) — 인터넷(공개 법령 사본)으로 확인"
    assert res["current_guideline"]["check_error"] is None
    assert "개정" not in res["message"].split("—")[0].replace("업무지침", "") and "건" not in res["message"]


def test_obsolete_longest_name_only():
    snap = dict(SNAP, obsolete_names=[{"name": "가상기술관리법", "replaced_by": "A"},
                                      {"name": "가상기술관리법 시행령", "replaced_by": "B"}])
    fs = only(run("가상기술관리법 시행령 제1조, 가상기술관리법 제2조", snapshot=snap), "obsolete_name")
    assert sorted((f["norm"], f["count"]) for f in fs) == [("가상기술관리법", 1), ("가상기술관리법 시행령", 1)]


# ---------- 통합: 우리 plan 산출물을 실제 기준표로 ----------

def test_our_generated_plan_is_not_outdated(tmp_path):
    import contextlib
    import importlib.util
    import io
    from pathlib import Path

    from danburn.cli import main
    from danburn.readdoc import read_document

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("make_example_boq", root / "scripts" / "make_example_boq.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    boq = mod.build(tmp_path / "example_boq.xlsx")
    out = tmp_path / "plan.hwpx"
    with contextlib.redirect_stdout(io.StringIO()):
        main(["plan", "--boq", str(boq), "--block", "나동", "--project",
              str(root / "src" / "danburn" / "data" / "templates" / "project.example.yaml"),
              "--revision", "0", "--date", "2026. 01. 05.", "--offline", "--out", str(out)])
    res = check_plan(read_document(out).text, snapshot=load_snapshot(), fetch=offline, today=date(2026, 9, 27))
    bad = [(f["kind"], f["cited"], f["current"]) for f in res["findings"] if f["status"] == "outdated"]
    assert not [f for f in res["findings"] if f["kind"] == "admrule" and f["status"] == "info"]   # 번호 인용 있으면 이름만 알림 없음
    assert bad == [], bad
    assert res["counts"]["citations"] > 0
    json.dumps(res, ensure_ascii=False)


# ---------- L9-C3 계획서가 아닌 문서 ----------

def test_not_a_plan_date_only_is_unknown():
    res = run("협조 공문\n작성일: 2029. 01. 05.\n회신 바랍니다.")
    assert res["looks_like_plan"] is False
    assert res["status"] == "unknown"
    assert not [f for f in res["findings"] if f["status"] == "outdated"]
    assert only(res, "plan_date")[0]["status"] == "info"
    assert res["message"].startswith("품질관리계획서로 보이지 않음 — 맞는 파일인지 확인")
    assert "\n" not in res["message"]
    json.dumps(res, ensure_ascii=False)


def test_not_a_plan_old_code_still_judged():
    res = run("자재 승인 요청서 작성일 2029. 01. 05. 적용 기준 KCS 14 20 10 : 2022")
    assert res["looks_like_plan"] is False
    assert only(res, "code")[0]["status"] == "outdated"
    assert res["status"] == "outdated"


@pytest.mark.parametrize("mark", ["품질관리계획서", "품질 관리 계획", "품질시험계획", "품질 시험계획서"])
def test_plan_with_old_date_only_stays_outdated(mark):
    res = run(f"{mark}\n작성일: 2029. 01. 05.")
    assert res["looks_like_plan"] is True
    assert only(res, "plan_date")[0]["status"] == "outdated"
    assert res["status"] == "outdated"
    assert not res["message"].startswith("품질관리계획서로 보이지 않음")
    json.dumps(res, ensure_ascii=False)


# ---------- L9-C4 독립 리뷰 채택 결함 ----------

H1_TEXT = ("품질관리계획서\n적용 기준: 건설공사 품질관리 업무지침(국토교통부 고시 제2030-50호) 및 "
           "건설공사 안전관리 업무수행 지침(국토교통부 고시 제2023-58호)을 따른다.")


def test_h1_other_notice_next_to_guideline_not_bound():
    res = run(H1_TEXT)
    assert [f["norm"] for f in only(res, "admrule")] == ["2030-50"]
    assert res["status"] == "current"


@pytest.mark.parametrize("text,expected", [
    ("건설공사 품질관리 업무지침(2030. 3. 1. 시행, 국토교통부 고시 제2029-10호)", ["2029-10"]),
    ("국토교통부 고시 제2029-10호 「건설공사 품질관리 업무지침」", ["2029-10"]),
    ("「건설공사 품질관리 업무지침」(국토교통부고시 제2029-10호)", ["2029-10"]),
    ("건설공사 안전관리 업무지침(국토교통부 고시 제2029-10호)", []),            # 다른 관리 지침
    ("건설공사 품질관리 업무지침, 건설기술 진흥법 시행규칙(국토교통부 고시 제2029-10호)", []),
    ("고시 제2029-10호 「가설공사 표준시방 기준」 및 품질관리 업무지침", []),
])
def test_h1_binding_variants(text, expected):
    assert [f["norm"] for f in only(run("품질관리계획서\n" + text), "admrule") if f["version"]] == expected


def test_h1_unbound_guideline_name_stays_info():
    res = run("품질관리계획서\n건설공사 품질관리 업무지침 및 안전관리 업무수행 지침(국토교통부 고시 제2023-58호)")
    fs = only(res, "admrule")
    assert [f["status"] for f in fs] == ["info"]


@pytest.mark.parametrize("cited", ["KCS 14 20 10-2016", "KCS 14 20 10 - 2016", "KCS 14 20 10–2016", "KCS 14 20 10—2016"])
def test_h3_hyphen_year(cited):
    [f] = only(run(cited), "code")
    assert f["version"] == "2016" and f["status"] == "outdated"


def test_h3_hyphen_does_not_eat_five_level():
    [f] = only(run("LHCS 14 20 10 05-2020"), "code")
    assert f["norm"] == "LHCS 14 20 10 05" and f["version"] == "2020"


@pytest.mark.parametrize("line", ["준공 예정일자 2030.05.30", "착공일자 2030. 5. 1.", "공사기간 2030.05.01", "유효기간 만료일자 2030-05-20"])
def test_h4_schedule_dates_not_plan_date(line):
    [f] = only(run(f"품질관리계획서\n작성일: 2029. 01. 05.\n{line}"), "plan_date")
    assert f["norm"] == "2029-01-05"


def test_h4_history_table_still_used():
    text = "품질관리계획서\n개정 이력\nRev.0 2029. 04. 01. 최초 작성\nRev.1 2030. 04. 02. 준공 예정일 변경 반영"
    [f] = only(run(text), "plan_date")
    assert f["norm"] == "2030-04-02"


# ---------- L9-C5 message 에 개발 용어 없음 ----------

def _offline_cli(url):
    raise OSError("offline")                        # CLI --offline 이 넣는 fetch 와 같은 모양


@pytest.mark.parametrize("fetch,tail,err", [
    (_offline_cli, "— 내장 기준표(확인일 2030-05-01)로 판정 — 인터넷 확인은 하지 않음(--offline)", None),
    (offline, "— 내장 기준표(확인일 2030-05-01)로 판정 — 인터넷 확인 실패", "TimeoutError: timed out"),
])
def test_c5_message_plain_words(fetch, tail, err):
    res = run("품질관리계획서 업무지침(고시 제2030-50호)", fetch=fetch)
    assert res["message"] == "현행 업무지침 제2030-50호(시행 2030-03-01) " + tail
    assert res["current_guideline"]["check_error"] == err
    for word in ("미러", "OSError", "TimeoutError", "스냅샷", "동봉"):
        assert word not in res["message"]
    json.dumps(res, ensure_ascii=False)


def test_c5_total_failure_message_plain():
    res = run("품질관리계획서 업무지침(고시 제2029-10호)", fetch=_offline_cli, snapshot={})
    assert res["message"].startswith("현행 업무지침을 확인하지 못함(인터넷 확인은 하지 않음(--offline), 내장 기준표에도 없음)")
    assert "OSError" not in res["message"]
