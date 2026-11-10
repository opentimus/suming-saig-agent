#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""武汉固定旅游线路查询：按线路代号（G1-G9）输出结构化行程单。

用法:
    python3 query_route.py G1 G2          # 查询指定线路（可一次传多个）
    python3 query_route.py --days 3       # 3 日游，自动推导为 G1 G2 G3
    python3 query_route.py --find 黄鹤楼   # 按景点名反查所属线路并输出行程
    python3 query_route.py --all          # 导出全部 9 条线路

行程内的景点顺序以接口「排序」字段递增为准（可用 --no-sort 退回接口返回顺序）。

代号表:
    G1 龟蛇主线   G2 内东湖主线 G3 外东湖主线
    G4 武昌主线   G5 汉口主线   G6 汉阳主线
    G7 汉口支线   G8 武昌支线   G9 光谷支线

可选环境变量:
    WUHAN_ROUTE_API_TOKEN 覆盖默认接口 Token
    WUHAN_ROUTE_BASE_URL  覆盖默认服务地址（默认 https://admin.aoaerp.com）
    WUHAN_ROUTE_APP       覆盖默认应用名（默认 SPU）
    WUHAN_ROUTE_TABLE     覆盖默认表名（默认 旅遊线路）
"""

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = os.environ.get("WUHAN_ROUTE_BASE_URL", "https://admin.aoaerp.com")
API_TOKEN = os.environ.get(
    "WUHAN_ROUTE_API_TOKEN",
    "0FpMQZUGcTc2lhOhPEZm_Q3F9i1q1rL73ncfJTMGpqGIWFjwld2K0otOHBFcVR6YO9z42ZvEe7EtyGy3lO2JRcrjKNUYCbHRde_5aZgjPMp-Kgzx_9tk2qPeexJXxUsu",
)
APP_NAME = os.environ.get("WUHAN_ROUTE_APP", "SPU")
TABLE_NAME = os.environ.get("WUHAN_ROUTE_TABLE", "旅遊线路")

# 路径不带 /v1 前缀：/v1/api/lowcode/... 会被 nginx 以 405 拒绝
ENDPOINT = f"{BASE_URL.rstrip('/')}/api/lowcode/normal/dify/app/table/record/page"
PAGE_SIZE = 100

ROUTE_NAMES = {
    "G1": "龟蛇主线",
    "G2": "内东湖主线",
    "G3": "外东湖主线",
    "G4": "武昌主线",
    "G5": "汉口主线",
    "G6": "汉阳主线",
    "G7": "汉口支线",
    "G8": "武昌支线",
    "G9": "光谷支线",
}
NAME_TO_CODE = {v: k for k, v in ROUTE_NAMES.items()}

# 规范衔接链：G1→G2【G9】→G3→G4【G8】→G5【G7】→G6
ROUTE_CHAIN = ["G1", "G2", "G9", "G3", "G4", "G8", "G5", "G7", "G6"]
MAIN_LINES = ["G1", "G2", "G3", "G4", "G5", "G6"]
BRANCH_FILL = ["G9", "G8", "G7"]
# 支线挂靠的主线：G2 后补 G9、G4 后补 G8、G5 后补 G7
BRANCH_HOST = {"G9": "G2", "G8": "G4", "G7": "G5"}


def fetch_records() -> tuple:
    """拉取「旅遊线路」表全量记录。

    该接口的 record 过滤条件在服务端不生效（实测 lt/eq 均返回全量），
    因此这里拉全量，由调用方在客户端按代号筛选。
    """
    payload = {"appName": APP_NAME, "tableName": TABLE_NAME, "record": {}}
    req = urllib.request.Request(
        f"{ENDPOINT}?pageNum=1&pageSize={PAGE_SIZE}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"请求失败 HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"请求失败: {e.reason}")

    payload_data = data.get("data") or {}
    rows = payload_data.get("rows") or []
    total = payload_data.get("total")
    if not rows:
        raise SystemExit(f"接口未返回数据: {json.dumps(data, ensure_ascii=False)[:500]}")
    return rows, total


def field_text(fields: list, name: str) -> str:
    """取字段文本，兼容 [{"text": "..."}] 与纯字符串两种形态。"""
    for f in fields:
        if f.get("name") != name:
            continue
        value = f.get("value")
        if isinstance(value, list):
            if not value:
                return ""
            first = value[0]
            return str(first.get("text", "")) if isinstance(first, dict) else str(first)
        return "" if value is None else str(value)
    return ""


def field_url(fields: list, name: str) -> str:
    """取图片类字段 URL，兼容 [{"link","text","type":"url"}] 与纯字符串两种形态。

    优先取 `link`，回落到 `text`；缺失或非 http(s) 时返回空串。
    """
    for f in fields:
        if f.get("name") != name:
            continue
        value = f.get("value")
        if isinstance(value, list):
            if not value:
                return ""
            first = value[0]
            if isinstance(first, dict):
                url = (first.get("link") or first.get("text") or "").strip()
            else:
                url = str(first).strip()
        elif isinstance(value, str):
            url = value.strip()
        else:
            url = ""
        if url.lower().startswith(("http://", "https://")):
            return url
        return ""


def normalize(rows: list) -> list:
    """把接口记录归一化为景点字典，丢弃代号不在 G1-G9 的记录。"""
    records = []
    for idx, row in enumerate(rows):
        fields = row.get("payloadFieldList") or []
        code = field_text(fields, "路线代号").strip().upper()
        if code not in ROUTE_NAMES:
            continue
        records.append(
            {
                "idx": idx,
                "code": code,
                "order": parse_order(field_text(fields, "排序")),
                "spot": field_text(fields, "景点名称").strip(),
                "kind": field_text(fields, "类型").strip(),
                "duration": field_text(fields, "花费时间").strip(),
                "stars": field_text(fields, "推荐指数").strip(),
                "review": field_text(fields, "点评").strip(),
                "area": field_text(fields, "起止片区").strip(),
                "img1": field_url(fields, "图片1"),
                "img2": field_url(fields, "图片2"),
                "img3": field_url(fields, "图片3"),
            }
        )
    return records


def parse_hours(text: str) -> float:
    """从 '0.5h' / '1h' / '2小时' 等文本中提取小时数，无法解析时按 0 计。"""
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else 0.0


def parse_order(text: str):
    """解析「排序」字段为数值（整数或小数），缺失/非数字返回 None。"""
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m.group()) if m else None


def sort_spots(group: list) -> list:
    """同一线路内的景点按「排序」字段递增排列。

    - 排序值相同的（异常数据）保持接口返回顺序。
    - 排序值缺失或非数字的记录排在有值记录之后，相对顺序沿用接口返回顺序，
      在「排序」字段整体不可用时会退化为此前的录入顺序。
    """
    ranked, unranked = [], []
    for pos, record in enumerate(group):
        target = ranked if record.get("order") is not None else unranked
        target.append((pos, record))
    ranked.sort(key=lambda item: (item[1]["order"], item[0]))
    return [record for _, record in ranked] + [record for _, record in unranked]


def image_issues(records: list) -> list:
    """汇总「图片」字段的数据质量问题：全表图片完全相同（占位数据）或某景点缺图。"""
    problems = []
    triples = {}
    missing = []
    for r in records:
        triple = (r.get("img1"), r.get("img2"), r.get("img3"))
        triples.setdefault(triple, 0)
        triples[triple] += 1
        if not any(triple):
            missing.append(r["spot"] or "（未命名景点）")
    distinct = [t for t in triples if any(t)]
    if distinct and len(distinct) == 1 and len(records) > 1:
        problems.append(
            f"全部 {len(records)} 条记录的「图片1/2/3」均为同一组占位图，"
            f"并非按景点区分的真实配图：{distinct[0][0][:60]}…"
        )
    elif missing:
        problems.append(f"缺少图片的景点（{len(missing)} 个）：{'、'.join(missing[:10])}"
                        + (" 等" if len(missing) > 10 else ""))
    return problems


def images_are_placeholder(records: list) -> bool:
    """全表图片为同一组占位图（非按景点区分）时返回 True。

    判定：去重后仅剩 1 组非空图片组合、且记录数 > 1。此时卡片只渲染文字版，
    避免满屏重复图，待后台按景点补齐真实配图后自动恢复嵌图。
    """
    triples = {(r.get("img1"), r.get("img2"), r.get("img3")) for r in records}
    distinct = [t for t in triples if any(t)]
    return bool(distinct) and len(distinct) == 1 and len(records) > 1


def order_issues(records: list) -> list:
    """汇总「排序」字段的数据质量问题（重复值、缺失值），用于 stderr 提示。"""
    problems = []
    for code in ROUTE_CHAIN:
        group = [r for r in records if r["code"] == code]
        if not group:
            continue
        missing = [r["spot"] or "（未命名景点）" for r in group if r["order"] is None]
        seen, dup = {}, []
        for r in group:
            if r["order"] is None:
                continue
            if r["order"] in seen:
                dup.append(f"{r['order']:g}：{seen[r['order']]} / {r['spot']}")
            else:
                seen[r["order"]] = r["spot"]
        if missing:
            problems.append(f"{code} 缺失排序值：{'、'.join(missing)}")
        if dup:
            problems.append(f"{code} 排序值重复：{'；'.join(dup)}")
    return problems


def fmt_hours(total: float) -> str:
    if total <= 0:
        return "0h"
    if abs(total - round(total)) < 1e-9:
        return f"{int(round(total))}h"
    return f"{total:g}h"


def parse_codes(args: list) -> list:
    """解析位置参数为代号列表，支持 G1 / g1 / 龟蛇主线 / 'G1,G2' 等写法。"""
    codes = []
    for raw in args:
        for part in re.split(r"[,，\s]+", raw):
            token = part.strip()
            if not token:
                continue
            upper = token.upper()
            if upper in ROUTE_NAMES:
                codes.append(upper)
            elif token in NAME_TO_CODE:
                codes.append(NAME_TO_CODE[token])
            else:
                raise SystemExit(
                    f"无法识别的线路「{token}」，允许 G1-G9 或线路名"
                    f"（如 龟蛇主线、内东湖主线）"
                )
    return sort_codes(codes)


def sort_codes(codes: list) -> list:
    """按规范衔接链去重排序，保证输出顺序与用户传入顺序无关。"""
    seen = set()
    ordered = []
    for code in ROUTE_CHAIN:
        if code in codes and code not in seen:
            ordered.append(code)
            seen.add(code)
    return ordered


def codes_for_days(days: int) -> list:
    """N 日游推导：<=6 日取前 N 条主线，超出按 G9、G8、G7 顺序补支线。"""
    if days < 1:
        raise SystemExit("--days 需 >= 1")
    if days > len(ROUTE_CHAIN):
        print(
            f"提示：最多支持 {len(ROUTE_CHAIN)} 日，已按全部线路输出",
            file=sys.stderr,
        )
        days = len(ROUTE_CHAIN)
    if days <= len(MAIN_LINES):
        return sort_codes(list(MAIN_LINES[:days]))
    # 补足支线后必须按衔接链重排，否则 G9/G8/G7 会全部堆在末尾
    return sort_codes(list(MAIN_LINES) + list(BRANCH_FILL[: days - len(MAIN_LINES)]))


def find_by_spot(records: list, keyword: str) -> list:
    """按景点名模糊反查其所属线路代号。"""
    hits = [r for r in records if keyword in r["spot"]]
    if not hits:
        raise SystemExit(f"未找到名称包含「{keyword}」的景点")
    return sort_codes({r["code"] for r in hits})


# ---------------------------------------------------------------------------
# HTML 缩略卡渲染（--cards）：图片经缩放后以 base64 内联，离线可看
# ---------------------------------------------------------------------------
IMAGE_OVERRIDES = [
    ("AGBK3D8tNyRfGHCUQQK58dnYw37oHkJPKPg7_Oq1L928aG1dF8b_gc15CDA8FaItNZvK3RMEnSZusP-oHmeixOpEuctC7NDQ04iV_zcg7BUYPeq-iX-oD-RLc_uA0GHhp6cjSpPcu-UE8TQHZIi94A", "门店实景照（大众点评）", "ok"),
    ("v2-b525d00568199f921fd7a51d184069da", "历史展板照（知乎·汉口水塔/祁万顺史料）", "info"),
    ("add6facb5fdd0f4cfa4b391aa4b78582", "老街水淹历史照（通用怀旧配图）", "warn"),
    ("bc14527d130/260107/51d0e0515476f7391a8681b15c698252", "晴川里·知音秘境装饰柱实景", "ok"),
]
HOST_LABELS = [
    ("qcloud.dpfile.com", "大众点评实景", "ok"),
    ("zhimg.com", "知乎图（展板/史料）", "info"),
    ("bdstatic.com", "通用配图（历史/怀旧）", "warn"),
]


def image_label(url: str):
    """按 URL 片段/域名推断图片来源与可信度，供缩略卡标注。"""
    for frag, lab, rel in IMAGE_OVERRIDES:
        if frag in url:
            return lab, rel
    for host, lab, rel in HOST_LABELS:
        if host in url:
            return lab, rel
    return "接口图片", "muted"


IMAGE_TIMEOUT = 15
# 下载阶段放宽上限：原图再大也会被缩到 220px，决定 HTML 体积的是缩放结果而非原图。
# 此前 2MB 的上限会误杀约 14% 的大图（实测 198 张中 28 张），故放宽到 10MB。
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
# 仅在无缩放工具（PIL/sips 均不可用）时内联原图的上限
MAX_INLINE_BYTES = 150 * 1024
IMAGE_WORKERS = 8


def _download(url: str, path: str) -> bool:
    """下载图片到 path，成功返回 True。

    带超时与体积上限，避免网络挂起卡死整个脚本或把超大文件塞进 HTML；
    失败时向 stderr 输出具体原因，便于排查。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=IMAGE_TIMEOUT) as resp:
            data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    except Exception as e:
        print(f"图片下载失败（{type(e).__name__}: {e}）：{url[:60]}…", file=sys.stderr)
        return False
    if len(data) > MAX_DOWNLOAD_BYTES:
        print(
            f"图片超过 {MAX_DOWNLOAD_BYTES // 1024 // 1024}MB，跳过：{url[:60]}…",
            file=sys.stderr,
        )
        return False
    with open(path, "wb") as f:
        f.write(data)
    return True


