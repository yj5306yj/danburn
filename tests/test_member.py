from danburn.calc import parse_sets
from danburn.member import infer_members, to_formwork_arg
from danburn.model import BoqLine


def L(name, spec, section, disc="건축", supply="사급", qty=10.0):
    return BoqLine(disc, "x", 1, name, spec, "M3", qty, "", supply, section)


def test_pour_rows_decide_member_for_supplied_concrete():
    lines = [L("레미콘", "25-24-15", "아파트 > 지급자재비", supply="지급"),
             L("레미콘", "25-24-8", "아파트 > 지급자재비", supply="지급"),
             L("레미콘", "25-18-8", "아파트 > 지급자재비", supply="지급"),
             L("철근 콘크리트타설(펌프카)", "S15cm, 보통", "아파트 > 상부공사 > 철근콘크리트공사", qty=300),
             L("철근 콘크리트타설(펌프카)", "S12cm 이하", "아파트 > 기초공사 > 철근콘크리트공사", qty=200),
             L("레미콘", "25-21-15", "토목 > 단지토목(구조물)공사", disc="토목", supply="지급"),
             L("레미콘", "25-24-15", "옹벽공사 > 역L형 옹벽", disc="토목")]
    got = infer_members(lines)
    assert got["건축:25-24-150"]["parts"] == "수직+수평+예비"
    assert got["건축:25-24-80"]["parts"] == "수직+예비"
    assert got["건축:25-18-80"]["parts"] == ""
    assert got["토목:25-21-150"] == {"parts": "", "evidence": ["단서 없음 — 사용자 확인"], "confirm": True}
    assert got["토목:25-24-150"]["parts"] == "수직+예비"
    assert parse_sets(to_formwork_arg(got)) == {"건축:25-24-150": 3, "건축:25-24-80": 2, "토목:25-24-150": 2}


def test_minor_zone_noise_does_not_flip_member():
    lines = [L("레미콘", "25-24-8", "아파트 > 지급자재비", supply="지급"),
             L("철근 콘크리트타설", "S12cm 이하", "아파트 > 기초공사 > 철근콘크리트공사", qty=9000),
             L("철근 콘크리트타설", "S12cm 이하", "아파트 > 상부공사 > 철근콘크리트공사", qty=1)]
    assert infer_members(lines)["건축:25-24-80"]["parts"] == "수직+예비"
