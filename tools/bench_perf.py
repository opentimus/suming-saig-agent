#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""全项目性能基线测量。

分四块量化，避免网络波动污染同一次比较：

  1. map  —— `show_map.py` 端到端（子进程，取中位数）与产物大小；
  2. images —— route 模式图片流水线（`build_thumbs`，用离线快照里的真实 URL）；
  3. rag  —— `retrieve.py` 端到端 + 索引/分块解析耗时拆解；
  4. docs —— agents / SKILL.md 的字节数、字符数与中文 token 估算。

用法：
    python3 tools/bench_perf.py                                 # 跑全部并打印
    python3 tools/bench_perf.py --save tools/perf/baseline.json  # 固化基线
    python3 tools/bench_perf.py --compare tools/perf/baseline.json tools/perf/after.json
    python3 tools/bench_perf.py --skip-images --skip-route        # 只测不联网的部分

`--route` 会真实调用一次接口生成页面（需要联网），默认关闭；图片流水线默认开启。
"""

import argparse
import contextlib
import io
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_MAP = ROOT / "skills" / "wuhan-guide" / "scripts" / "show_map.py"
SKILL_ROUTE = ROOT / "skills" / "wuhan-guide" / "scripts" / "query_route.py"
RAG_SCRIPTS = ROOT / "skills" / "saig-spu-rag" / "scripts"
RAG_RETRIEVE = RAG_SCRIPTS / "retrieve.py"
SNAPSHOT = ROOT / "tools" / "route_snapshot.json"
MAP_IMAGE = ROOT / "skills" / "wuhan-guide" / "assets" / "wuhan-guide-map.jpg"
MAP_TEMPLATE = ROOT / "skills" / "wuhan-guide" / "assets" / "wuhan-guide-map.html"
REPORT_DEFAULT = ROOT / "tools" / "perf" / "baseline.json"

DOC_FILES = (
    "agents/jiang-xiao-shu.md",
    "skills/wuhan-guide/SKILL.md",
    "skills/saig-spu-rag/SKILL.md",
    "README.md",
)


def _median(values):
    return round(statistics.median(values), 4) if values else 0.0


def _run(cmd, timeout=300):
    return _run_check(cmd, None, timeout)


def _run_check(cmd, env=None, timeout=300):
    """按需注入环境变量（例如把缩略图缓存指到临时目录，保证冷/热可复现）。"""
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout,
        env=env,
    )
    return time.perf_counter() - started, proc


def measure_map(tmpdir: Path, rounds: int = 3) -> dict:
    times, sizes = [], None
    for _ in range(rounds):
        out = tmpdir / "map" / "wuhan-guide.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        cost, proc = _run([str(SKILL_MAP), "--out", str(out)])
        if proc.returncode != 0:
            return {"error": proc.stderr.strip()[:300]}
        times.append(cost)
        sizes = {
            "html_bytes": out.stat().st_size,
            "jpg_bytes": (out.parent / MAP_IMAGE.name).stat().st_size,
        }
    result = {"seconds_median": _median(times), "seconds_all": [round(t, 3) for t in times]}
    result.update(sizes or {})
    return result


def _snapshot_urls() -> list:
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    urls = []
    for row in rows:
        for field in row.get("payloadFieldList") or []:
            if field.get("name") not in ("图片1", "图片2", "图片3"):
                continue
            value = field.get("value")
            if isinstance(value, list) and value:
                first = value[0]
                url = (first.get("link") or first.get("text") or "") if isinstance(first, dict) else str(first)
                if isinstance(url, str) and url.startswith("http") and url not in urls:
                    urls.append(url)
    return urls


def measure_images(tmpdir: Path) -> dict:
    """复用 query_route 的缩略图流水线，分别测冷启动与缓存命中两条路径。"""
    sys.path.insert(0, str(SKILL_MAP.parent))
    import query_route as qr  # noqa: PLC0415

    urls = _snapshot_urls()
    if not urls:
        return {"error": "快照中没有图片 URL"}

    supports = _supports_no_cache(qr)
    workdir = tmpdir / "thumbs"
    workdir.mkdir(parents=True, exist_ok=True)

    def run(no_cache: bool):
        buffer = io.StringIO()
        started = time.perf_counter()
        with contextlib.redirect_stderr(buffer):
            if supports:
                thumbs = qr.build_thumbs(urls, str(workdir), no_cache=no_cache)
            else:
                thumbs = qr.build_thumbs(urls, str(workdir))
        return {
            "seconds": round(time.perf_counter() - started, 3),
            "ok": len(thumbs),
            "payload_bytes": sum(len(v) for v in thumbs.values()),
        }

    old_cache = os.environ.get("WUHAN_GUIDE_CACHE")
    os.environ["WUHAN_GUIDE_CACHE"] = str(tmpdir / "cache-images")
    try:
        cold = run(True)
        warm_first = run(False)
        warm = run(False)
    finally:
        if old_cache is None:
            os.environ.pop("WUHAN_GUIDE_CACHE", None)
        else:
            os.environ["WUHAN_GUIDE_CACHE"] = old_cache
    return {
        "urls": len(urls),
        "seconds_median": cold["seconds"],      # 与旧报告同名字段，便于跨版本对比
        "cold_seconds": cold["seconds"],
        "warm_first_seconds": warm_first["seconds"],
        "warm_seconds": warm["seconds"],
        "cache": "on" if supports else "off",
        "ok": cold["ok"],
        "payload_bytes": cold["payload_bytes"],
        "warm_payload_bytes": warm["payload_bytes"],
    }


def _supports_no_cache(module) -> bool:
    import inspect  # noqa: PLC0415

    return "no_cache" in inspect.signature(module.build_thumbs).parameters


def measure_rag(rounds: int = 3) -> dict:
    times = []
    for _ in range(rounds):
        cost, proc = _run([str(RAG_RETRIEVE), "武汉有多少人口", "4"])
        if proc.returncode != 0:
            return {"error": proc.stderr.strip()[:300]}
        times.append(cost)

    sys.path.insert(0, str(RAG_SCRIPTS))
    import retrieve as rag  # noqa: PLC0415

    load_times, search_times = [], []
    chunks = idx = None
    for _ in range(rounds):
        started = time.perf_counter()
        chunks, idx = rag.load()
        load_times.append(time.perf_counter() - started)
        started = time.perf_counter()
        rag.bm25_search("武汉有多少人口", chunks, idx, 4)
        search_times.append(time.perf_counter() - started)
    return {
        "cli_seconds_median": _median(times),
        "cli_seconds_all": [round(t, 3) for t in times],
        "load_seconds_median": _median(load_times),
        "search_seconds_median": _median(search_times),
        "index_bytes": (RAG_SCRIPTS.parent / "data" / "index.json").stat().st_size,
        "chunks_bytes": (RAG_SCRIPTS.parent / "data" / "chunks.json").stat().st_size,
    }


def measure_route(tmpdir: Path) -> dict:
    """真实线路查询两次：第一次冷缓存，第二次命中缩略图缓存。"""
    out = tmpdir / "route" / "wuhan-guide.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    # 独立缓存目录：避免图片基准预热缓存后把 route「冷启动」测成热启动
    env = dict(os.environ, WUHAN_GUIDE_CACHE=str(tmpdir / "cache-route"))
    cold, proc = _run_check([str(SKILL_ROUTE), "--days", "2", "--out", str(out)], env)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()[:400]}
    warm, proc2 = _run_check([str(SKILL_ROUTE), "--days", "2", "--out", str(out)], env)
    if proc2.returncode != 0:
        return {"error": proc2.stderr.strip()[:400]}
    return {
        "seconds": round(cold, 3),          # 与旧报告同名字段（冷启动）
        "cold_seconds": round(cold, 3),
        "warm_seconds": round(warm, 3),
        "html_bytes": out.stat().st_size,
        "jpg_bytes": (out.parent / MAP_IMAGE.name).stat().st_size,
        "stderr_tail": proc2.stderr.strip().splitlines()[-3:],
    }


def measure_docs() -> dict:
    docs = {}
    for rel in DOC_FILES:
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        docs[rel] = {
            "bytes": path.stat().st_size,
            "chars": len(text),
            # 中文为主：约 1.6 字符/token，仅用于粗略比较
            "tokens_est": int(len(text) / 1.6),
        }
    return docs


def measure_assets() -> dict:
    return {
        "map_jpg_bytes": MAP_IMAGE.stat().st_size,
        "map_template_bytes": MAP_TEMPLATE.stat().st_size,
        "dist_zip_bytes": max((p.stat().st_size for p in (ROOT / "dist").glob("*.zip")), default=0),
    }


def collect(args) -> dict:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmpdir = Path(raw_tmp)
        report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "python": sys.version.split()[0]}
        report["assets"] = measure_assets()
        report["docs"] = measure_docs()
        report["map"] = measure_map(tmpdir)
        report["rag"] = measure_rag()
        report["images"] = {} if args.skip_images else measure_images(tmpdir)
        report["route"] = measure_route(tmpdir) if args.route else {"skipped": True}
    return report


def print_report(report: dict) -> None:
    assets, docs = report.get("assets", {}), report.get("docs", {})
    print(f"采集时间 {report.get('generated_at')}  Python {report.get('python')}")
    print(f"\n[体积] 底图 {assets.get('map_jpg_bytes', 0)/1024:.0f}KB  "
          f"模板 {assets.get('map_template_bytes', 0)/1024:.0f}KB  "
          f"包 {assets.get('dist_zip_bytes', 0)/1024/1024:.2f}MB")

    mp = report.get("map", {})
    if "error" in mp:
        print(f"\n[map] 失败：{mp['error']}")
    else:
        print(f"\n[map] 端到端中位数 {mp['seconds_median']:.3f}s  "
              f"HTML {mp['html_bytes']/1024:.0f}KB  + 底图 {mp['jpg_bytes']/1024:.0f}KB")

    images = report.get("images") or {}
    if images and "error" not in images:
        print(f"[images] {images['urls']} 张  冷 {images['seconds_median']:.1f}s / "
              f"热 {images.get('warm_seconds', 0):.1f}s  成功 {images['ok']}  "
              f"内联 {images['payload_bytes']/1024/1024:.2f}MB  缓存 {images['cache']}")
    elif images:
        print(f"[images] 失败：{images['error']}")

    rag = report.get("rag", {})
    if "error" in rag:
        print(f"[rag] 失败：{rag['error']}")
    else:
        print(f"[rag] CLI 中位数 {rag['cli_seconds_median']:.3f}s  "
              f"load {rag['load_seconds_median']*1000:.0f}ms  "
              f"search {rag['search_seconds_median']*1000:.1f}ms  "
              f"索引 {rag['index_bytes']/1024/1024:.2f}MB")

    route = report.get("route", {})
    if route.get("skipped"):
        print("[route] 跳过（未联网）")
    elif "error" in route:
        print(f"[route] 失败：{route['error']}")
    else:
        print(f"[route] --days 2 端到端 {route['seconds']:.1f}s  HTML {route['html_bytes']/1024:.0f}KB")

    print("\n[docs] 字节 / 字符 / 估算 token")
    for rel, info in docs.items():
        print(f"  {rel:<34} {info['bytes']:>7} {info['chars']:>7} {info['tokens_est']:>7}")


def compare(old_path: Path, new_path: Path) -> None:
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))

    def pick(report, *keys, default=0):
        node = report
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
        return node if node is not None else default

    rows = [
        ("底图字节", pick(old, "assets", "map_jpg_bytes"), pick(new, "assets", "map_jpg_bytes"), False),
        ("map 端到端(s)", pick(old, "map", "seconds_median"), pick(new, "map", "seconds_median"), False),
        ("map HTML 字节", pick(old, "map", "html_bytes"), pick(new, "map", "html_bytes"), False),
        ("图片流水线(s)", pick(old, "images", "seconds_median"), pick(new, "images", "seconds_median"), False),
        ("图片流水线热(s)", pick(old, "images", "warm_seconds"), pick(new, "images", "warm_seconds"), False),
        ("缩略图内联字节", pick(old, "images", "payload_bytes"), pick(new, "images", "payload_bytes"), False),
        ("RAG CLI(s)", pick(old, "rag", "cli_seconds_median"), pick(new, "rag", "cli_seconds_median"), False),
        ("RAG load(s)", pick(old, "rag", "load_seconds_median"), pick(new, "rag", "load_seconds_median"), False),
        ("RAG 索引字节", pick(old, "rag", "index_bytes"), pick(new, "rag", "index_bytes"), False),
        ("route 冷启动(s)", pick(old, "route", "seconds"), pick(new, "route", "seconds"), False),
        ("route 缓存命中(s)", pick(old, "route", "warm_seconds"), pick(new, "route", "warm_seconds"), False),
        ("route HTML 字节", pick(old, "route", "html_bytes"), pick(new, "route", "html_bytes"), False),
        ("包体积字节", pick(old, "assets", "dist_zip_bytes"), pick(new, "assets", "dist_zip_bytes"), False),
    ]
    print(f"{'指标':<18}{'改造前':>12}{'改造后':>12}{'变化':>14}")
    for label, before, after, _ in rows:
        if not before or not after:
            continue
        pct = (after - before) / before * 100
        print(f"{label:<18}{before:>12.4g}{after:>12.4g}{pct:>+13.1f}%")

    old_docs, new_docs = old.get("docs", {}), new.get("docs", {})
    if old_docs and new_docs:
        print("\n文档 token 估算：")
        for rel in old_docs:
            before = old_docs[rel]["tokens_est"]
            after = new_docs.get(rel, {}).get("tokens_est")
            if after is None:
                print(f"  {rel:<34}{before:>7} -> 已移除/迁移")
                continue
            print(f"  {rel:<34}{before:>7} -> {after:>7}  ({(after-before)/before*100:+.0f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description="全项目性能基线测量")
    parser.add_argument("--save", default=str(REPORT_DEFAULT), help="报告写入路径")
    parser.add_argument("--route", action="store_true", help="额外跑一次真实线路查询（需联网）")
    parser.add_argument("--skip-images", action="store_true", help="跳过图片流水线（需联网）")
    parser.add_argument("--image-rounds", type=int, default=2, help="图片流水线重复次数")
    parser.add_argument("--compare", nargs=2, metavar=("改造前", "改造后"), help="对比两份报告")
    args = parser.parse_args()

    if args.compare:
        compare(Path(args.compare[0]), Path(args.compare[1]))
        return 0

    report = collect(args)
    print_report(report)
    out = Path(args.save)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
