#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""saig-spu-rag 检索回归评测工具。

按评测集逐条调用真实 CLI（`skills/saig-spu-rag/scripts/retrieve.py`），
统计 Recall@1/3/5、MRR@5 与越界问句的误答率，并支持与历史报告对比：

    python3 tools/eval_rag.py                                  # 跑评测并打印摘要
    python3 tools/eval_rag.py --save tools/eval/baseline_v1.json  # 固化基线报告
    python3 tools/eval_rag.py --compare tools/eval/baseline_v1.json tools/eval/current.json

走子进程而不是 import，是为了测到生产路径（含索引加载与 JSON 输出）。
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RETRIEVE = ROOT / "skills" / "saig-spu-rag" / "scripts" / "retrieve.py"
DEFAULT_SET = ROOT / "tools" / "eval" / "rag_eval_set.json"
DEFAULT_TOP_K = 5


def sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()[:16]


def run_query(query: str, top_k: int) -> list:
    """调用一次检索 CLI，返回解析后的结果列表。"""
    proc = subprocess.run(
        [sys.executable, str(RETRIEVE), query, str(top_k)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"retrieve.py 退出码 {proc.returncode}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"retrieve.py 输出不是合法 JSON：{exc}")
    if not isinstance(data, list):
        raise RuntimeError("retrieve.py 输出既不是数组，也不是预期的错误结构")
    return data


def matches(expect: dict, result: dict) -> bool:
    """source 与 section 均按子串匹配，容忍分块标题的细微差异。"""
    source = expect.get("source") or ""
    section = expect.get("section") or ""
    if not source and not section:
        return False
    got_source = result.get("source") or ""
    got_section = result.get("section") or ""
    if source and source not in got_source:
        return False
    if section:
        if not got_section:
            return False
        if section not in got_section and got_section not in section:
            return False
    return True


def first_rank(expect: list, results: list) -> int:
    """返回首个命中期望的排名（1 起），未命中返回 0。"""
    for rank, result in enumerate(results, start=1):
        for item in expect:
            if matches(item, result):
                return rank
    return 0


def evaluate(cases: list, top_k: int) -> dict:
    records = []
    for case in cases:
        query = case["query"]
        expect = case.get("expect") or []
        started = time.time()
        try:
            results = run_query(query, top_k)
            error = ""
        except RuntimeError as exc:
            results, error = [], str(exc)
        cost = time.time() - started
        rank = first_rank(expect, results) if expect else 0
        records.append({
            "query": query,
            "expect": expect,
            "first_rank": rank,
            "seconds": round(cost, 3),
            "error": error,
            "got": [
                {
                    "rank": i,
                    "source": r.get("source"),
                    "section": r.get("section"),
                    "score": r.get("score"),
                }
                for i, r in enumerate(results, start=1)
            ],
        })
    return {"records": records, "metrics": summarize(records, top_k)}


def summarize(records: list, top_k: int) -> dict:
    in_scope = [r for r in records if r["expect"]]
    out_scope = [r for r in records if not r["expect"]]
    ranks = [r["first_rank"] for r in in_scope]
    total = len(in_scope) or 1

    def recall(k: int) -> float:
        return round(sum(1 for r in ranks if 0 < r <= k) / total, 4)

    mrr = sum(1.0 / r for r in ranks if 0 < r <= 5) / total
    false_positive = sum(1 for r in out_scope if r["got"])
    return {
        "in_scope": len(in_scope),
        "out_scope": len(out_scope),
        "recall@1": recall(1),
        "recall@3": recall(3),
        "recall@5": recall(5),
        "mrr@5": round(mrr, 4),
        "out_of_scope_fp_rate": round(false_positive / len(out_scope), 4) if out_scope else 0.0,
        "errors": sum(1 for r in records if r["error"]),
        "avg_seconds": round(sum(r["seconds"] for r in records) / (len(records) or 1), 3),
        "top_k": top_k,
    }


def print_summary(report: dict, verbose: bool) -> None:
    metrics = report["metrics"]
    print(f"评测集：{len(report['records'])} 条（覆盖问题 {metrics['in_scope']}，"
          f"越界 {metrics['out_scope']}），top_k={metrics['top_k']}")
    print(f"Recall@1={metrics['recall@1']:.3f}  Recall@3={metrics['recall@3']:.3f}  "
          f"Recall@5={metrics['recall@5']:.3f}  MRR@5={metrics['mrr@5']:.3f}")
    print(f"越界误答率={metrics['out_of_scope_fp_rate']:.3f}  "
          f"单次调用 {metrics['avg_seconds']:.3f}s  错误 {metrics['errors']} 条")

    missed = [r for r in report["records"] if r["expect"] and not r["first_rank"]]
    if missed:
        print("\n未命中（前 3 名）：")
        for r in missed:
            top = "；".join(
                f"{g['source']}/{g['section']}" for g in r["got"][:3]
            ) or "（空）"
            want = "；".join(f"{e['source']}/{e['section']}" for e in r["expect"])
            print(f"  - {r['query']}\n      期望 {want}\n      实得 {top}")

    fp = [r for r in report["records"] if not r["expect"] and r["got"]]
    if fp:
        print("\n越界问句误答（应返回空）：")
        for r in fp:
            top = "；".join(f"{g['source']}/{g['section']}" for g in r["got"][:2])
            print(f"  - {r['query']} -> {top}")

    if verbose:
        print("\n逐条结果：")
        for r in report["records"]:
            if not r["expect"]:
                state = "空" if not r["got"] else "误报"
            elif r["first_rank"]:
                state = f"rank={r['first_rank']}"
            else:
                state = "miss"
            print(f"  [{state}] {r['query']}")


def compare(old_path: Path, new_path: Path) -> None:
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))
    om, nm = old["metrics"], new["metrics"]
    keys = [
        ("recall@1", "Recall@1", True),
        ("recall@3", "Recall@3", True),
        ("recall@5", "Recall@5", True),
        ("mrr@5", "MRR@5", True),
        ("out_of_scope_fp_rate", "越界误答率", False),
        ("avg_seconds", "单次调用耗时(s)", False),
    ]
    print(f"基线：{old_path}")
    print(f"当前：{new_path}\n")
    print(f"{'指标':<16}{'基线':>10}{'当前':>10}{'变化':>12}")
    for key, label, higher_better in keys:
        before, after = om.get(key, 0), nm.get(key, 0)
        delta = after - before
        mark = ""
        if abs(delta) > 1e-9:
            better = delta > 0 if higher_better else delta < 0
            mark = ("  ↑" if delta > 0 else "  ↓") + ("" if better else "（变差）")
        print(f"{label:<16}{before:>10.4f}{after:>10.4f}{delta:>+12.4f}{mark}")

    old_ranks = {r["query"]: r["first_rank"] for r in old["records"]}
    ups, downs, same = [], [], 0
    for record in new["records"]:
        before = old_ranks.get(record["query"])
        if before is None:
            continue
        after = record["first_rank"]
        if after == before:
            same += 1
            continue
        improved = (before == 0 and after > 0) or (
            0 < after < before if before else False
        )
        (ups if improved else downs).append((record["query"], before, after))
    print(f"\n逐条：改善 {len(ups)}，变差 {len(downs)}，持平 {same}")
    for query, before, after in downs:
        print(f"  - 变差 {query}：{before or 'miss'} -> {after or 'miss'}")
    for query, before, after in ups:
        print(f"  + 改善 {query}：{before or 'miss'} -> {after}")


