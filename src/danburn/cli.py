"""danburn 명령행: 도급내역서 → 8.11 JSON·HWPX.

예: danburn build --boq 지급자재내역서.xlsx --block 블록B --out out/8.11.hwpx
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from pathlib import Path
from .paths import RULES_DIR

DEFAULT_RULES = RULES_DIR


YES, NO = ("예", "네", "yes", "y", "true", "1", "o"), ("아니오", "아니요", "no", "n", "false", "0", "x")


def _confirmations(a: argparse.Namespace) -> dict[str, bool | str]:
    """현장 확인 답(L7-E7): project.yaml '현장_확인: {종별 key: 예|아니오}' 위에 --confirm 'key=예,key2=아니오' 를 덮는다."""
    out: dict[str, bool | str] = {}
    items: list[tuple[str, object]] = []
    if getattr(a, "project", None):
        import yaml
        items += list(((yaml.safe_load(Path(a.project).read_text(encoding="utf-8")) or {}).get("현장_확인") or {}).items())
    for part in filter(None, (x.strip() for x in (getattr(a, "confirm", "") or "").split(","))):
        k, _, v = part.partition("=")
        items.append((k.strip(), v.strip()))
    for k, v in items:
        t = str(v).strip().lower() if not isinstance(v, bool) else ("yes" if v else "no")
        if str(k).startswith("name:") and t not in YES + NO and re.fullmatch(r"[a-z][a-z0-9_]*", t):
            out[str(k)] = t                             # 품명 확인 행을 그 종별 규칙으로 넣기(L7-E8): 'name:<품명>=steel_fiber'
            continue
        if t not in YES + NO:
            raise ValueError(f"현장 확인 '{k}' 의 답 '{v}' 을 읽을 수 없습니다. 예 또는 아니오로 적으세요.")
        out[str(k)] = t in YES
    return out


def _name_groups(items: list[dict]) -> list[dict]:
    """품명 확인 항목을 (설치 행 여부, 추정 종별 목록)이 같은 것끼리 한 질문으로 묶는다(L7-E9).
    묶음 key = 'name:<첫 품명>' — 이 key 로 답하면 묶음의 모든 품명에 같은 답."""
    groups: dict[tuple, dict] = {}
    for u in items:
        gk = (bool(u.get("install")), tuple(g["key"] for g in u["guesses"]))
        g = groups.get(gk)
        if g is None:
            g = groups[gk] = {"key": f"name:{u['name']}", "names": [], "members": [], "lines": 0, "units": [],
                              "spec_words": [], "guesses": u["guesses"], "install": gk[0]}
        g["names"].append(u["name"])
        g["members"].append(u)
        g["lines"] += u["lines"]
        g["units"] += [x for x in u["units"] if x not in g["units"]]
        if u["spec_word"] not in g["spec_words"]:
            g["spec_words"].append(u["spec_word"])
    for g in groups.values():
        n = len(g["names"])
        g["label"] = g["names"][0] + (f" 외 {n - 1}품명" if n > 1 else "")
    return list(groups.values())


def cmd_build(a: argparse.Namespace) -> int:
    from .boq import read_boq
    from .calc import aggregate, plan_rows, rows_to_json
    from .hwpx_out import build_811
    from .rules import load_rules

    rules = load_rules(a.rules)
    owner = (a.owner or "").upper()
    rules = {k: r for k, r in rules.items() if not r.owner or r.owner.upper() == owner}   # 발주처 전용 규칙은 --owner 일 때만
    lines = []
    for p in a.boq:
        lines += read_boq(p)
    if not lines:
        import openpyxl
        sheets = {str(p): openpyxl.load_workbook(p, read_only=True).sheetnames for p in a.boq}
        print("읽을 수 있는 행이 없습니다. v0은 지급자재 내역서 양식(시트 '지급(건)'·'지급(기)'·'지급(토)')만 읽습니다.\n"
              f"받은 파일의 시트: {json.dumps(sheets, ensure_ascii=False)}", file=sys.stderr)
        return 2
    blocks = sorted({ln.block for ln in lines if ln.block})
    if a.block is not None:
        hit = [b for b in blocks if a.block in b]
        if not hit and blocks:
            print(f"--block '{a.block}' 과 맞는 블록이 없습니다. 있는 블록: {blocks}", file=sys.stderr)
            return 2
        if len(hit) > 1:
            print(f"--block '{a.block}' 이 여러 블록에 걸립니다: {hit}. 더 구체적으로 적으세요.", file=sys.stderr)
            return 2
    used = [ln for ln in lines if a.block is None or not ln.block or a.block in ln.block]
    all_blocks_for = frozenset({"토목"}) if a.civil_scope == "공구" else frozenset()
    try:
        confirm = _confirmations(a)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    from .calc import forced_matches, rule_for_key
    # 묶음 답 펼치기(L7-E9): 품명 확인 질문은 여러 품명을 한 key 로 묶어 묻는다 → 답을 묶음의 모든 품명 key 로 옮긴다
    if any(k.startswith("name:") for k in confirm):
        from .calc import match_rule as _mr
        from .index import coverage as _cov
        _used = [ln for ln in lines if a.block is None or not ln.block or a.block in ln.block]
        for u in (_nu := _cov(_used, matched=lambda ln: _mr(ln, rules) is not None)["name_unknown"]):
            u["key"] = f"name:{u['name']}"
        for g in _name_groups(_nu):
            if g["key"] in confirm:
                for u in g["members"]:
                    confirm.setdefault(u["key"], confirm[g["key"]])
    forced = forced_matches(lines, rules, {k for k, v in confirm.items() if v is True},   # '예' → 그 종별 규칙으로 넣는다
                            by_name={k[5:]: v for k, v in confirm.items() if k.startswith("name:") and isinstance(v, str)})
    mats, unread = aggregate(lines, rules, a.block, all_blocks_for, moved=(earthwork_moved := []), forced=forced)
    if not mats:
        print("자재·규격으로 묶인 행이 없습니다(블록 이름 또는 품명 매칭 확인).", file=sys.stderr)
        return 2
    found = {m.material for m in mats}
    warnings = [f"{r.material}({r.label}): 입력에서 0행 — 이 자재의 8.11 행이 없습니다(사급 내역·블록 선택 확인)"
                for r in rules.values() if r.material not in found and r.warn_if_missing]
    # hate(루프 3): 규칙이 없는 자재가 조용히 빠지지 않게 — 별표2 색인으로 식별해 알린다
    from .index import coverage
    used_lines = [ln for ln in lines if a.block is None or not ln.block or a.block in ln.block]
    covered_keys = frozenset(k for r in rules.values() for k in r.index_keys)
    from .calc import match_rule as _match_rule
    # 행 단위 판정(L7-E4): 규칙 파일이 있어도 그 행이 규칙에 안 걸리면 드러낸다(조용한 누락 방지)
    cov = coverage(used_lines, covered_keys=covered_keys,
                   matched=lambda ln: id(ln) in forced or _match_rule(ln, rules) is not None)
    uncovered = cov["uncovered"]
    produced_keys = {k for m in mats for k in rules[m.material].index_keys}
    from .index import load_index
    produced_keys |= {e.key for e in load_index() if e.rule in {m.material for m in mats}}   # 색인 rule 로 이어진 종별(레미콘·철근)
    for u in cov["unmatched_in_covered"]:
        u["produced"] = u["key"] in produced_keys
    # 경고·미작성 표에는 8.11 행이 하나도 안 생긴 종별만(이미 행이 있는 종별의 나머지 행은 대개 시공·부속 행 — 요약에만)
    rule_miss = [u for u in cov["unmatched_in_covered"] if not u["produced"]]
    labor_only = [u for u in cov.get("labor_only", []) if u["key"] not in produced_keys]   # 이미 산출된 종별은 빼기(L4-T3)
    # 현장 확인(L7-E7): 사용자에게 물을 목록(규칙이 있는 종별만 — 답이 '예'면 넣을 수 있다), '아니오'는 경고에서 빼고 따로 남긴다
    def _ask(u, kind):
        r = rule_for_key(u["key"], rules)
        return {"key": u["key"], "label": u["label"], "kind": kind, "examples": u["examples"][:3], "lines": u["lines"],
                "units": u.get("units", []), "rule": f"{r.material}({r.label})" if r else None}
    # rule_miss 는 8.11 행이 하나도 없는 종별만 묻는다(L7-E9) — 행이 있는 종별의 나머지 행은 요약 unmatched_in_covered 에만.
    # 다른 자재가 규격 말로 섞이던 행은 E8 에서 name_unknown 으로 따로 묻는다.
    ask = [_ask(u, "rule_miss") for u in cov["unmatched_in_covered"] if u["key"] not in confirm and not u["produced"]]
    ask += [_ask(u, "install_only") for u in labor_only if u["key"] not in confirm]
    ask = [x for x in ask if x["rule"]]
    no_keys = {k for k, v in confirm.items() if v is False}
    confirmed_excluded = [{"key": u["key"], "label": u["label"], "lines": u["lines"], "examples": u["examples"][:3]}
                          for u in (*uncovered, *cov["unmatched_in_covered"], *labor_only) if u["key"] in no_keys]
    uncovered = [u for u in uncovered if u["key"] not in no_keys]
    rule_miss = [u for u in rule_miss if u["key"] not in no_keys]
    labor_only = [u for u in labor_only if u["key"] not in no_keys]
    # 품명으로 자재를 알 수 없는 행(L7-E8): 규격 말로 다른 자재 이름 아래 묶지 않고 품명 그대로 묻는다. 답 key 는 'name:<품명>'
    name_unknown = cov.get("name_unknown", [])
    for u in name_unknown:
        u["key"] = f"name:{u['name']}"
    name_unknown_confirmed = [u for u in name_unknown if confirm.get(u["key"]) is True]
    confirmed_excluded += [{"key": u["key"], "label": u["name"], "lines": u["lines"], "examples": u["specs"][:3]}
                           for u in name_unknown if confirm.get(u["key"]) is False]
    # 설치 행뿐인 품명은 추정 종별이 모두 이미 8.11 에 있으면 묻지 않는다(설치 행에만 있음과 같은 원칙 L4-T3) — 요약 name_unknown 에는 남음
    name_unknown_open = [u for u in name_unknown if u["key"] not in confirm
                         and not (u.get("install") and all(g["key"] in produced_keys for g in u["guesses"]))]
    open_groups = _name_groups(name_unknown_open)                      # 같은 추정끼리 한 질문(L7-E9)
    for g in open_groups:
        for u in g["members"]:
            u["group"] = g["key"]
    ask += [{"key": g["key"], "label": g["label"], "kind": "name_unknown", "examples": g["names"][:3], "names": g["names"],
             "lines": g["lines"], "units": g["units"], "rule": None, "spec_word": g["spec_words"][0], "spec_words": g["spec_words"],
             "specs": [x for u in g["members"] for x in u["specs"]][:3], "guess": g["guesses"][0] if g["guesses"] else None,
             "guesses": g["guesses"],
             "choices": {**{x["key"]: f"{r.label}(으)로 넣기 — 규격에 그 자재가 맞을 때"
                            for x in g["guesses"] if (r := rule_for_key(x["key"], rules))},
                         "예": "시험 대상 자재 — 발주처 기준 필요로 표시", "아니오": "자재 아님(빼기)", "나중에": "답하지 않음"}}
            for g in open_groups]
    warnings += [f"품명으로 자재를 알 수 없음 — 확인 필요: {g['label']}(규격에 '{'·'.join(g['spec_words'])}', 내역 {g['lines']}행)"
                 for g in open_groups]
    warnings += [f"발주처 기준 필요 — 시험계획 미작성: {u['name']}(현장 확인: 시험 대상 자재, 규격에 '{u['spec_word']}', 내역 {u['lines']}행)"
                 for u in name_unknown_confirmed]                              # '예' → 발주처 기준 필요로 표시(L7-E8)
    warnings += [f"규칙 없음 — 시험계획 미작성: {u['label']}(별표2 p.{u['page']}, 내역 {u['lines']}행, 예: {', '.join(u['examples'][:2])})"
                 for u in uncovered]
    warnings += [f"규칙 밖 행 — 확인 필요: {u['label']}(규칙은 있으나 걸리지 않은 내역 {u['lines']}행, 예: {', '.join(u['examples'][:2])})"
                 for u in rule_miss]
    warnings += [f"설치 행에만 있음 — 자재 포함 여부 확인: {u['label']}(내역 {u['lines']}행, 예: {', '.join(u['examples'][:2])})"
                 for u in labor_only]
    from .extra import flag_extras
    from .calc import ambiguous, match_rule
    unmatched = [ln for ln in used_lines if id(ln) not in forced and match_rule(ln, rules) is None]
    extras = flag_extras(unmatched)                                   # 규칙에 잡힌 행은 ‘미작성’으로 경고하지 않는다(hate 루프 4)
    amb = [{"name": ln.name, "rules": ambiguous(ln, rules)} for ln in used_lines if ambiguous(ln, rules)]
    warnings += [f"규칙 겹침 — 확인 필요: '{x['name']}' → {', '.join(x['rules'])} (가장 앞 규칙으로 계산)" for x in amb[:20]]
    handled = {k for m in mats for k in rules[m.material].extra_keys}      # 실제로 행을 만든 발주처 규칙의 항목만 경고에서 뺀다
    extras["owner_standard_needed"] = [x for x in extras["owner_standard_needed"] if x["key"] not in handled]
    warnings += [f"발주처 기준 필요 — 시험계획 미작성: {x['label']}(별표2 밖, 내역 {x['lines']}행, 예: {', '.join(x['examples'][:2])})"
                 for x in extras["owner_standard_needed"]]
    from .calc import parse_sets
    member_inferred = None
    formwork_arg = a.formwork_sets
    if not formwork_arg and not a.no_infer:
        from .member import infer_members, to_formwork_arg
        member_inferred = infer_members(lines, a.block)
        formwork_arg = to_formwork_arg(member_inferred)
    rows = plan_rows(mats, rules, parse_sets(a.sets_per_lot), parse_sets(formwork_arg), a.include_optional,
                     parse_sets(a.makers), a.non_ks)
    from .calc import added_spec_rows, missing_common_specs
    missing_common = missing_common_specs(mats)
    if a.add_spec:
        rows += added_spec_rows([s.strip() for s in a.add_spec.split(",") if s.strip()], rules, parse_sets(a.makers))
    forced_src = {(ln.sheet, ln.row) for ln in lines if id(ln) in forced}
    for r in rows:                                          # 현장 확인으로 들어온 내역 행이 섞인 8.11 행
        if forced_src & set(r.sources):
            r.note = (r.note + "; " if r.note else "") + "현장 확인으로 포함"
    confirmed_included = sorted({(k, rule_for_key(k, rules).material) for k, v in confirm.items() if v is True and rule_for_key(k, rules)}
                                | {(k, rule_for_key(v, rules).material) for k, v in confirm.items()
                                   if isinstance(v, str) and rule_for_key(v, rules)})
    out = Path(a.out)
    versions = sorted({r.basis_version for r in rules.values()})
    json_path = out.with_suffix(".json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(rows_to_json(rows), ensure_ascii=False, indent=1), encoding="utf-8")
    from .hwpx_out import unlisted_items
    unlisted = unlisted_items(uncovered, extras["owner_standard_needed"], extras["site_measurements"], rule_miss=rule_miss)
    unlisted += [{"kind": "owner_standard", "label": u["name"], "basis": "현장 확인", "lines": u["lines"]}
                 for u in name_unknown_confirmed]
    unlisted += [{"kind": "품명 확인 필요", "label": g["label"], "basis": f"규격에 '{'·'.join(g['spec_words'])}'", "lines": g["lines"],
                  "action": "품명으로 자재를 확인한 뒤 시험 대상이면 시험계획 작성"} for g in open_groups]
    if getattr(a, "project", None):
        import yaml
        from .plan_doc import build_plan
        project = yaml.safe_load(Path(a.project).read_text(encoding="utf-8"))
        if a.logo:
            project["로고"] = a.logo          # CLI 가 YAML 보다 우선
        if a.company:
            project["회사명"] = a.company
        try:
            build_plan(rows, project, out, basis_version=", ".join(versions), revision=a.revision, date=a.date,
                       unlisted=unlisted, notice_footer=a.notice_footer, notes=warnings)
        except (ValueError, FileNotFoundError) as e:      # 개정 모순·로고 파일 없음·자리표시 누락 등 — 파일을 만들지 않음
            print(f"계획서를 만들지 않았습니다: {e}", file=sys.stderr)
            return 2
    else:
        build_811(rows, out, basis_version=", ".join(versions), logo=a.logo, company=a.company, unlisted=unlisted, notice_footer=a.notice_footer,
                  generated_note=f"자동 산출 초안 — 품질관리자가 현장 조건을 확인한 뒤 확정한다. 규격 미판독 행 {len(unread)}건."
                                 + "".join(f" [누락 경고] {w}" for w in warnings
                                           if not w.startswith(("규칙 없음", "규칙 밖 행", "발주처 기준 필요", "품명으로 자재를 알 수 없음"))))   # 표로 싣는다
    from .calc import optional_tests
    import os
    os.chmod(out, 0o644)
    os.chmod(json_path, 0o644)
    if a.offline or "1" in (os.environ.get("DANBURN_OFFLINE"), os.environ.get("QCPLAN_OFFLINE")):   # 옛 이름 호환(L7-N1)
        basis_check = {"status": "unknown", "message": "--offline: 기준 최신 여부를 확인하지 않음"}
    else:
        from .basis import check_basis
        basis_check = check_basis(rules)
    # 행별 비고에 흩어진 확인 항목을 한곳에(새 에이전트 스킬 시험 L5 지적)
    from collections import defaultdict
    confirm: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for part in filter(None, (x.strip() for x in (r.note or "").split(";"))):
            confirm[part].append(r.item)
    needs_confirmation = [{"note": k, "rows": len(v), "items": sorted(set(v))[:10]} for k, v in confirm.items()]
    summary = {"needs_confirmation": needs_confirmation, "ambiguous_lines": amb,
               "labor_only_materials": [{k: u.get(k) for k in ("key", "label", "lines", "examples")} for u in labor_only],
               "owner_standard_needed": extras["owner_standard_needed"],
               "site_measurements_to_confirm": extras["site_measurements"],
               "uncovered_materials": [{k: u.get(k) for k in ("key", "label", "page", "lines", "examples")} for u in uncovered],
               "unmatched_in_covered": [{k: u.get(k) for k in ("key", "label", "page", "lines", "examples", "produced")}
                                        for u in cov["unmatched_in_covered"]],
               "basis_check": {k: basis_check.get(k) for k in ("status", "message", "checked_at")}, "civil_scope": a.civil_scope, "missing_common_specs": missing_common, "member_inferred": member_inferred, "formwork_sets_used": formwork_arg, "basis_version": versions, "warnings": warnings, "optional_tests_excluded": optional_tests(rules),
               "boq_lines_used": len(used), "spec_groups": len(mats), "plan_rows": len(rows), "work_missing": sum(1 for r in rows if not r.work), "earthwork_moved": earthwork_moved,
               "ask": ask, "confirmed_included": [{"key": k, "rule": m, "lines": sum(1 for ln in used if id(ln) in forced and forced[id(ln)][0].material == m
                                                                and (ln.name == k[5:] if k.startswith("name:") else f"name:{ln.name}" not in confirm))}
                                                   for k, m in confirmed_included],
               "confirmed_excluded": confirmed_excluded,
               "name_unknown": [{**{k: u[k] for k in ("key", "name", "spec_word", "specs", "lines", "units", "install", "guess", "guesses")},
                                 "shown": u in name_unknown_open, "group": u.get("group")} for u in name_unknown],
               "name_unknown_confirmed": [{"key": u["key"], "name": u["name"], "lines": u["lines"]} for u in name_unknown_confirmed], "unread_spec_lines": len(unread),
               "hwpx": str(out), "json": str(json_path)}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def cmd_check_basis(a: argparse.Namespace) -> int:
    """규칙 데이터의 기준 판이 현행 고시와 같은지 공개 법령 미러로 확인한다(사용자 파일은 보내지 않음)."""
    from .basis import check_basis
    from .rules import load_rules
    rules = load_rules(a.rules)
    if getattr(a, "offline", False) or "1" in (os.environ.get("DANBURN_OFFLINE"), os.environ.get("QCPLAN_OFFLINE")):
        def _no_net(url):
            raise OSError("offline")
        res = check_basis(rules, fetch=_no_net)            # 네트워크 없이: 규칙의 기준 판만 보이고 status unknown(종료 4)
        res["message"] = "--offline: 기준 최신 여부를 확인하지 않음 — 규칙 데이터의 판만 표시"
    else:
        res = check_basis(rules)
    print(json.dumps(res, ensure_ascii=False))
    return {"current": 0, "outdated": 3}.get(res["status"], 4)


def cmd_inspect(a: argparse.Namespace) -> int:
    """입력 확인: 시트, 읽힌 행 수, 블록 목록. 스킬 2·3단계용."""
    import openpyxl
    from collections import Counter
    from .boq import read_boq
    for p in a.boq:
        sheets = openpyxl.load_workbook(p, read_only=True).sheetnames
        lines = read_boq(p)
        print(json.dumps({"file": str(p), "sheets": sheets, "readable_lines": len(lines),
                          "by_sheet": dict(Counter(ln.sheet for ln in lines)),
                          "blocks": dict(Counter(ln.block or "(공통)" for ln in lines)),
                          "supported": bool(lines)}, ensure_ascii=False))
    return 0


def _add_calc_args(b: argparse.ArgumentParser) -> None:
    b.add_argument("--boq", nargs="+", required=True, help="도급내역서 xlsx (지급자재 내역서 형식)")
    b.add_argument("--block", default=None, help="블록·공구 열 이름 일부 (예: 블록B). 없으면 전체")
    b.add_argument("--rules", default=str(DEFAULT_RULES))
    b.add_argument("--sets-per-lot", default="", help="레미콘 압축강도 로트당 조 수를 통째로 지정. 예: '25-24-150=7'. 없으면 규칙 기본값(28일3+7일1=4조)")
    b.add_argument("--owner", default="", help="발주처 기준 규칙을 켠다(예: LH → LHCS 10 40 00 부록 「품질시험 및 검사기준」). 없으면 별표2만")
    b.add_argument("--logo", default=None, help="내 회사 로고 이미지(PNG/JPEG, 로컬 파일). 없으면 로고 칸을 비워 둔다")
    b.add_argument("--company", default="", help="내 회사명(로고 칸 아래 표시). 없으면 비워 둔다")
    b.add_argument("--offline", action="store_true", help="기준 최신 여부 확인(공개 법령 미러 조회)을 건너뛴다")
    b.add_argument("--civil-scope", choices=["블록", "공구"], default="블록",
                   help="토목 물량 범위. 원칙은 블록별, 한 업체가 두 공구 토목을 함께 맡으면 '공구'(모든 블록 합계)")
    b.add_argument("--add-spec", default="", help="도급내역서에 빠진 흔한 규격을 수량 없이 넣는다. 예: '건축:rebar:SD400 D10,건축:rebar:SD400 D13'")
    b.add_argument("--makers", default="", help="철근 제조회사 수(규격별). 예: 'SD400 D13=2,*=1'. 없으면 1곳+확인 필요")
    b.add_argument("--non-ks", action="store_true", help="철근이 KS 인증품이 아니면(50톤마다 외부 시험)")
    b.add_argument("--no-infer", action="store_true", help="부위 자동 추정을 끈다(거푸집 해체용 조를 더하지 않음)")
    b.add_argument("--include-optional", action="store_true", help="조건부·실무 생략 시험(휨강도, 온도·배합설계·현장배합수정)도 넣는다")
    b.add_argument("--formwork-sets", default="", help="거푸집 해체용 조를 규격별로 더한다. 부위로: 기둥·기초는 수직+예비, 슬래브·보까지면 수직+수평+예비. 예: '25-24-150=수직+수평+예비,25-24-80=수직+예비'")
    b.add_argument("--out", required=True, help="출력 HWPX 경로 (같은 이름 .json 도 생성)")
    b.add_argument("--confirm", default="", help="현장 확인 답(요약 ask 목록의 key). 예: 'steel_fiber=예,fiberboard=아니오' — 예: 그 종별 규칙으로 8.11 에 넣음, 아니오: 경고에서 뺌. project.yaml '현장_확인' 보다 우선")
    b.add_argument("--notice-footer", action="store_true", help="쪽 아래에 고지 줄 「본 제품은 한글과컴퓨터의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.」를 넣는다(기본 끔 — 제출 문서용, 고지는 랜딩·README·NOTICE 에 둔다)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="danburn")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="도급내역서에서 8.11 초안(HWPX+JSON)을 만든다")
    _add_calc_args(b)
    b.set_defaults(func=cmd_build)
    pl = sub.add_parser("plan", help="도급내역서+현장 정보로 품질관리계획서 전체(표지·목차·개정이력·1~10장, 8.11 계산 표)를 만든다")
    _add_calc_args(pl)
    pl.add_argument("--project", required=True, help="현장 정보 YAML (예: src/danburn/data/templates/project.example.yaml)")
    pl.add_argument("--revision", default="0", help="개정 번호 (예: 0, 3)")
    pl.add_argument("--date", required=True, help="개정 일자 (예: 2026. 09. 26.)")
    pl.set_defaults(func=cmd_build)
    c = sub.add_parser("check-basis", help="기준 판(업무지침 고시 번호)이 현행인지 확인한다. 종료 0=현행, 3=개정됨, 4=확인 못 함")
    c.add_argument("--rules", default=str(DEFAULT_RULES))
    c.add_argument("--offline", action="store_true", help="공개 법령 미러를 조회하지 않고 규칙 데이터의 기준 판만 보인다(종료 4)")
    c.set_defaults(func=cmd_check_basis)
    i = sub.add_parser("inspect", help="도급내역서를 읽을 수 있는지, 어떤 블록이 있는지 확인한다")
    i.add_argument("--boq", nargs="+", required=True)
    i.set_defaults(func=cmd_inspect)
    st = sub.add_parser("start", help="처음이면 여기부터: 몇 가지 질문으로 현장 정보를 만들고 계획서까지 만든다")
    st.add_argument("--answers", default=None, help="질문 답을 담은 yaml(비대화형). 키는 src/danburn/data/interview.yaml 의 key")
    st.add_argument("--plain", action="store_true", help="한 줄 질문·번호 응답(에이전트·스크린리더용)")
    st.add_argument("--yes", action="store_true", help="--answers 에 없는 답은 기본값(없으면 모름)으로")
    st.add_argument("--folder", default=".", help="내역서·로고 후보를 찾을 폴더(기본: 지금 폴더)")
    st.add_argument("--out-dir", default=None, help="산출 폴더(기본: ~/Documents/danburn/<공사명>/, 저장소 밖)")
    st.add_argument("--no-plan", action="store_true", help="project.yaml 만 만들고 계획서는 만들지 않는다")
    st.add_argument("--offline", action="store_true", help="기준 최신 여부 확인(공개 법령 미러 조회)을 건너뛴다")
    st.set_defaults(func=cmd_start)
    if argv is None and len(sys.argv) == 1 or argv == []:
        return _no_args(ap)
    a = ap.parse_args(argv)
    return a.func(a)


def cmd_start(a: argparse.Namespace) -> int:
    from .start import main as start_main
    return start_main(a)


def _no_args(ap: argparse.ArgumentParser) -> int:
    """인자 없이 실행: 터미널이면 start 로 바로 시작할지 묻고, 아니면 도움말."""
    if not sys.stdin.isatty():
        ap.print_help()
        return 0
    print("danburn — 도급내역서와 몇 가지 답으로 품질관리계획서를 만듭니다.")
    print("처음이면 질문에 답하며 시작하는 'danburn start' 를 권합니다. 지금 시작할까요? [Y/n]")
    if input("> ").strip().lower() in ("n", "no", "아니오"):
        ap.print_help()
        return 0
    return main(["start"])


if __name__ == "__main__":
    sys.exit(main())
