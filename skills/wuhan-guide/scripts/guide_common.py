#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""武汉导览：单页双视图模板的唯一渲染契约与共享工具。

两个入口（show_map.py 零接口导览 / query_route.py 单次接口行程）共用本模块：
读景点 JSON → 校验 → 读模板 → 精确替换六个占位符 → 原子写出同名页面。

景点唯一事实源是 assets/spots.json：地图热区、线路按钮、页内可编辑数据块都由它生成，
编号由数组顺序派生（1..N），不单独落库。模板约 2.4MB 且含单行 base64，
全程用 newline="" 精确读写，绝不整文件重排或统一行尾。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from html import escape
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets"
ASSET = ASSETS / "wuhan-guide-map.html"
SPOTS_FILE = ASSETS / "spots.json"
DEFAULT_NAME = "wuhan-guide.html"

# 注入契约分两类：
# 1) 单点令牌：CSS 与模式，模板里各出现一次；
# 2) 带默认内容的块：块内预置默认 18 景点 / 线路按钮 / 内联数据 / 导览占位，
#    模板直接打开也能完整预览，生成时整块替换（含起止标记），产物不保留标记。
TOKEN_CSS = "__GUIDE_CARDS_CSS__"
TOKEN_MODE = "__GUIDE_MODE__"
SINGLE_TOKENS = (TOKEN_CSS, TOKEN_MODE)

# 块标记本身是完整 HTML 注释，替换时连注释一起移除，避免残留 <!-- 把生成内容注释掉
BLOCK_CARDS = ("<!-- __GUIDE_CARDS_HTML__ -->", "<!-- __GUIDE_CARDS_HTML_END__ -->")
BLOCK_SPOTS = ("<!-- __GUIDE_SPOTS_HTML__ -->", "<!-- __GUIDE_SPOTS_HTML_END__ -->")
BLOCK_ROUTE_BTNS = ("<!-- __GUIDE_ROUTE_BTNS__ -->", "<!-- __GUIDE_ROUTE_BTNS_END__ -->")
BLOCK_SPOTS_JSON = ("<!-- __GUIDE_SPOTS_JSON__ -->", "<!-- __GUIDE_SPOTS_JSON_END__ -->")
BLOCKS = (BLOCK_CARDS, BLOCK_SPOTS, BLOCK_ROUTE_BTNS, BLOCK_SPOTS_JSON)

ALL_MARKERS = SINGLE_TOKENS + tuple(marker for block in BLOCKS for marker in block)
MODES = ("map", "route")

# 线路代号与名称：代号固定 G1–G9，名称用于按钮 title / aria-label
ROUTES = (
    ("G1", "龟蛇主线"),
    ("G2", "内东湖主线"),
    ("G3", "外东湖主线"),
    ("G4", "武昌主线"),
    ("G5", "汉口主线"),
    ("G6", "汉阳主线"),
    ("G7", "汉口支线"),
    ("G8", "武昌支线"),
    ("G9", "光谷支线"),
)
ROUTE_CODES = tuple(code for code, _ in ROUTES)

# 预览服务（WorkBuddy/IDE）通常只服务工作区目录，这些路径下的文件直接预览会返回 403
NON_PREVIEWABLE_ROOTS = ("/tmp", "/private/tmp", "/var/folders", "/private/var/folders")


def _require_text(raw: dict, field: str, label: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"景点「{label}」的 {field} 必须是非空字符串")
    return value.strip()


def _require_number(raw: dict, field: str, label: str, lo: float, hi: float) -> float:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"景点「{label}」的 {field} 必须是数字")
    value = float(value)
    if not lo <= value <= hi:
        raise ValueError(f"景点「{label}」的 {field} 必须在 {lo:g}–{hi:g} 之间，实际 {value:g}")
    return value


