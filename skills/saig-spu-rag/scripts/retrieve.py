#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""
retrieve.py — saig-spu-rag 技能的运行时检索入口。

用法：
    python3 scripts/retrieve.py "你的查询" [top_k]

输出：JSON 数组，按 BM25 相关度降序，每条含
    id / source / section / page / score / text
其中 source 为 references/ 下的 .md 文件名，section 为章节标题；
Markdown 数据源无页码，page 恒为 null。
供 WorkBuddy 读取后基于证据作答并标注来源。

检索策略：Okapi BM25（中文单字+二元组分词）。若无任何词项命中，
则回退到「章节标题包含查询词」的块，仍无则回退到前若干块。
"""

import os
import re
import sys
import json
import math

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CHUNKS_PATH = os.path.join(SKILL_DIR, "data", "chunks.json")
INDEX_PATH = os.path.join(SKILL_DIR, "data", "index.json")

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str):
    text = text.lower()
    toks = _WORD_RE.findall(text)
    cjk = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    toks.extend(cjk)
    for i in range(len(cjk) - 1):
        toks.append(cjk[i] + cjk[i + 1])
    return toks


def load():
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    with open(INDEX_PATH, encoding="utf-8") as f:
        idx = json.load(f)
    return chunks, idx


def bm25_search(query: str, chunks, idx, top_k: int):
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    N = idx["N"]
    avgdl = idx["avgdl"]
    k1 = idx.get("k1", 1.5)
    b = idx.get("b", 0.75)
    df = idx["df"]
    postings = idx["postings"]
    doc_len = idx["doc_len"]

    scores = {}
    for t in set(q_tokens):
        if t not in postings:
            continue
        dft = df[t]
        idf = math.log((N - dft + 0.5) / (dft + 0.5) + 1)
        for doc_id, f in postings[t].items():
            did = int(doc_id)
            denom = f * (k1 + 1) / (f + k1 * (1 - b + b * doc_len[did] / avgdl))
            scores[did] = scores.get(did, 0.0) + idf * denom

    if not scores:
        return None  # 交给回退逻辑

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
    out = []
    for doc_id, sc in ranked:
        c = chunks[doc_id]
        out.append({
            "id": c["id"],
            "source": c["source"],
            "section": c.get("section", ""),
            "page": c.get("page"),
            "score": round(sc, 4),
            "text": c["text"],
        })
    return out


def fallback_title(query: str, chunks, top_k: int):
    """回退：章节标题或正文包含查询中连续词段的块。"""
    q = query.lower()
    hits = []
    for c in chunks:
        hay = ((c.get("section") or "") + " " + c["text"]).lower()
        if q in hay:
            hits.append(c)
    hits = hits[:top_k]
    return [{
        "id": c["id"], "source": c["source"],
        "section": c.get("section", ""), "page": c.get("page"),
        "score": None, "text": c["text"],
    } for c in hits]


def main():
    if len(sys.argv) < 2:
        print(json.dumps(
            {"error": "用法: python3 retrieve.py \"查询\" [top_k]"},
            ensure_ascii=False))
        sys.exit(1)
    query = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    chunks, idx = load()
    results = bm25_search(query, chunks, idx, top_k)
    if results is None:
        results = fallback_title(query, chunks, top_k)
    if not results:
        # 最后兜底：返回前 top_k 块，避免空结果
        results = [{
            "id": c["id"], "source": c["source"],
            "section": c.get("section", ""), "page": c.get("page"),
            "score": None, "text": c["text"],
        } for c in chunks[:top_k]]

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
