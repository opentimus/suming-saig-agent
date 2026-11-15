#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""武汉导览 · 导览模式：零接口、零网络，产出「地图主视图 + 行程引导占位」单页。

用法:
    python3 show_map.py --out /abs/path/to/workspace/wuhan-guide.html
    python3 show_map.py                       # 默认写到当前工作目录 wuhan-guide.html

stdout 为可直接回显给用户的正文，stderr 为运行元数据。
线路查询意图请改用同目录的 query_route.py，两者输出同一个 ASCII 文件名、幂等覆盖。
"""

import argparse
import os
import sys
from pathlib import Path

import guide_common as gc


def intro_html(count: int) -> str:
    """导览模式下行程面板里的引导占位；不伪装成行程数据。"""
    return (
        '<div class="gd-intro">\n'
        '  <div class="gd-intro-mark" aria-hidden="true">汉</div>\n'
        '  <div class="gd-intro-copy">\n'
        '    <h3>这张地图负责「看全城」，行程交给下一句</h3>\n'
        f'    <p>当前是全景导览视图：地图可拖动查看全图，{count} 个可点击景点、G1–G9 多选高亮、鼠标 3D 倾斜与景点简介。'
        '想要结构化行程单，说出天数或线路代号，同一张页面会在这里铺开对应线路的行程卡片。</p>\n'
        '    <div class="gd-chips">\n'
        '      <span class="gd-chip">武汉玩一天怎么玩</span>\n'
        '      <span class="gd-chip">推荐武汉 2 日游</span>\n'
        '      <span class="gd-chip">G1 和 G2 有哪些景点</span>\n'
        '      <span class="gd-chip">黄鹤楼在哪条线路上</span>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="输出武汉导览单页（导览模式，零接口）")
    parser.add_argument(
        "--out",
        default=os.path.join(os.getcwd(), gc.DEFAULT_NAME),
        help="输出 HTML 的绝对路径（须位于工作区内，文件名保持 ASCII）",
    )
    args = parser.parse_args()

    try:
        template = gc.load_template()
        spots = gc.load_spots()
        routes = gc.route_spots(spots)
        listing = gc.render_list(spots)
    except (OSError, ValueError) as exc:
        return gc.fail(f"内置页面模板校验失败：{exc}")

    try:
        path = gc.render_page(
            cards_css="",
            cards_html=intro_html(len(spots)),
            mode="map",
            out=Path(os.path.abspath(os.path.expanduser(args.out))),
            template=template,
            spots=spots,
        )
    except (OSError, ValueError) as exc:
        return gc.fail(f"生成导览页失败：{exc}", code=3)

    out = Path(path)
    print(f"武汉导览交互地图：{out}")
    print("（单文件离线可用：地图可拖动查看全图，含可点击景点、G1–G9 多选高亮、3D 倾斜与简介弹窗；"
          "底部行程面板当前为引导占位，说出天数或线路代号即可在同一页面生成行程卡片；"
          "橙金编号与下方清单编号对应）")
    print()
    print(listing)

    print(gc.preview_hint(out), file=sys.stderr)
    print(f"模式：导览（零接口）｜来源：{gc.ASSET}｜热区 {len(spots)} 个｜"
          f"线路 {len(routes)} 条｜sha256(前16) {gc.page_digest(out)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
