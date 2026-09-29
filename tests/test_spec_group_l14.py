"""L14-C3 규격 묶음: 시공 조건만 다른 규격은 한 행, 제품 규격이 다르면 따로 남는다(합성 내역 행)."""
from pathlib import Path

import pytest

from danburn.calc import aggregate
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES_DIR = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"


@pytest.fixture(scope="module")
def rules():   # --owner LH 와 같은 거름(맨홀뚜껑은 LH 규칙)
    return {k: r for k, r in load_rules(RULES_DIR).items() if not r.owner or r.owner == "LH"}


def _mats(rules, rows, disc="토목"):
    lines = [BoqLine(disc, "합성", i + 1, n, s, u, q, "", "사급") for i, (n, s, u, q) in enumerate(rows)]
    mats, _ = aggregate(lines, rules)
    return sorted((m.material, m.spec, m.unit, round(m.qty, 2)) for m in mats)


def test_condition_only_variants_merge(rules):
    assert _mats(rules, [("시스템비계 설치 해체", "10M 이하", "M2", 100), ("시스템비계 설치 해체", "10M 초과 ~ 20M 이하", "M2", 50)], "건축") \
        == [("temp_system_scaffold", "전체", "m2", 150)]
    assert _mats(rules, [("어스앵커 천공 및 강선삽입", "토사(타격식), 천공구경 105MM", "M", 30),
                         ("어스앵커 천공 및 강선삽입", "연암(타격식), 천공구경 105MM", "M", 20)]) == [("pc_strand", "전체", "m", 50)]
    assert _mats(rules, [("시트방수", "(바닥)", "M2", 40), ("시트방수", "수직부위", "M2", 4)], "건축") \
        == [("polymer_waterproof_sheet", "전체", "m2", 44)]


def test_scaffold_units_stay_apart(rules):
    """㎡ 비계와 ㎥ 동바리는 환산 근거가 없어 단위별 행으로 남는다."""
    got = _mats(rules, [("시스템비계 설치 해체", "10M 이하", "M2", 100), ("조립식강관동바리(시스템동바리)", "(H:4.2~10M) 1개월", "M3", 70)], "건축")
    assert got == [("temp_system_scaffold", "전체", "m2", 100), ("temp_system_scaffold", "전체", "m3", 70)]


def test_form_plywood_keeps_coated_apart(rules):
    got = _mats(rules, [("합판거푸집", "3회, 복잡", "M2", 30), ("합판거푸집", "4회, 보통", "M2", 20),
                        ("제치장코팅합판 거푸집", "(6회)", "M2", 10)], "건축")
    assert got == [("form_plywood", "표면가공(코팅)합판", "m2", 10), ("form_plywood", "합판", "m2", 50)]


def test_earthwork_not_grouped(rules):
    """보류: 되메우기·터파기는 설비→토목 토공 이관(L7-E3)이 규격으로 짝을 맞추므로 묶지 않는다."""
    assert _mats(rules, [("터파기 (사질토)", "90도, 보통", "M3", 10), ("터파기 (사질토)", "135도, 불량", "M3", 5)]) \
        == [("excavation_bearing", "135도,불량", "m3", 5), ("excavation_bearing", "90도,보통", "m3", 10)]
    assert len(_mats(rules, [("되메우기 (사질토)", "90도,보통", "M3", 100), ("되메우기 (사질토)", "90도, 불량", "M3", 50)])) == 2


def test_frost_subbase_base_course_apart(rules):
    got = _mats(rules, [("혼합골재(채취상차도)", "보조기층용", "M3", 30), ("포장하부 보조기층", "인력시공,T-75CM", "M3", 3),
                        ("L형측구 포장하부 동상방지층", "인력식 소규모 장비사용 시공", "M3", 2), ("혼합골재(채취상차도)", "기층용", "M3", 9)])
    assert got == [("frost_subbase", "기층용", "m3", 9), ("frost_subbase", "보조기층·동상방지층", "m3", 35)]


