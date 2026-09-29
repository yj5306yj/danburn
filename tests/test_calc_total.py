"""규격 총량 합산(L14-A) — 동(블록) 열로 잘게 나뉜 합성 내역서도 같은 자재·같은 규격은 한 행, 총량 기준 횟수."""
from __future__ import annotations

from pathlib import Path

import pytest

from danburn.calc import aggregate, plan_rows
from danburn.model import BoqLine
from danburn.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
# 합성 수치(둥근 값) — 실제 현장 자료의 수치를 쓰지 않는다(CLAUDE.md 절대 규칙 2, L14-D6)
CONCRETE = [("가동", 10.0), ("나동", 100.0), ("다동", 250.0), ("라동", 40.0)]      # 합 400㎥
REBAR = [("가동", 5.0), ("나동", 20.0), ("다동", 100.0)]                             # 합 125t


@pytest.fixture(scope="module")
def rules():
    return load_rules(ROOT / "src" / "danburn" / "data" / "rules")


def _lines():
    out = []
    for i, (blk, q) in enumerate(CONCRETE):
        section = "건축 > 토공사 및 기초공사" if i == 0 else "건축 > 철근콘크리트공사"    # 조각마다 공종이 달라도
        out.append(BoqLine("건축", "내역(건)", i + 1, "레미콘", "25-24-15", "M3", q, blk, "사급", section))
    for i, (blk, q) in enumerate(REBAR):
        out.append(BoqLine("건축", "내역(건)", 10 + i, "철근", "SD500 D10", "TON", q, blk, "사급",
                           "건축 > 철근콘크리트공사"))
    return out


def test_blocks_merge_into_one_spec_total(rules):
    mats, _ = aggregate(_lines(), rules)
    conc = [m for m in mats if m.material == "ready_mixed_concrete"]
    bar = [m for m in mats if m.material == "rebar"]
    assert [(m.spec, m.qty) for m in conc] == [("25-24-150", 400.0)]
    assert [(m.spec, m.qty) for m in bar] == [("SD500 D10", 125.0)]
    assert len(conc[0].sources) == 4
    assert conc[0].work == "철근콘크리트공사"                # 공종 다수결도 합친 총량 기준


def test_counts_follow_total_not_pieces(rules):
    mats, _ = aggregate(_lines(), rules)
    rows = plan_rows(mats, rules, makers={"*": 3})
    conc = [r for r in rows if r.material == "ready_mixed_concrete"]
    by_test = {r.test_type: r for r in conc}
    assert len({r.qty for r in conc}) == 1 and conc[0].qty == 400.0
    comp = next(r for t, r in by_test.items() if "압축강도" in t)
    assert comp.count_site + comp.count_external == 8          # ⌈400/360⌉=2로트 × 4조 (조각별이면 4조각 × 1로트 × 4조 = 16)
    slump = next(r for t, r in by_test.items() if "슬럼프" in t)
    assert slump.count_site + slump.count_external == 4         # ⌈400/120⌉=4 (조각별이면 1+1+3+1 = 6)
    bar = [r for r in rows if r.material == "rebar"]
    assert len(bar) == 1 and bar[0].count_external == 3         # 제조사 3곳 × 1규격 (조각별이면 9)


def test_block_option_still_picks_one_block(rules):
    mats, _ = aggregate(_lines(), rules, block="다동")
    got = {m.material: m.qty for m in mats}
    assert got == {"ready_mixed_concrete": 250.0, "rebar": 100.0}


# ── 규격 키 정규화(L14-D1): 표기 차이·시공 조건 괄호로 같은 제품이 갈리지 않게, 다른 제품 규격은 절대 합치지 않게 ──

