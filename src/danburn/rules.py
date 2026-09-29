"""별표2 시험 규칙 YAML(data/rules/*.yaml)을 Rule 자료형으로 읽는다."""
from __future__ import annotations

from pathlib import Path
import re

import yaml

from .model import Frequency, Rule, TestRule

WHERE_VALUES = ("현장", "외부", "KS")
KS_SUBSTITUTE_VALUES = ("", "certificate")


def _require(obj: dict, key: str, ctx: str):
    value = obj.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{ctx}: '{key}' 가 비어 있음")
    return value


def _frequency(raw: dict, ctx: str) -> Frequency:
    per_qty = raw.get("per_qty")
    unit = raw.get("unit")
    if per_qty is not None:
        if not unit:
            raise ValueError(f"{ctx}: per_qty 가 있으면 unit 도 있어야 함")
        per_qty = float(per_qty)
        if per_qty <= 0:
            raise ValueError(f"{ctx}: per_qty 는 양수여야 함")
    return Frequency(
        per_qty=per_qty,
        unit=unit,
        text=_require(raw, "text", ctx),
        minimum=int(raw.get("minimum", 1)),
        lot=bool(raw.get("lot", False)),
        default_sets=int(raw["default_sets"]) if raw.get("default_sets") is not None else None,
        sets_basis=raw.get("sets_basis") or "",
    )


def _test(raw: dict, ctx: str) -> TestRule:
    test_type = _require(raw, "test_type", ctx)
    ctx = f"{ctx} [{test_type}]"
    where = raw.get("where", "현장")
    if where not in WHERE_VALUES:
        raise ValueError(f"{ctx}: where 는 {WHERE_VALUES} 중 하나여야 함 (받은 값 {where!r})")
    ks_substitute = _ks_substitute(raw.get("ks_substitute"), ctx)
    ks_still_test = raw.get("ks_still_test", False)
    if not isinstance(ks_still_test, bool):
        raise ValueError(f"{ctx}: ks_still_test 는 true/false 여야 함 (받은 값 {ks_still_test!r})")
    if ks_substitute and ks_still_test:
        raise ValueError(f"{ctx}: ks_substitute 와 ks_still_test 를 함께 켤 수 없음")
    below = raw.get("ks_substitute_below")
    if below is not None and (isinstance(below, bool) or not isinstance(below, int) or below < 1):
        raise ValueError(f"{ctx}: ks_substitute_below 는 1 이상 정수여야 함 (받은 값 {below!r})")
    if below is not None and (ks_substitute or ks_still_test):
        raise ValueError(f"{ctx}: ks_substitute_below 는 ks_substitute·ks_still_test 와 함께 쓸 수 없음")
    eco_substitute = raw.get("eco_substitute", False)
    if not isinstance(eco_substitute, bool):
        raise ValueError(f"{ctx}: eco_substitute 는 true/false 여야 함 (받은 값 {eco_substitute!r})")
    return TestRule(
        test_type=test_type,
        method=_require(raw, "method", ctx),
        frequency=_frequency(_require(raw, "frequency", ctx), ctx),
        basis=_require(raw, "basis", ctx),
        where=where,
        conditions=raw.get("conditions") or "",
        optional=bool(raw.get("optional", False)),
        display=raw.get("display") or "",
        ks_substitute=ks_substitute,
        ks_still_test=ks_still_test,
        eco_substitute=eco_substitute,
        ks_substitute_below=below,
    )


def _ks_substitute(value, ctx: str) -> str:
    """ks_substitute: 없음·false → "", true·'certificate' → "certificate"."""
    if value is None or value is False:
        return ""
    if value is True:
        return "certificate"
    if value not in KS_SUBSTITUTE_VALUES:
        raise ValueError(f"{ctx}: ks_substitute 는 true/false 또는 'certificate' 여야 함 (받은 값 {value!r})")
    return value


