#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""武汉导览：单页双视图模板的唯一渲染契约与共享工具。

两个入口（show_map.py 零接口导览 / query_route.py 单次接口行程）共用本模块：
读模板 → 校验 18 个热区与 9 条线路 → 精确替换三个占位符 → 原子写出同名页面。

模板约 2.2MB 且含单行 base64，全程用 newline="" 精确读写，绝不整文件重排或统一行尾。
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

ASSET = Path(__file__).resolve().parents[1] / "assets" / "wuhan-guide-map.html"
DEFAULT_NAME = "wuhan-guide.html"

# 三个自解释占位符：模板中各恰好出现一次
TOKEN_CSS = "__GUIDE_CARDS_CSS__"
TOKEN_HTML = "__GUIDE_CARDS_HTML__"
TOKEN_MODE = "__GUIDE_MODE__"
TOKENS = (TOKEN_CSS, TOKEN_HTML, TOKEN_MODE)
MODES = ("map", "route")

# 预览服务（WorkBuddy/IDE）通常只服务工作区目录，这些路径下的文件直接预览会返回 403
NON_PREVIEWABLE_ROOTS = ("/tmp", "/private/tmp", "/var/folders", "/private/var/folders")

# 片区顺序即编号顺序；仅用于清单排版与编号校验，不改变地图内容
AREA_GROUPS = (
    ("汉口 · 江岸／江汉", ("武汉博物馆", "吉庆民俗街", "兰陵路", "汉口江滩",
                       "万松园美食街", "SPU社区·江岸智民里")),
    ("武昌 · 黄鹤楼／长江大桥", ("黄鹤楼", "户部巷", "粮道街", "昙华林",
                            "武汉长江大桥")),
    ("东湖 · 沙湖", ("东湖风景区", "湖北省博物馆", "武汉大学", "武汉SKP")),
    ("光谷 · 南湖", ("中南财经政法大学", "SPU社区·光谷")),
    ("汉阳 · 龟山／月湖", ("龟山",)),
)

# 完整匹配每个热区按钮，便于同时校验 data 属性与 DOM 标签
BUTTON_RE = re.compile(
    r'<button class="hotspot"(?P<attrs>[^>]*)>(?P<body>.*?)</button>',
    re.DOTALL | re.UNICODE,
)
ATTR_NO_RE = re.compile(r'data-no="(\d+)"')
ATTR_TITLE_RE = re.compile(r'data-title="([^"]+)"')
CHIP_RE = re.compile(
    r'<span class="spot-chip"[^>]*>\s*<i class="spot-no">(\d+)</i>\s*'
    r'<span class="spot-name">([^<]+)</span>\s*</span>',
    re.UNICODE,
)

# 控制条线路按钮：data-spots 是「线路 → 点位编号」唯一映射源。
# 抽屉内的快捷按钮用 class="gd-route-btn"，不会被此正则匹配。
ROUTE_BTN_RE = re.compile(
    r'<button class="route-btn"[^>]*data-route="(G\d+)"[^>]*data-spots="([\d,]+)"[^>]*>',
    re.UNICODE,
)


def parse_spots(html: str) -> list:
    """读取热区的 (编号, 名称)，并校验 DOM 标签与 data 属性一致，作为清单唯一事实源。"""
    buttons = BUTTON_RE.findall(html)
    if not buttons:
        raise ValueError("模板中未找到 .hotspot 按钮，资源可能损坏")
    if html.count('<button class="hotspot"') != len(buttons):
        raise ValueError("模板中存在结构异常的 .hotspot 按钮")

    spots = []
    for attrs, body in buttons:
        no_m, title_m, chip_m = (
            ATTR_NO_RE.search(attrs), ATTR_TITLE_RE.search(attrs), CHIP_RE.search(body)
        )
        if not (no_m and title_m and chip_m):
            raise ValueError("模板中存在缺少 data-no／data-title／.spot-chip 的热区，资源可能损坏")
        no, title = int(no_m.group(1)), title_m.group(1)
        chip_no, chip_name = int(chip_m.group(1)), chip_m.group(2)
        if chip_no != no or chip_name != title:
            raise ValueError(
                f"热区 {no} {title} 的 DOM 标签与 data 属性不一致（标签为 {chip_no} {chip_name}）"
            )
        spots.append((no, title))

    titles = [t for _, t in spots]
    nos = [n for n, _ in spots]
    if len(titles) != len(set(titles)):
        raise ValueError("模板中存在重复景点标题")
    if sorted(nos) != list(range(1, len(spots) + 1)):
        raise ValueError(
            f"地图标号必须是从 1 到 {len(spots)} 的连续唯一整数，实际为 {sorted(nos)}"
        )
    return spots


