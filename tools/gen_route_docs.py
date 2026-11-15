#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""由「旅遊线路」表生成线路参考文档，消除重复维护与计数漂移。

单一事实源是接口数据（可离线用 tools/route_snapshot.json 快照）。本脚本据此生成：
    skills/wuhan-guide/references/route_codes.md       代号字典 / 衔接链 / N 日游 / 景点反查

用法:
    python3 tools/gen_route_docs.py --snapshot      # 联网拉全量并刷新快照
    python3 tools/gen_route_docs.py --write         # 用快照重新生成 route_codes.md
    python3 tools/gen_route_docs.py --check         # 只校验 md 是否与快照一致

为什么需要它：文档此前硬编码了线路名、景点清单与条数（68 条、G2 11 个点位等），
后台数据一旦调整就会失真。改为生成后，改数据只需 --snapshot + --write。

接口过滤条件在服务端不生效（详见 skills/wuhan-guide/references/api_reference.md），
因此这里拉全量、在本地按「路线代号」分组，并按「排序」升序排列。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "tools" / "route_snapshot.json"
CODES_DOC = ROOT / "skills" / "wuhan-guide" / "references" / "route_codes.md"

SPDX = "<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->\n"

# 线路结构（代号顺序语义，而非景点数据）：主线 6 条 + 支线 3 条，支线挂靠主线。
MAIN_LINES = ("G1", "G2", "G3", "G4", "G5", "G6")
BRANCH_HOST = OrderedDict((("G9", "G2"), ("G8", "G4"), ("G7", "G5")))
BRANCH_FILL = ("G9", "G8", "G7")
ROUTE_CHAIN = ("G1", "G2", "G9", "G3", "G4", "G8", "G5", "G7", "G6")
LINE_KIND = {code: ("主线" if code in MAIN_LINES else "支线") for code in ROUTE_CHAIN}

QUERY_ROUTE = ROOT / "skills" / "wuhan-guide" / "scripts" / "query_route.py"


def _field_text(value) -> str:
    """接口字段有两种形态：数组 [{text}] 与纯字符串。"""
    if isinstance(value, list):
        return "".join(
            str(item.get("text", "")) for item in value if isinstance(item, dict)
        ).strip()
    return value.strip() if isinstance(value, str) else ""


def fetch_snapshot() -> list:
    """复用 query_route 的接口实现，保证地址/Token/表名只有一处定义。"""
    sys.path.insert(0, str(QUERY_ROUTE.parent))
    import query_route  # noqa: E402  (需要先插入 sys.path)

    rows, _total = query_route.fetch_records()
    if not rows:
        raise SystemExit("接口未返回数据，快照未更新")
    return rows


def normalize(rows: list) -> "OrderedDict[str, list]":
    """按代号分组，组内按「排序」升序（缺失/非数字排后，保持接口原序）。"""
    grouped: "OrderedDict[str, list]" = OrderedDict()
    for row in rows:
        fields = {item.get("name"): item.get("value") for item in row.get("payloadFieldList") or []}
        code = _field_text(fields.get("路线代号"))
        if not code:
            continue
        grouped.setdefault(code, []).append({
            "order": _field_text(fields.get("排序")),
            "name": _field_text(fields.get("景点名称")),
            "type": _field_text(fields.get("类型")),
            "stay": _field_text(fields.get("花费时间")),
            "stars": _field_text(fields.get("推荐指数")),
            "comment": _field_text(fields.get("点评")),
            "area": _field_text(fields.get("起止片区")),
            "route_name": _field_text(fields.get("路线名")),
        })

    def sort_key(item):
        raw = item["order"]
        try:
            return (0, float(raw), item["name"])
        except (TypeError, ValueError):
            return (1, 0.0, item["name"])

    for code in grouped:
        grouped[code].sort(key=sort_key)
    return grouped


def _hours(stays: list) -> float:
    total = 0.0
    for raw in stays:
        text = raw.strip().lower().rstrip("h")
        try:
            total += float(text)
        except ValueError:
            continue
    return total


def _fmt_hours(hours: float) -> str:
    return f"{hours:g}h"


def _code_order(grouped: "OrderedDict[str, list]") -> list:
    """代号表/速览表用自然顺序 G1..G9；未知代号追加在后。"""
    def key(code):
        tail = code[1:]
        return (0, int(tail)) if tail.isdigit() else (1, code)

    return sorted(grouped, key=key)