def _spec_group(raw, ctx: str) -> dict:
    """spec_group: all | {label} | {pattern, label, other} → Rule 필드."""
    if raw is None:
        return {}
    if raw == "all":
        return {"spec_group": "all", "spec_group_label": "규격별"}
    if not isinstance(raw, dict):
        raise ValueError(f"{ctx}: spec_group 은 'all' 또는 {{pattern, label, other}} 여야 함 (받은 값 {raw!r})")
    pattern = raw.get("pattern")
    if not pattern:
        return {"spec_group": "all", "spec_group_label": str(raw.get("label") or "규격별")}
    try:
        groups = re.compile(pattern).groups
    except re.error as e:
        raise ValueError(f"{ctx}: spec_group.pattern 정규식 오류: {e}") from None
    label = str(raw.get("label") or "{1}")
    refs = [int(n) for n in re.findall(r"\{(\d+)\}", label)]
    if any(n > groups for n in refs):
        raise ValueError(f"{ctx}: spec_group.label 이 없는 그룹을 가리킴 ({label}, 그룹 {groups}개)")
    return {"spec_group": "pattern", "spec_group_pattern": pattern, "spec_group_label": label,
            "spec_group_other": str(raw.get("other") or "기타")}


def load_rule(path: Path) -> Rule:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    ctx = Path(path).name
    tests = _require(raw, "tests", ctx)
    match = raw.get("match") or {}
    if bool(match.get("names_generic")) != bool(match.get("spec_names")):
        raise ValueError(f"{ctx}: match.names_generic 과 match.spec_names 는 함께 적어야 함")
    group_tests = bool(raw.get("group_tests", False))
    group = raw.get("group") or {}
    if group_tests:
        _require(group, "frequency", f"{ctx} group")
        _require(group, "basis", f"{ctx} group")
    return Rule(
        material=_require(raw, "material", ctx),
        label=_require(raw, "label", ctx),
        tests=tuple(_test(t, ctx) for t in tests),
        basis_version=_require(raw, "basis_version", ctx),
        match_names=tuple(match.get("names") or ()),
        match_units=tuple(match.get("units") or ()),
        match_exclude=tuple(match.get("exclude") or ()),
        match_names_generic=tuple(match.get("names_generic") or ()),
        match_spec_names=tuple(match.get("spec_names") or ()),
        ks_mark=bool(raw.get("ks_mark", False)),
        index_keys=tuple(raw.get("index_keys") or ()),
        ks_count=str(raw.get("ks_count", "makers")),
        warn_if_missing=bool(raw.get("warn_if_missing", False)),
        makers_label=str(raw.get("makers_label", "제조회사")),
        owner=str(raw.get("owner", "")),
        accept_install_rows=bool(raw.get("accept_install_rows", False)),
        install_units=tuple(raw.get("install_units") or ()),
        extra_keys=tuple(raw.get("extra_keys") or ()),
        unit_factors=tuple((str(k), str(v[0]), float(v[1])) for k, v in (raw.get("unit_factors") or {}).items()),
        order=int(raw.get("order", 50)),
        work=str(raw.get("work") or "").strip(),
        group_tests=group_tests,
        group_frequency=(group.get("frequency") or "").strip(),
        group_basis=(group.get("basis") or "").strip(),
        **_spec_group(raw.get("spec_group"), ctx),
    )


def load_rules(dir: str | Path) -> dict[str, Rule]:
    if not Path(dir).is_dir():                  # 설치본에 데이터가 빠졌거나 --rules 경로가 틀림 — 규칙 0개로 조용히 돌지 않는다(L8-P1)
        raise FileNotFoundError(f"규칙 폴더가 없습니다: {dir}")
    rules: dict[str, Rule] = {}
    for path in sorted(Path(dir).glob("*.yaml")):
        rule = load_rule(path)
        if rule.material in rules:
            raise ValueError(f"{path.name}: material '{rule.material}' 중복")
        rules[rule.material] = rule
    return {k: _with_index_names(r) for k, r in rules.items()}


def _with_index_names(rule: Rule) -> Rule:
    """match.names 가 비어 있으면 연결된 별표2 색인 종별의 동의어를 쓴다."""
    if rule.match_names or not rule.index_keys:
        return rule
    from dataclasses import replace
    from .index import load_index
    by_key = {e.key: e for e in load_index()}
    names = tuple(dict.fromkeys(n for k in rule.index_keys if k in by_key for n in (by_key[k].names or (by_key[k].label,))))
    return replace(rule, match_names=names)