def parse_routes(html: str, spots: list) -> list:
    """读取 9 个线路按钮，校验代号顺序与点位编号有效性。"""
    found = ROUTE_BTN_RE.findall(html)
    if len(found) != 9:
        raise ValueError("控制条应有 9 个 G1–G9 线路按钮，实际找到 %d 个" % len(found))
    codes = [c for c, _ in found]
    if codes != ["G%d" % i for i in range(1, 10)]:
        raise ValueError("线路代号应为 G1–G9 顺序，实际为 %s" % codes)
    valid = {str(n) for n, _ in spots}
    for code, raw in found:
        nos = [x.strip() for x in raw.split(",") if x.strip()]
        if not nos or len(nos) != len(set(nos)):
            raise ValueError("%s 的 data-spots 为空或有重复：%s" % (code, raw))
        unknown = [n for n in nos if n not in valid]
        if unknown:
            raise ValueError("%s 的 data-spots 含不存在的点位编号：%s" % (code, unknown))
    return found


def expected_numbering() -> dict:
    """片区顺序推导出的「名称 → 编号」对照表。"""
    return {
        title: i
        for i, title in enumerate(
            (t for _, group in AREA_GROUPS for t in group), start=1
        )
    }


def render_list(spots: list) -> str:
    expected = expected_numbering()
    actual = {title: no for no, title in spots}
    missing = [t for t in expected if t not in actual]
    unexpected = [t for t in actual if t not in expected]
    if missing or unexpected:
        raise ValueError(
            "清单与地图热区不一致：地图新增 %s，清单缺少 %s"
            % (unexpected or "无", missing or "无")
        )
    mismatched = [f"{t}(地图 {actual[t]}／清单 {expected[t]})"
                  for t in expected if actual[t] != expected[t]]
    if mismatched:
        raise ValueError("地图标号与清单编号不一致：" + "、".join(mismatched))

    lines = [f"图上可点击景点（共 {len(spots)} 个，编号与地图上的橙金编号标签一致；按片区）："]
    for area, group in AREA_GROUPS:
        labeled = "、".join(f"[{expected[t]}] {t}" for t in group)
        lines.append(f"- {area}：{labeled}")
    return "\n".join(lines)


def preview_hint(path: Path) -> str:
    ap = str(path)
    if ap.startswith(NON_PREVIEWABLE_ROOTS):
        return (
            f"警告：{ap} 位于系统临时目录，预览服务通常只服务工作区，"
            "直接预览会返回 Forbidden(403)。请用 --out 输出到工作区内的绝对路径。"
        )
    return f"页面已写入：{ap}"


def page_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def load_template() -> str:
    """精确读取模板（保留行尾与 2MB base64 长行），并确认三个占位符各恰好一次。"""
    if not ASSET.is_file():
        raise FileNotFoundError(f"内置页面模板缺失：{ASSET}")
    with open(ASSET, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    for tok in TOKENS:
        n = html.count(tok)
        if n != 1:
            raise ValueError(f"模板占位符 {tok} 应恰好出现 1 次，实际 {n} 次")
    return html


def validate_template(html: str) -> tuple[list, list]:
    """复用热区与线路校验，返回 (景点列表, 线路列表)。"""
    spots = parse_spots(html)
    routes = parse_routes(html, spots)
    return spots, routes


def render_page(*, cards_css: str, cards_html: str, mode: str,
                out: Path, template: str | None = None) -> str:
    """把卡片 CSS / 卡片 HTML / 模式注入模板，原子写出同名单页，返回绝对路径。

    template 可由入口传入已校验过的模板，避免 2.2MB 被重复读取。
    """
    if mode not in MODES:
        raise ValueError(f"未知页面模式：{mode}，应为 {' / '.join(MODES)}")
    html = template if template is not None else load_template()
    validate_template(html)

    # 注入内容不得自带占位符，避免二次替换串味
    for tok in TOKENS:
        if tok in cards_css or tok in cards_html:
            raise ValueError(f"注入内容含模板占位符：{tok}")
    html = (html.replace(TOKEN_CSS, cards_css)
                .replace(TOKEN_HTML, cards_html)
                .replace(TOKEN_MODE, mode))
    for tok in TOKENS:
        if tok in html:
            raise ValueError(f"占位符未完全替换：{tok}")

    path = Path(os.path.abspath(os.path.expanduser(str(out))))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 临时文件 + 原子替换，避免复制中断留下半截 HTML
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(html)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except (OSError, UnboundLocalError):
            pass
        raise OSError(f"写入页面失败：{exc}") from exc
    return str(path)


def fail(message: str, code: int = 2) -> int:
    print(f"错误：{message}", file=sys.stderr)
    return code
