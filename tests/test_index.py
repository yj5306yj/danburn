"""별표2 전체 종별 색인 — 식별·노무 제외·규칙 유무 구분 (합성 품명)."""
from pathlib import Path

from danburn.index import coverage, identify, is_labor, load_index
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"


def _line(name, spec="", unit="m2", qty=10.0):
    return BoqLine(discipline="건축", sheet="합성", row=1, name=name, spec=spec, unit=unit,
                   qty=qty, block="", supply="사급")


def _keys(name, spec=""):
    return [e.key for e in identify(name, spec)]


def test_index_loads_whole_table():
    index = load_index()
    assert len(index) >= 200
    parts = {e.part for e in index}
    assert parts == {"1. 공통", "2. 토목", "3. 건축"}
    assert len({e.key for e in index}) == len(index)
    assert all(1 <= e.page <= 52 for e in index)


def test_index_rules_exist():
    rules = load_rules(RULES)
    used = {e.rule for e in load_index() if e.rule}
    assert used == {"ready_mixed_concrete", "rebar"}
    assert used <= set(rules)


def test_identify_common_materials():
    assert _keys("아스콘 표층 WC-1")[0] == "asphalt_plant_mix"
    assert _keys("아스팔트 콘크리트")[0] == "asphalt_plant_mix"
    assert _keys("시멘트벽돌 190x90x57")[0] == "concrete_brick"
    assert _keys("벽돌")[0] == "concrete_brick"
    assert _keys("우레탄 도막방수")[0] == "coating_waterproofing"
    assert _keys("액체방수 2차")[0] == "liquid_waterproofing"
    assert _keys("복층유리 24mm")[0] == "insulated_glass"
    assert _keys("강화유리")[0] == "tempered_glass"
    assert _keys("성토")[0] == "fill_soil"
    assert _keys("흙쌓기(유용토)")[0] == "fill_soil"


def test_identify_longest_name_wins():
    assert _keys("점토벽돌") == ["clay_brick"]                    # '벽돌' 은 버린다
    assert _keys("노체 성토")[0] == "road_embankment"
    assert _keys("에폭시 피복철근 D16")[0] == "epoxy_coated_rebar"
    assert _keys("아스팔트 슁글")[0] == "asphalt_shingle"


def test_identify_ignores_spaces_and_uses_spec_or_ks():
    assert _keys("콘 크 리 트 벽 돌")[0] == "concrete_brick"
    assert _keys("자재", "KS F 4004")[0] == "concrete_brick"
    assert _keys("알 수 없는 품명") == []


def test_labor_rows_excluded():
    assert is_labor("레미콘 타설")
    assert is_labor("철근 가공조립")
    assert is_labor("벽돌 소운반")
    assert not is_labor("조립식맨홀 D900")                        # '조립' 이 자재 이름 안에 있다
    assert is_labor("조립식맨홀 설치")
    cov = coverage([_line("레미콘 타설", unit="m3"), _line("철근 가공조립", unit="ton"),
                    _line("보통인부", unit="인")])
    assert cov["covered"] == [] and cov["uncovered"] == []
    assert {r["key"] for r in cov["labor_only"]} == {"fresh_concrete", "hardened_concrete", "rebar"}


def test_coverage_splits_ready_and_missing():
    lines = [
        _line("레미콘", "25-24-150", "m3", 100),
        _line("철근", "SD400 D13", "ton", 5),
        _line("아스콘 표층", "", "ton", 50),
        _line("시멘트벽돌", "190x90x57", "매", 1000),
        _line("콘크리트벽돌", "", "매", 500),
        _line("우레탄 도막방수", "", "m2", 80),
        _line("복층유리", "24mm", "m2", 30),
        _line("성토", "", "m3", 900),
        _line("레미콘 타설", "", "m3", 100),
        _line("알 수 없는 품명"),
    ]
    cov = coverage(lines)
    covered = {c["key"]: c for c in cov["covered"]}
    assert set(covered) == {"fresh_concrete", "hardened_concrete", "rebar"}
    assert covered["rebar"]["lines"] == 1
    assert covered["fresh_concrete"]["lines"] == 1                # 타설 행은 빠진다
    uncovered = {u["key"]: u for u in cov["uncovered"]}
    assert set(uncovered) == {"asphalt_plant_mix", "concrete_brick", "coating_waterproofing",
                              "insulated_glass", "fill_soil"}
    brick = uncovered["concrete_brick"]
    assert brick["lines"] == 2 and brick["examples"] == ["시멘트벽돌", "콘크리트벽돌"]
    assert brick["page"] == 32 and brick["ks"] == "KS F 4004"
    assert set(brick) >= {"key", "label", "page", "lines", "examples"}