def _route_codes(grouped: "OrderedDict[str, list]") -> str:
    ordered = [code for code in ROUTE_CHAIN if code in grouped]
    ordered += [code for code in grouped if code not in ordered]
    natural = _code_order(grouped)
    total_spots = sum(len(grouped[code]) for code in natural)

    out = [SPDX, "# 武汉固定旅游线路代号字典\n",
           "> 本文件由 `tools/gen_route_docs.py` 生成，请勿手改；改数据请改接口后重新生成。\n",
           "## 代号表\n",
           "| 代号 | 线路名 | 类型 | 景点数 |",
           "| --- | --- | --- | --- |"]
    for code in natural:
        rows = grouped[code]
        out.append(f"| {code} | {rows[0]['route_name']} | {LINE_KIND.get(code, '支线')} | {len(rows)} |")
    out.append("")
    out.append(
        f"主线 {len([c for c in natural if LINE_KIND.get(c) == '主线'])} 条，"
        f"支线 {len([c for c in natural if LINE_KIND.get(c) != '主线'])} 条，"
        f"全表共 {total_spots} 条景点记录。\n"
    )

    # 衔接关系按「主线顺序 + 支线缩进挂在主线之后」画树，与 ROUTE_CHAIN 语义一致
    out += ["## 衔接关系\n", "```"]
    for code in ordered:
        if code in BRANCH_HOST:
            continue
        out.append(f"{code} {grouped[code][0]['route_name']}")
        for branch, host in BRANCH_HOST.items():
            if host == code and branch in grouped:
                out.append(f"  → {branch} {grouped[branch][0]['route_name']}")
    out += ["```\n",
            "**规范化顺序**（脚本输出排序与行程天数顺序均以此为准，与用户传入顺序无关）：\n",
            "```", " → ".join(ordered), "```\n"]

    out += ["## 支线挂靠关系\n", "| 支线 | 挂靠主线 | 增补位置 |", "| --- | --- | --- |"]
    for branch, host in BRANCH_HOST.items():
        if branch in grouped and host in grouped:
            out.append(f"| {branch} {grouped[branch][0]['route_name']} | {host} {grouped[host][0]['route_name']} | 排在 {host} 之后 |")
    out.append("")
    out.append("单独点名某条支线时，若用户需要连贯行程，应一并传入其挂靠主线（如只说「光谷怎么玩」→ 传 G2 G9）。\n")

    out += ["## N 日游推导\n", "| 天数 | 线路组合 |", "| --- | --- |"]
    mains = [code for code in ordered if LINE_KIND.get(code) == "主线"]
    for days in range(1, len(mains) + 1):
        out.append(f"| {days} 日 | {'、'.join(mains[:days])} |")
    for extra, branch in enumerate(BRANCH_FILL, start=1):
        if branch not in grouped:
            continue
        combo = mains + [b for b in BRANCH_FILL[:extra] if b in grouped]
        out.append(f"| {len(mains) + extra} 日 | {'、'.join(combo)} |")
    out.append("")
    out.append(
        f"规则：N ≤ {len(mains)} 取主线前 N 条；N > {len(mains)} 先取 {len(mains)} 条主线，"
        f"再按 {'、'.join(BRANCH_FILL)} 顺序补足。\n"
    )

    out += ["## 景点 → 代号速查\n",
            "用于从用户提到的景点名反查其所属线路。也可用 `scripts/query_route.py --find <景点名>` 直接反查。\n",
            "> 下列列表按接口「排序」字段**递增**排列，与 `scripts/query_route.py` 的输出顺序一致；"
            "排序值重复或缺失时按接口返回顺序，属源数据情况。\n"]
    for code in ordered:
        names = "、".join(row["name"] for row in grouped[code])
        out.append(f"- **{code} {grouped[code][0]['route_name']}**：{names}")
    out.append("")
    return "\n".join(out)


def build(rows: list) -> dict:
    grouped = normalize(rows)
    if not grouped:
        raise SystemExit("快照中没有可用的线路记录")
    return {CODES_DOC: _route_codes(grouped)}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成线路参考文档")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", action="store_true", help="联网拉取全量并刷新快照")
    group.add_argument("--write", action="store_true", help="用现有快照重新生成两份 md")
    group.add_argument("--check", action="store_true", help="校验两份 md 与快照是否一致")
    args = parser.parse_args()

    if args.snapshot:
        rows = fetch_snapshot()
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"快照已更新：{SNAPSHOT.relative_to(ROOT)}（{len(rows)} 条记录）；"
              "接着运行 --write 重新生成文档", file=sys.stderr)
        return 0

    if not SNAPSHOT.is_file():
        print(f"错误：快照缺失 {SNAPSHOT.relative_to(ROOT)}，请先 --snapshot", file=sys.stderr)
        return 2

    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    docs = build(rows)

    if args.check:
        stale = [path for path, text in docs.items() if not path.is_file() or path.read_text(encoding="utf-8") != text]
        if stale:
            for path in stale:
                print(f"漂移：{path.relative_to(ROOT)}", file=sys.stderr)
            print("文档与快照不一致，请运行 --write", file=sys.stderr)
            return 1
        print("校验通过：线路文档与快照一致")
        return 0

    for path, text in docs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"已生成 {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