def test_product_sizes_stay_apart(rules):
    """호칭이 다른 제품(맨홀뚜껑 D900·D1200, 경계석 단면)은 묶지 않는다 — 설치 깊이·곡선/직선만 묶는다."""
    got = _mats(rules, [("원형맨홀,주철제뚜껑", "D900 (h=1.82M)", "개소", 3), ("원형맨홀,주철제뚜껑", "D900 (h=2.14M)", "개소", 2),
                        ("원형맨홀,주철제뚜껑", "D1200 (h=2.60M)", "개소", 1)])
    assert got == [("lh_manhole_cover", "D1200", "개소", 1), ("lh_manhole_cover", "D900", "개소", 5)]
    got = _mats(rules, [("도로경계석", "합성,곡선,150×150×1,000mm", "개", 5), ("도로경계석", "합성,직선,150×150×1,000mm", "개", 7),
                        ("보차도경계석", "합성,직선,180×200×1,000mm", "개", 4)])
    assert got == [("curb_block", "150X150X1000", "ea", 12), ("curb_block", "180X200X1000", "ea", 4)]


def test_interlocking_block_not_grouped(rules):
    """보류: 투수·불투수와 두께(제품)가 규격·품명에 섞여 있어 묶지 않는다."""
    got = _mats(rules, [("인조화강석블록(보도용)", "불투수, T60", "M2", 10), ("인조화강석블록(보도용)", "200x200xT60mm, 투수", "M2", 20)])
    assert len(got) == 2 and all(m[0] == "interlocking_block" for m in got)


def test_stone_by_quarry_and_no_separate_supply_rows(rules):
    got = _mats(rules, [("화강석판석", "포천석, 연마 30T", "M2", 50), ("화강석판석", "포천석,혼드 25T", "M2", 10),
                        ("석재바닥판깔기(석재별도, 건조모르타르포함)", "(바탕20MM, 건조시멘트모르타르)", "M2", 99)], "건축")
    assert [m for m in got if m[0] == "stone"] == [("stone", "포천석", "m2", 60)]   # 석재별도 시공 행은 석재 수량에 안 들어간다
    assert ("dry_cement_mortar", "자재 포함 시공 행", "ton", 0) in got               # 그 행은 건조모르타르(포함 자재)로 간다


def test_cement_transport_row_not_counted(rules):
    got = _mats(rules, [("시멘트(점포상차도)", "40KG", "포", 100), ("시멘트 수송비", "20KM까지", "포", 100)])
    assert len(got) == 1 and got[0][:2] == ("portland_cement", "전체")


def test_no_obsolete_names_in_rule_methods():
    """규칙 시험방법에 폐지·통합된 옛 기준 명칭(standards_snapshot obsolete_names)이 없다 — danburn check 가 outdated 로 잡는다."""
    import re
    import yaml
    snap = yaml.safe_load((RULES_DIR.parent / "standards_snapshot.yaml").read_text(encoding="utf-8"))
    pats = [re.compile(r"\s*".join(re.escape(c) for c in e["name"] if not c.isspace())) for e in snap["obsolete_names"]]
    hits = [(k, t.test_type, t.method) for k, r in load_rules(RULES_DIR).items() for t in r.tests
            if any(p.search(t.method) for p in pats)]
    assert not hits, hits


def test_ductile_pipe_ks_items_substituted_in_group():
    r = load_rules(RULES_DIR)["lh_ductile_iron_pipe"]
    assert r.group_tests and r.ks_mark and r.ks_count == "makers"
    assert {t.test_type for t in r.tests if t.ks_substitute} == {"KS D 4311에 규정된 시험종목"}