def load_spots() -> list:
    """读取并校验 assets/spots.json，返回规范化的景点列表（数组顺序即编号顺序）。"""
    if not SPOTS_FILE.is_file():
        raise FileNotFoundError(f"景点数据文件缺失：{SPOTS_FILE}")
    try:
        with open(SPOTS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"景点数据不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("景点数据的顶层必须是对象（含 version 与 spots）")
    if payload.get("version") != 1:
        raise ValueError(f"景点数据 version 应为 1，实际 {payload.get('version')!r}")
    raw_spots = payload.get("spots")
    if not isinstance(raw_spots, list) or not raw_spots:
        raise ValueError("景点数据的 spots 必须是非空数组")

    spots, names = [], set()
    for index, raw in enumerate(raw_spots, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 个景点必须是对象")
        name = _require_text(raw, "name", f"#{index}")
        if name in names:
            raise ValueError(f"景点名称重复：{name}")
        names.add(name)
        spot_type = _require_text(raw, "type", name)
        desc = raw.get("desc")
        if not isinstance(desc, str):
            raise ValueError(f"景点「{name}」的 desc 必须是字符串")
        area = _require_text(raw, "area", name)
        routes = raw.get("routes")
        if not isinstance(routes, list):
            raise ValueError(f"景点「{name}」的 routes 必须是数组")
        cleaned_routes = []
        for code in routes:
            if code not in ROUTE_CODES:
                raise ValueError(f"景点「{name}」的线路代号不合法：{code!r}（应为 G1–G9）")
            if code not in cleaned_routes:
                cleaned_routes.append(code)
        spots.append({
            "name": name,
            "type": spot_type,
            "desc": desc.strip(),
            "x": _require_number(raw, "x", name, 0, 100),
            "y": _require_number(raw, "y", name, 0, 100),
            "w": _require_number(raw, "w", name, 2, 40),
            "area": area,
            "routes": cleaned_routes,
        })
    return spots


def route_spots(spots: list) -> dict:
    """由景点的 routes 反推「线路 → 点位编号」，9 条线路全部返回（可能为空）。"""
    mapping = {code: [] for code in ROUTE_CODES}
    for no, spot in enumerate(spots, start=1):
        for code in spot["routes"]:
            mapping[code].append(no)
    return mapping


def spots_digest(spots: list) -> str:
    """景点数据短哈希：页面重新生成后用于判定 localStorage 存档是否过期。"""
    canonical = json.dumps(
        {"routes": [list(r) for r in ROUTES], "spots": spots},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _fmt(value: float) -> str:
    return f"{value:g}"


def render_spots_html(spots: list) -> str:
    """生成热区按钮；编号取自数组顺序，data-* 与可见标签保持一致。"""
    lines = []
    for no, spot in enumerate(spots, start=1):
        name = escape(spot["name"], quote=True)
        spot_type = escape(spot["type"], quote=True)
        desc = escape(spot["desc"], quote=True)
        # 编号牌取第一条所属线路的主题色；无线路时沿用橙金默认色
        style = f'--x:{_fmt(spot["x"])}%;--y:{_fmt(spot["y"])}%;--w:{_fmt(spot["w"])}%;--h:88px'
        if spot["routes"]:
            style += f';--rc:var(--g{spot["routes"][0][1:]})'
        lines.append(
            f'        <button class="hotspot" data-no="{no}" '
            f'style="{style}" '
            f'data-title="{name}" data-type="{spot_type}" data-desc="{desc}">'
            f'<span class="sr">{escape(spot["name"])}</span>'
            f'<span class="spot-chip" aria-hidden="true"><i class="spot-no">{no}</i>'
            f'<span class="spot-name">{escape(spot["name"])}</span></span></button>'
        )
    return "\n".join(lines)


def render_route_btns(spots: list) -> str:
    """生成 9 个线路按钮；data-spots 由景点声明的所属线路反推，允许为空集合。"""
    mapping = route_spots(spots)
    lines = []
    for code, name in ROUTES:
        nos = mapping[code]
        raw = ",".join(str(n) for n in nos)
        lines.append(
            f'        <button class="route-btn" type="button" data-route="{code}" data-spots="{raw}" '
            f'aria-pressed="false" title="{code} {escape(name, quote=True)} · 覆盖 {len(nos)} 个点位" '
            f'aria-label="{code} {escape(name, quote=True)}">{code}</button>'
        )
    return "\n".join(lines)


def render_spots_json(spots: list) -> str:
    """生成页内可编辑数据块；baseHash 供前端判定 localStorage 存档是否匹配当前页面。"""
    payload = {
        "version": 1,
        "baseHash": spots_digest(spots),
        "routes": [{"code": code, "name": name} for code, name in ROUTES],
        "spots": spots,
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # 避免景点简介里的 </script> 提前闭合内联数据块
    return text.replace("</", "<\\/")


def render_list(spots: list) -> str:
    """按片区首次出现顺序输出文字清单，编号与地图一致。"""
    order, groups = [], {}
    for no, spot in enumerate(spots, start=1):
        area = spot["area"]
        if area not in groups:
            groups[area] = []
            order.append(area)
        groups[area].append(f"[{no}] {spot['name']}")
    lines = [f"图上可点击景点（共 {len(spots)} 个，编号与地图上的橙金编号标签一致；按片区）："]
    for area in order:
        lines.append(f"- {area}：{'、'.join(groups[area])}")
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


def _replace_block(html: str, block: tuple, content: str) -> str:
    """用 content 替换 start…end 之间的整块默认内容（含起止标记）。"""
    start, end = block
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if len(pattern.findall(html)) != 1:
        raise ValueError(f"模板块 {start} … {end} 必须恰好出现 1 次")
    return pattern.sub(lambda _match: content, html, count=1)


def load_template() -> str:
    """精确读取模板（保留行尾与 2MB 级 base64 长行），并校验令牌/块标记各恰好一次。

    ⚠ 模板是靠「字符串级精确替换」维护的，任何行尾归一化、格式化或整文件重排都会
    破坏内联 base64 行。禁止用编辑器格式化该文件；仓库级保护见根目录 `.gitattributes`。
    """
    if not ASSET.is_file():
        raise FileNotFoundError(f"内置页面模板缺失：{ASSET}")
    with open(ASSET, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    if "\r\n" in html:
        raise ValueError(
            f"模板 {ASSET.name} 含 CRLF 行尾，可能是编辑器或 git 自动转换造成的，"
            "会破坏内联 base64 行；请恢复为纯 LF 后重试"
        )
    for tok in SINGLE_TOKENS:
        n = html.count(tok)
        if n != 1:
            raise ValueError(f"模板令牌 {tok} 应恰好出现 1 次，实际 {n} 次")
    for block in BLOCKS:
        for marker in block:
            n = html.count(marker)
            if n != 1:
                raise ValueError(f"模板块标记 {marker} 应恰好出现 1 次，实际 {n} 次")
    return html


def render_page(*, cards_css: str, cards_html: str, mode: str,
                out: Path, template: str | None = None,
                spots: list | None = None) -> str:
    """把景点、线路按钮、页内数据、卡片 CSS / HTML / 模式注入模板并原子写出。

    template / spots 可由入口传入已校验过的结果，避免重复读取大文件。
    块内默认内容只服务于“模板直接打开”，生成时整体替换。
    """
    if mode not in MODES:
        raise ValueError(f"未知页面模式：{mode}，应为 {' / '.join(MODES)}")
    html = template if template is not None else load_template()
    spot_list = spots if spots is not None else load_spots()

    spots_html = render_spots_html(spot_list)
    route_btns = render_route_btns(spot_list)
    spots_json = (
        '<script type="application/json" id="guideSpotsData">'
        + render_spots_json(spot_list)
        + '</script>'
    )
    injected = (cards_css, cards_html, mode, spots_html, route_btns, spots_json)
    # 注入内容不得自带标记，避免二次替换串味
    for value in injected:
        for marker in ALL_MARKERS:
            if marker in value:
                raise ValueError(f"注入内容含模板标记：{marker}")

    html = _replace_block(html, BLOCK_CARDS, cards_html)
    html = _replace_block(html, BLOCK_SPOTS, spots_html)
    html = _replace_block(html, BLOCK_ROUTE_BTNS, route_btns)
    html = _replace_block(html, BLOCK_SPOTS_JSON, spots_json)
    html = html.replace(TOKEN_CSS, cards_css)
    html = html.replace(TOKEN_MODE, mode)
    for marker in ALL_MARKERS:
        if marker in html:
            raise ValueError(f"模板标记未完全替换：{marker}")

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
