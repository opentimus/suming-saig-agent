#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""把 spots.json 的当前快照刷进模板的四个默认块，让「直接打开模板」与生成产物一致。

模板 `skills/wuhan-guide/assets/wuhan-guide-map.html` 的 `__GUIDE_*__` 块内预置了一份
默认内容（热区、线路按钮、内联数据、导览文案里的景点数），供模板被直接双击预览时使用。
改完 `spots.json` 后运行本脚本刷新这份快照，避免预览看到旧数据：

    python3 tools/sync_template_defaults.py --write   # 刷新默认块
    python3 tools/sync_template_defaults.py --check   # 只校验是否与 spots.json 一致

注意：模板含 2MB 级单行 base64，全程用 newline="" 精确读写，绝不做整文件重排；
脚本结束时校验模板仍为纯 LF 行尾。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "wuhan-guide" / "scripts"))

import guide_common as gc  # noqa: E402

TEMPLATE = gc.ASSET
COUNT_PATTERN = re.compile(r"\d+ 个可点击景点")


def _swap_block(html: str, block: tuple, content: str) -> str:
    start, end = block
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if len(pattern.findall(html)) != 1:
        raise SystemExit(f"模板块 {start} 必须恰好出现 1 次")
    return pattern.sub(lambda _m: f"{start}\n{content}\n{end}", html, count=1)


def render(html: str, spots: list) -> str:
    spots_json = (
        '<script type="application/json" id="guideSpotsData">'
        + gc.render_spots_json(spots)
        + "</script>"
    )
    html = _swap_block(html, gc.BLOCK_SPOTS, gc.render_spots_html(spots))
    html = _swap_block(html, gc.BLOCK_ROUTE_BTNS, gc.render_route_btns(spots))
    html = _swap_block(html, gc.BLOCK_SPOTS_JSON, spots_json)
    # 导览占位文案里的景点数同样来自 spots.json
    return COUNT_PATTERN.sub(f"{len(spots)} 个可点击景点", html)


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新模板默认块")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="用 spots.json 覆盖默认块")
    group.add_argument("--check", action="store_true", help="校验默认块是否与 spots.json 一致")
    args = parser.parse_args()

    if not TEMPLATE.is_file():
        print(f"错误：模板缺失 {TEMPLATE}", file=sys.stderr)
        return 2

    with open(TEMPLATE, "r", encoding="utf-8", newline="") as handle:
        html = handle.read()
    spots = gc.load_spots()
    expected = render(html, spots)

    if args.check:
        if expected == html:
            print(f"校验通过：模板默认块与 spots.json 一致（{len(spots)} 个景点）")
            return 0
        print("模板默认块与 spots.json 不一致，请运行 --write", file=sys.stderr)
        return 1

    if expected == html:
        print(f"无需改动：模板默认块已是 spots.json 的最新快照（{len(spots)} 个景点）")
        return 0
    if "\r\n" in expected:
        print("错误：渲染结果含 CRLF，拒绝写入以免破坏内联 base64", file=sys.stderr)
        return 3
    with open(TEMPLATE, "w", encoding="utf-8", newline="") as handle:
        handle.write(expected)
    print(f"已刷新模板默认块：{len(spots)} 个景点，baseHash = {gc.spots_digest(spots)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