# L14-C6(hate 채택): 두께·종호·종류·지름 같은 제품 규격은 묶지 않는다 — 시공 조건만 뗀다
def test_eps_thickness_stays_apart(rules):
    rows = [("PS(비드법) 단열재 벽체붙이기(접착)", f"(비드법2종2호{t}mm)", "M2", q) for t, q in ((30, 200), (45, 300), (125, 400))]
    got = _mats(rules, rows, "건축")
    assert got == [("lh_eps_insulation", "비드법2종2호125MM", "m2", 400), ("lh_eps_insulation", "비드법2종2호30MM", "m2", 200),
                   ("lh_eps_insulation", "비드법2종2호45MM", "m2", 300)]
    same = _mats(rules, [("비드법 단열재", "비드법2종2호, 25MM", "M2", 10), ("비드법 단열재", "비드법2종2호25MM(벽체)", "M2", 5)], "건축")
    assert same == [("lh_eps_insulation", "비드법2종2호25MM", "m2", 15)]      # 같은 제품의 표기·부위 차이는 한 행


def test_gypsum_board_thickness_and_type_apart(rules):
    got = _mats(rules, [("석고보드", "벽9.5MM", "M2", 100), ("석고보드", "9.5X900X1800", "M2", 20), ("석고보드", "벽12.5MM", "M2", 30),
                        ("방수석고보드", "9.5방수석고보드", "M2", 7)], "건축")
    assert got == [("gypsum_board", "12.5T", "m2", 30), ("gypsum_board", "9.5T", "m2", 120), ("gypsum_board", "방수9.5T", "m2", 7)]


def test_other_product_specs_apart(rules):
    assert len(_mats(rules, [("복층유리", "22MM,실링재별도", "M2", 10), ("복층유리", "아르곤,22MM,실링재별도", "M2", 10),
                             ("복층유리", "아르곤,24MM,실링재별도", "M2", 10)], "건축")) == 3
    assert len(_mats(rules, [("경질폴리염화비닐관", "D50MM(VG1)", "M", 10), ("경질폴리염화비닐관", "D75MM(VG1)", "M", 10)])) == 2
    assert _mats(rules, [("PVC계 바닥재", "T6.0", "M2", 10), ("PVC계 바닥재", "T=2MM(경보행용)", "M2", 3)], "건축") \
        == [("pvc_floor", "2T", "m2", 3), ("pvc_floor", "6.0T", "m2", 10)]


def test_paint_conditions_merge_products_apart(rules):
    got = _mats(rules, [("수성페인트", "벽2회롤러칠,바탕만들기제외", "M2", 10), ("수성페인트", "천장2회뿜칠,바탕만들기제외", "M2", 5)], "건축")
    assert got == [("water_paint", "전체", "m2", 15)]                      # 부위·칠 방법은 시공 조건
    got = _mats(rules, [("다채무늬도료", "상도", "M2", 10), ("다채무늬도료", "중도", "M2", 10)], "건축")
    assert [m[1] for m in got] == ["상도", "중도"]


def test_unmatched_group_names_say_what_is_missing(rules):
    """L14-C7: 패턴에 안 걸린 행은 '규격별' 대신 뜻이 보이는 이름(두께 기준은 '두께 미기재', 그 밖 '규격 미기재')."""
    assert _mats(rules, [("석고보드", "(규격 없음)", "M2", 5)], "건축") == [("gypsum_board", "두께 미기재", "m2", 5)]
    assert _mats(rules, [("경질폴리염화비닐관", "", "M", 5)]) == [("general_pvc_pipe", "규격 미기재", "m", 5)]
    assert _mats(rules, [("경질폴리염화비닐관", "D=35", "M", 5), ("경질폴리염화비닐관", "D=50", "M", 5)]) \
        == [("general_pvc_pipe", "D=35", "m", 5), ("general_pvc_pipe", "D=50", "m", 5)]
    for k, r in load_rules(RULES_DIR).items():
        assert not (r.spec_group == "pattern" and r.spec_group_other == "규격별"), k