def test_index_exclude_drops_false_hits():
    assert _keys("덕타일 주철관") != ["ceramic_tile"] and "ceramic_tile" not in _keys("덕타일 주철관")
    assert "rebar" not in _keys("철근 간격재") and "rebar" not in _keys("철근고임대")
    assert "rebar" not in _keys("철근 결속선")
    assert "stone" not in _keys("석재뿜칠")
    assert _keys("화강석 판석")[0] == "stone"
    assert _keys("경질 발포 플라스틱 단열재(PUR)")[0] == "pur_foam_insulation"   # EPS 로 가지 않는다
    assert _keys("경질 발포 플라스틱 단열재")[0] == "eps_insulation"


def test_included_material_in_parentheses_ranks_last():
    assert _keys("자기질타일 붙이기(건조모르타르 포함)")[0] == "ceramic_tile"
    assert _keys("건조모르타르(타일 제외)")[0] == "dry_cement_mortar"            # '포함' 이 아닌 괄호는 그대로
    cov = coverage([_line("자기질타일 붙이기(건조모르타르 포함)")])
    assert [r["key"] for r in cov["uncovered"]] == ["ceramic_tile"]              # 포함 자재는 세지 않는다


def test_checked_synonyms_l4_g5():
    assert _keys("저소음 3층 PVC관 100mm")[0] == "foam_core_pvc_pipe"           # KS M 3413 발포 중심층 공압출
    assert _keys("PVC관 VG1")[0] == "general_pvc_pipe"
    assert _keys("점착형 합성고무계 복합시트")[0] == "polymer_waterproof_sheet"  # KS F 4911 복합시트
    assert _keys("어스앵커 강선")[0] == "pc_strand"
    assert _keys("목문 900x2100")[0] == "door_set"
    assert _keys("목문틀")[0] == "wood_window_frame"
    assert _keys("합성수지창 이중창")[0] == "window_set"
    assert _keys("합성수지창호형재")[0] == "synthetic_window_profile"
    for name in ("배수판", "강관틀비계", "혼합골재", "목제창호"):                 # 종별 경계 불명 — 넣지 않음
        assert _keys(name) == [], name


def test_labor_only_flags_material_hidden_in_install_rows():
    cov = coverage([_line("PVC지수판 설치", unit="m"), _line("레미콘", "25-24-150", "m3")])
    assert [r["key"] for r in cov["labor_only"]] == ["pvc_waterstop"]
    cov = coverage([_line("PVC지수판 설치", unit="m"), _line("PVC지수판", "200mm", "m")])
    assert cov["labor_only"] == []                                              # 자재 행이 있으면 알리지 않는다


def test_rules_follow_index_fixes():
    from danburn.calc import match_rule
    rules = load_rules(RULES)

    def rule_of(name, unit):
        r = match_rule(_line(name, unit=unit), rules)
        return r.material if r else None

    assert rule_of("석재뿜칠", "m2") is None
    assert rule_of("철근 결속선", "ton") is None
    assert rule_of("경질 발포 플라스틱 단열재(PUR)", "m2") == "pur_foam_insulation"
    assert rule_of("저소음 3층 PVC관", "m") is None                              # 일반 PVC관 규칙으로 가지 않는다
    assert rule_of("점착형 합성고무계 복합시트", "m2") == "polymer_waterproof_sheet"
    assert rule_of("앵커강선", "m") == "pc_strand"
    assert rule_of("목문", "ea") == "door_set"
    assert rule_of("발코니창", "ea") == "window_set"