def _sniff_mime(path: str) -> str:
    """按文件头判断真实图片类型。

    data URI 的 MIME 与实际内容不符时（如 PNG 内容标成 image/jpeg），
    部分浏览器会直接拒渲染，表现为图片空白。
    """
    with open(path, "rb") as f:
        head = f.read(16)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def make_thumb(url: str, tmpdir: str, tag: str = "0"):
    """下载图片并缩放到 220px，返回 data URI；失败返回 None。

    缩放优先 PIL，其次 macOS sips；两者都不可用时，仅当原图小于
    MAX_INLINE_BYTES 才内联原图，避免无缩放工具时产出超大 HTML。
    `tmpdir` 由调用方统一创建与回收；并发调用时必须传入不同的 `tag`，
    否则多个任务会争用同一个临时文件名。
    """
    raw = os.path.join(tmpdir, f"raw_{tag}.bin")
    if not _download(url, raw):
        return None

    try:
        from PIL import Image

        im = Image.open(raw)
        im.thumbnail((220, 220))
        out = os.path.join(tmpdir, f"t_{tag}.jpg")
        im.convert("RGB").save(out, "JPEG", quality=82)
        with open(out, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    except ImportError:
        pass
    except Exception as e:
        print(f"PIL 缩放失败（{type(e).__name__}: {e}）：{url[:60]}…", file=sys.stderr)

    out = os.path.join(tmpdir, f"t_{tag}.jpg")
    if (
        shutil.which("sips")
        and subprocess.run(
            ["sips", "-Z", "220", raw, "--out", out], capture_output=True
        ).returncode == 0
        and os.path.exists(out)
    ):
        with open(out, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

    size = os.path.getsize(raw)
    if size > MAX_INLINE_BYTES:
        print(
            f"无可用缩放工具（PIL/sips）且原图 {size // 1024}KB 超过 "
            f"{MAX_INLINE_BYTES // 1024}KB，跳过内联：{url[:60]}…",
            file=sys.stderr,
        )
        return None
    with open(raw, "rb") as f:
        return f"data:{_sniff_mime(raw)};base64," + base64.b64encode(f.read()).decode()


def build_thumbs(urls: list, tmpdir: str, workers: int = IMAGE_WORKERS) -> dict:
    """并发下载并缩放，返回 {url: data_uri}；失败的 URL 不出现在结果中。

    实测串行预取全量约 200 张图需 160s+，并发后降到 20s 量级。
    """
    uniq = list(dict.fromkeys(urls))
    if not uniq:
        return {}
    thumbs = {}
    print(
        f"正在预取 {len(uniq)} 张图片（并发 {min(workers, len(uniq))}）…",
        file=sys.stderr,
    )
    with ThreadPoolExecutor(max_workers=min(workers, len(uniq))) as pool:
        futures = {
            pool.submit(make_thumb, u, tmpdir, str(i)): u for i, u in enumerate(uniq)
        }
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                data = fut.result()
            except Exception as e:
                print(
                    f"图片处理异常（{type(e).__name__}: {e}）：{url[:60]}…",
                    file=sys.stderr,
                )
                continue
            if data:
                thumbs[url] = data
    print(
        f"图片预取完成：成功 {len(thumbs)} / 失败 {len(uniq) - len(thumbs)}",
        file=sys.stderr,
    )
    return thumbs


CARDS_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6f8; color: #222; margin: 0; padding: 24px; }
.wrap { max-width: 1000px; margin: 0 auto; }
.banner { background: #fff; border: 1px solid #e3e5e8; border-radius: 14px; padding: 20px 24px; margin-bottom: 20px; }
.banner h1 { margin: 0 0 6px; font-size: 22px; }
.banner .sub { color: #666; font-size: 14px; }
.day { font-size: 17px; margin: 26px 0 4px; }
.sub { color: #666; font-size: 13px; margin-bottom: 12px; }
.grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
.card { background: #fff; border: 1px solid #e3e5e8; border-radius: 12px; padding: 16px; display: flex; flex-direction: column; }
.card-h { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.num { background: #185fa5; color: #fff; width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; flex: 0 0 auto; }
.card-h h3 { margin: 0; font-size: 16px; }
.meta { color: #666; font-size: 12.5px; margin-bottom: 8px; }
.review { font-size: 13px; color: #444; margin: 0 0 10px; line-height: 1.5; }
.thumbs { display: flex; flex-direction: row; flex-wrap: nowrap; gap: 6px; margin-top: auto; }
.thumb { margin: 0; flex: 0 0 calc((100% - 12px) / 3); min-width: 0; }
.thumb img { width: 100%; height: 84px; object-fit: cover; border-radius: 6px; border: 1px solid #eee; display: block; }
.nopic { font-size: 12.5px; color: #999; background: #fafafa; border: 1px dashed #ddd; border-radius: 8px; padding: 14px; text-align: center; margin-top: auto; }
.foot { color: #999; font-size: 12px; margin-top: 18px; line-height: 1.6; }
"""


def render_cards(codes, records, heading, sort=True, show_images=True, out_path=None):
    """生成 HTML 缩略卡页面并写入 out_path，返回路径。

    本函数只负责写 HTML 文件，文字行程单由调用方（main）另行调用 render() 输出。
    当全表图片为同一组占位图时，强制文字版（不嵌图）并标注待补齐。
    """
    if out_path is None:
        # 文件名保持纯 ASCII：部分预览服务/网关对中文路径返回 403 Forbidden
        out_path = os.path.join(os.getcwd(), "wuhan-route-" + "".join(codes) + ".html")
    # 统一成绝对路径，便于调用方直接拿去预览
    out_path = os.path.abspath(os.path.expanduser(out_path))
    groups = {c: [r for r in records if r["code"] == c] for c in codes}
    if sort:
        groups = {c: sort_spots(g) for c, g in groups.items()}
    total_hours = sum(parse_hours(r["duration"]) for c in codes for r in groups[c])
    total_spots = sum(len(groups[c]) for c in codes)
    # 占位图判定基于全量记录（全局属性），与本次渲染哪些线路无关
    placeholder = images_are_placeholder(records)

    sections = []
    # 所有缩略图复用同一个临时目录，函数结束时由 with 自动回收
    with tempfile.TemporaryDirectory() as tmpdir:
        # 先并发预取本次渲染所需的全部图片，避免逐张串行下载（实测 200 张需 160s+）
        need = []
        if show_images and not placeholder:
            for c in codes:
                for r in groups[c]:
                    for u in (r["img1"], r["img2"], r["img3"]):
                        if u and u not in need:
                            need.append(u)
        thumbs = build_thumbs(need, tmpdir) if need else {}

        for idx, code in enumerate(codes, start=1):
            group = groups[code]
            areas = []
            for r in group:
                if r["area"] and r["area"] not in areas:
                    areas.append(r["area"])
            line_hours = sum(parse_hours(r["duration"]) for r in group)
            cards = []
            for n, r in enumerate(group, start=1):
                urls = [u for u in (r["img1"], r["img2"], r["img3"]) if u]
                seen = set()
                urls = [u for u in urls if not (u in seen or seen.add(u))]
                if not show_images:
                    imgs = '<div class="nopic">已按 --no-image 隐藏图片</div>'
                elif placeholder:
                    imgs = '<div class="nopic">图片待后台补齐（当前为占位图）</div>'
                elif urls:
                    parts = []
                    for u in urls:
                        lab, rel = image_label(u)
                        data = thumbs.get(u)
                        alt = html.escape(r["spot"])
                        if data:
                            src, note = data, ""
                        else:
                            # 内联失败时回退原始外链：服务端下载不了不代表浏览器加载不了，
                            # 仍给一次机会；加载不出来由 onerror 隐藏，不留裂图
                            src, note = html.escape(u), ' data-fallback="1"'
                        parts.append(
                            '<figure class="thumb"><img src="' + src + '" alt="' + alt +
                            '" loading="lazy" onerror="this.style.display=\'none\'"' +
                            note + ' title="' + html.escape(lab) + '"></figure>'
                        )
                    imgs = '<div class="thumbs">' + "".join(parts) + '</div>' if parts else '<div class="nopic">图片加载失败</div>'
                else:
                    imgs = '<div class="nopic">暂无配图（接口未返回图片）</div>'
                # 后台表字段可能含 < > & 等字符，拼进 HTML 前一律转义
                meta = " ｜ ".join(
                    html.escape(x)
                    for x in [
                        ("类型：" + r["kind"]) if r["kind"] else "",
                        ("停留：" + r["duration"]) if r["duration"] else "",
                        ("推荐：" + r["stars"]) if r["stars"] else "",
                        ("片区：" + r["area"]) if r["area"] else "",
                    ]
                    if x
                )
                review = ('<p class="review">' + html.escape(r["review"]) + '</p>') if r["review"] else ""
                cards.append(
                    '<article class="card"><div class="card-h"><span class="num">' + str(n) +
                    '</span><h3>' + html.escape(r["spot"]) + '</h3></div><div class="meta">' +
                    meta + '</div>' + review + imgs + '</article>'
                )
            sub = ('<h2 class="day">第' + str(idx) + '天 · ' + code + ' ' + ROUTE_NAMES[code] +
                   '</h2><div class="sub">片区：' + html.escape("、".join(areas)) + ' ｜ 本线时长：' +
                   fmt_hours(line_hours) + ' ｜ ' + str(len(group)) + ' 个景点</div>')
            sections.append(sub + '<div class="grid">' + "".join(cards) + '</div>')

    banner_title = (heading.strip() + " 行程缩略卡") if heading.strip() else "武汉行程缩略卡"
    banner = ('<div class="banner"><h1>' + html.escape(banner_title) +
              '</h1><div class="sub">线路：' + "、".join(codes) + ' ｜ 全程约 ' +
              fmt_hours(total_hours) + ' ｜ 共 ' + str(total_spots) + ' 个景点</div></div>')
    foot = ('<p class="foot">图片来自接口「图片1/2/3」字段，缩放后内联，'
            '鼠标悬停图片可查看来源。相同 URL 已自动去重。'
            + ('<br>检测到全表图片为同一组占位图，卡片已隐藏图片，待后台按景点补齐真实配图后自动恢复。'
               if placeholder else '')
            + '</p>')
    doc = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' +
           html.escape(banner_title) + '</title><style>' + CARDS_CSS +
           '</style></head><body><div class="wrap">' + banner + "".join(sections) + foot +
           '</div></body></html>')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(_preview_hint(out_path), file=sys.stderr)
    return out_path


# 预览服务（WorkBuddy/IDE）通常只服务工作区目录，这些路径下的文件直接预览会返回 403
NON_PREVIEWABLE_ROOTS = ("/tmp", "/private/tmp", "/var/folders", "/private/var/folders")


def _preview_hint(path: str) -> str:
    """给出卡片路径，并在文件位于临时目录时提示预览可能返回 Forbidden。"""
    ap = os.path.abspath(path)
    if ap.startswith(NON_PREVIEWABLE_ROOTS):
        return (
            f"卡片已写入：{ap}\n"
            f"警告：该路径位于系统临时目录，预览服务通常只服务工作区，"
            f"直接预览会返回 Forbidden(403)。请用 --out 输出到工作区内的绝对路径后重试。"
        )
    return f"卡片已写入：{ap}"


def render(
    codes: list, records: list, heading: str, sort: bool = True, show_images: bool = True
) -> None:
    groups = {c: [r for r in records if r["code"] == c] for c in codes}
    if sort:
        groups = {c: sort_spots(g) for c, g in groups.items()}
    total_hours = sum(
        parse_hours(r["duration"]) for c in codes for r in groups[c]
    )
    total_spots = sum(len(groups[c]) for c in codes)
    # 与 render_cards 保持一致：全表图片为同一组占位图时不输出图片
    placeholder = show_images and images_are_placeholder(records)

    segments = []
    if heading.strip():
        segments.append(heading.strip())
    segments.append("线路 " + "、".join(codes))
    segments.append(f"全程约 {fmt_hours(total_hours)}")
    segments.append(f"共 {total_spots} 个景点")
    print("=" * 60)
    print(" " + "｜".join(segments))
    print("=" * 60)
    if placeholder:
        print("\n注：接口图片当前为同一组占位图，已省略图片输出；待后台按景点补齐后自动恢复。")

    for idx, code in enumerate(codes, start=1):
        group = groups[code]
        if not group:
            print(f"\n── 第{idx}天 · {code} {ROUTE_NAMES[code]} ──")
            print("   （该线路暂无景点记录）")
            continue
        areas = []
        for r in group:
            if r["area"] and r["area"] not in areas:
                areas.append(r["area"])
        line_hours = sum(parse_hours(r["duration"]) for r in group)
        print(f"\n── 第{idx}天 · {code} {ROUTE_NAMES[code]} ──")
        print(f"   片区：{'、'.join(areas) or '—'}｜本线时长：{fmt_hours(line_hours)}｜{len(group)} 个景点")

        for n, r in enumerate(group, start=1):
            print(f"\n   {n}. {r['spot'] or '（未命名景点）'}")
            meta = []
            if r["kind"]:
                meta.append(f"类型：{r['kind']}")
            if r["duration"]:
                meta.append(f"停留：{r['duration']}")
            if r["stars"]:
                meta.append(f"推荐指数：{r['stars']}")
            if r["area"]:
                meta.append(f"片区：{r['area']}")
            if meta:
                print(f"      {' ｜ '.join(meta)}")
            if r["review"]:
                print(f"      点评：{r['review']}")
            if show_images and not placeholder:
                imgs = [r["img1"], r["img2"], r["img3"]]
                imgs = [u for u in imgs if u]
                # 跳过已知外链被拦截的图床（如 zhihu 图床固定 403），避免前端显示裂图
                imgs = [u for u in imgs if "picx.zhimg.com" not in u]
                if imgs:
                    print(
                        "      " + " ".join(f"![{r['spot']}]({u})" for u in imgs)
                    )

    missing = [
        (b, BRANCH_HOST[b]) for b in codes if b in BRANCH_HOST and BRANCH_HOST[b] not in codes
    ]
    if missing:
        tips = "；".join(
            f"{b} {ROUTE_NAMES[b]} 通常衔接在 {h} {ROUTE_NAMES[h]} 之后"
            for b, h in missing
        )
        print(f"\n提示：{tips}。如需连贯行程请一并传入。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="武汉固定旅游线路查询（G1-G9）",
        add_help=True,
    )
    parser.add_argument(
        "codes",
        nargs="*",
        help="线路代号，可一次传多个，如 G1 G2 或 G1,G2 或 龟蛇主线",
    )
    parser.add_argument("--days", type=int, help="N 日游，自动推导线路组合（1-9）")
    parser.add_argument("--find", metavar="景点", help="按景点名反查所属线路")
    parser.add_argument("--all", action="store_true", help="输出全部 9 条线路")
    parser.add_argument(
        "--no-sort",
        action="store_true",
        help="不按「排序」字段重排景点，保留接口返回的原始顺序",
    )
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="不输出景点图片链接",
    )
    parser.add_argument(
        "--cards",
        action="store_true",
        help="输出 HTML 缩略卡（图片内联，离线可看），默认写入 ./wuhan-route-<codes>.html",
    )
    parser.add_argument(
        "--out",
        metavar="路径",
        help="--cards 模式下的 HTML 输出路径（默认 ./wuhan-route-<codes>.html）；"
        "建议指定工作区内的绝对路径，写到 /tmp 等临时目录会被预览服务拒绝",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if not (args.all or args.days is not None or args.find or args.codes):
        raise SystemExit(
            "用法: query_route.py G1 [G2 ...] | --days 3 | --find 黄鹤楼 | --all"
        )

    rows, total = fetch_records()
    records = normalize(rows)

    if args.all:
        target_codes, heading = list(ROUTE_CHAIN), "武汉全线路 "
    elif args.days is not None:
        target_codes, heading = codes_for_days(args.days), f"武汉{args.days}日游 "
    elif args.find:
        keyword = args.find.strip()
        target_codes = find_by_spot(records, keyword)
        names = "、".join(f"{c} {ROUTE_NAMES[c]}" for c in target_codes)
        print(f"景点「{keyword}」所属线路：{names}\n")
        heading = f"{keyword} 所属线路 "
    else:
        target_codes, heading = parse_codes(args.codes), ""

    # 文字行程单始终打到 stdout；--cards 时额外写一份 HTML 缩略卡
    out_path = None
    if args.cards:
        out_path = render_cards(
            target_codes,
            records,
            heading,
            sort=not args.no_sort,
            show_images=not args.no_image,
            out_path=args.out,
        )
    render(
        target_codes,
        records,
        heading,
        sort=not args.no_sort,
        show_images=not args.no_image,
    )
    if out_path:
        print(f"\n已生成缩略卡 HTML：{out_path}")
    sys.stdout.flush()
    print(f"\n---\n拉取 {len(rows)} 条 / total={total}", file=sys.stderr)
    if args.no_sort:
        print("已按接口返回顺序输出（--no-sort）", file=sys.stderr)
    else:
        problems = order_issues(records)
        if problems:
            print("排序字段异常，已按可用值递增并在异常处保持接口顺序：", file=sys.stderr)
            for item in problems:
                print(f"  - {item}", file=sys.stderr)
    if not args.no_image and not args.cards:
        for item in image_issues(records):
            print(f"图片字段提示：{item}", file=sys.stderr)


if __name__ == "__main__":
    main()