@pytest.mark.parametrize("raw, key", [
    ("((초배무))", "초배무"), ("(초배무)", "초배무"), ("초배무", "초배무"),
    ("(바탕20MM,건조시멘트모르타르)", ""), ("(바탕25MM,건조시멘트모르타르)", ""),
    ("바탕20MM+혼드25MM", "바탕20MM+혼드25MM"),                  # '+' 로 붙은 마감 두께는 제품 규격 → 그대로
    ("(규격 없음)", ""), ("L=12Km", ""), ("(별산)", ""), ("15KM까지", ""),
    ("D-450", "D450"), ("Ｄ－４５０", "D450"), ("D 300", "D300"),
    ("D-450MM,모래기초(60도)", "D450MM"), ("D-450MM,콘크리트기초(90도)", "D450MM"),
    ("10M이하(3개월)", "10M이하"),
    ("건조모르타르(조적벽h=0~200MM구간)", ""), ("건조모르타르(조적벽h=200~1,200MM구간)", ""),
    ("KS82KG/CM2,190X90X57,공사현장차상도", "KS82KG/CM2,190X90X57"),
    ("화강석,180×200×1,000mm", "화강석,180X200X1000MM"),
    ("휴게실,L=900", "휴게실,L=900"),              # KM 아닌 L= 는 제품 길이 → 그대로
    ("화강석,180X200X1000(A-Type,곡선구간)", "화강석,180X200X1000(A-TYPE,곡선구간)"),   # 곡선/직선 제품은 애매 → 그대로
    ("150,200", "150,200"),                                     # 맨 앞 숫자 목록은 천 단위로 보지 않는다
    ("300X300,600X600", "300X300,600X600"),                     # 치수 목록의 쉼표는 그대로(L14-D6)
    ("300X300,600", "300X300,600"),                             # 앞 3자리 묶음은 애매 → 그대로
    ("D=13,200", "D=13,200"),                                   # '=' 뒤 쉼표는 애매 → 그대로
    ("X12,000MM", "X12000MM"),
    ("어린이집ㄱ형,ㅁ-100X100", "어린이집ㄱ형,ㅁ-100X100"),          # 한글 자모는 그대로(NFKC 금지)
    ("（초배무）", "초배무"),
])
def test_normalize_spec_keys(raw, key):
    from danburn.calc import normalize_spec
    assert normalize_spec(raw) == key


@pytest.mark.parametrize("a, b", [("9.5T", "12.5T"), ("D300", "D450"), ("VG1", "VG2"), ("T50", "T30"),
                                  ("SD400", "SD500"), ("25-24-150", "25-27-150")])
def test_normalize_spec_keeps_different_products_apart(a, b):
    from danburn.calc import normalize_spec
    assert normalize_spec(a) != normalize_spec(b)


def _one(name, spec, qty, unit, row, disc="건축"):
    return BoqLine(disc, "내역(건)" if disc == "건축" else "내역(토)", row, name, spec, unit, qty, "", "사급", "")


def test_condition_variants_merge_into_one_row(rules):
    mats, _ = aggregate([
        _one("수도용고무링", "D-450", 3, "개", 1, "토목"), _one("수도용고무링", "D450", 2, "개", 2, "토목"),
        _one("수도용고무링", "D300", 4, "개", 3, "토목"),
        _one("데코시트", "벽,THK.9MM MDF", 100, "M2", 4), _one("데코시트", "벽, thk.9mm mdf", 50, "M2", 5),
        _one("데코시트", "벽,THK.18MM MDF", 70, "M2", 6),              # spec_group 없는 규칙(석재는 L14-C3 에서 석종 묶음이 생김)
    ], rules)
    got = {(m.material, m.spec): m.qty for m in mats if m.material in ("water_rubber", "lh_deco_sheet")}
    rubber = {s: q for (mat, s), q in got.items() if mat == "water_rubber"}
    assert rubber == {"D450": 5, "D300": 4}
    sheet = {s: q for (mat, s), q in got.items() if mat == "lh_deco_sheet"}
    assert sheet == {"벽,THK.9MMMDF": 150, "벽,THK.18MMMDF": 70}       # 9MM 두 표기는 합치고 18MM 는 따로


def test_different_rebar_and_concrete_specs_stay_apart(rules):
    mats, _ = aggregate([
        BoqLine("건축", "내역(건)", 1, "철근", "SD400 D13", "TON", 10.0, "", "사급", ""),
        BoqLine("건축", "내역(건)", 2, "철근", "SD500 D13", "TON", 20.0, "", "사급", ""),
        BoqLine("건축", "내역(건)", 3, "레미콘", "25-24-15", "M3", 100.0, "", "사급", ""),
        BoqLine("건축", "내역(건)", 4, "레미콘", "25-27-15", "M3", 200.0, "", "사급", ""),
    ], rules)
    got = {(m.material, m.spec): m.qty for m in mats}
    assert got[("rebar", "SD400 D13")] == 10 and got[("rebar", "SD500 D13")] == 20
    assert got[("ready_mixed_concrete", "25-24-150")] == 100 and got[("ready_mixed_concrete", "25-27-150")] == 200