def main() -> int:
    parser = argparse.ArgumentParser(description="saig-spu-rag 检索回归评测")
    parser.add_argument("--set", default=str(DEFAULT_SET), help="评测集路径")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="每条问句取前 k 条")
    parser.add_argument("--save", default="", help="把完整报告写入该路径")
    parser.add_argument("--verbose", action="store_true", help="打印逐条结果")
    parser.add_argument("--compare", nargs=2, metavar=("基线", "当前"),
                        help="对比两份报告，不跑评测")
    args = parser.parse_args()

    if args.compare:
        compare(Path(args.compare[0]), Path(args.compare[1]))
        return 0

    data = json.loads(Path(args.set).read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    if not cases:
        print(f"错误：评测集为空（{args.set}）", file=sys.stderr)
        return 2

    result = evaluate(cases, args.top_k)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "eval_set": str(Path(args.set).resolve().relative_to(ROOT)),
        "eval_set_sha256": sha256(Path(args.set)),
        "engine": {
            "retrieve": str(RETRIEVE.relative_to(ROOT)),
            "retrieve_sha256": sha256(RETRIEVE),
            "index_sha256": sha256(ROOT / "skills" / "saig-spu-rag" / "data" / "index.json"),
        },
        "metrics": result["metrics"],
        "records": result["records"],
    }
    print_summary(report, args.verbose)

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
