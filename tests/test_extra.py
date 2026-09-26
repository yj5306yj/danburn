from danburn.extra import flag_extras
from danburn.model import BoqLine


def L(name):
    return BoqLine("건축", "x", 1, name, "", "M", 1.0, "", "사급")


def test_extra_materials_are_flagged_even_in_install_rows():
    res = flag_extras([L("실링재 충전(창호주위)"), L("디지털도어록 설치"), L("주방가구 설치"), L("레미콘")])
    keys = {h["key"] for h in res["owner_standard_needed"]}
    assert {"sealant", "door_hardware", "furniture"} <= keys and len(keys) == 3
    assert {m["key"] for m in res["site_measurements"]} == {"indoor_air", "floor_impact_sound"}
