#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""
retrieve.py — saig-spu-rag 技能的运行时检索入口。

用法：
    python3 scripts/retrieve.py "你的查询" [top_k]

输出：JSON 数组，按相关度降序，每条含
    id / source / section / page / score / text
其中 source 为 references/ 下的 .md 文件名，section 为章节标题；
Markdown 数据源无页码，page 恒为 null。

检索策略：
  1. 查询侧先剥离意图词/疑问词（介绍/一下/什么/怎么/多少…），再做别名扩展；
     单个汉字权重 0.2、内容词 1.0、别名扩展词 0.6，避免虚词把结果带偏。
  2. 章节加权 BM25（索引里 section 权重 4.5、正文 1.0），标题命中比正文更值钱。
  3. 覆盖度过滤：命中词权重之和不足查询总权重 30% 的块直接丢弃（降噪主力）。
     分母只算用户原话的词，别名扩展词不参与，否则会误杀只命中关键原词的块。
  4. 同一 (source, section) 去重，并按来源软配额挑选，避免单一大文档挤掉其余文档。
  5. 全部落空时再尝试「原句出现在标题/正文」的兜底；仍无命中就返回空数组，
     由上层如实说明材料未覆盖，绝不拿无关块充数。

注：曾实现「2~3 字短语连续出现加成」，实测在本语料上反而降低首条命中率
（Recall@1 0.808 → 0.731），收益与章节权重重复、且偏爱长块，故未纳入打分链路。
"""

import json
import math
import os
import sys

import tokenizer as tk

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CHUNKS_PATH = os.path.join(SKILL_DIR, "data", "chunks.json")
INDEX_PATH = os.path.join(SKILL_DIR, "data", "index.json")

INDEX_VERSION = 3
MIN_COVERAGE = 0.30        # 命中词权重占查询总权重的最低比例（评测集上调定）
SOURCE_QUOTA_RATIO = 0.6   # 单来源在首轮最多占 top_k 的比例
FALLBACK_SCORE = 0.5       # 原句兜底命中的占位分（不参与与 BM25 的比较）


def load():
    """加载分块与索引，并校验分词器与索引版本是否匹配。

    索引里倒排表是扁平数组（[doc_id, tfw, doc_id, tfw, ...]），比嵌套小数组
    少一层对象、json 解析快约 3 倍；曾试过 marshal 二进制缓存，实测反而慢 2 倍
    （嵌套小列表在 marshal 里逐元素构造），故不做解析缓存。
    """
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    with open(INDEX_PATH, encoding="utf-8") as f:
        idx = json.load(f)

    version = idx.get("version")
    if version != INDEX_VERSION:
        raise SystemExit(
            f"索引格式为 v{version}，本脚本需要 v{INDEX_VERSION}；"
            f"请运行 python3 {os.path.join(HERE, 'build_index.py')} 重建索引"
        )
    mode = idx.get("tokenizer", tk.MODE_CHAR)
    if mode not in tk.SUPPORTED_MODES:
        raise SystemExit(f"索引声明的分词器「{mode}」不受支持，请重建索引")
    if mode == tk.MODE_JIEBA and tk.jieba_module() is None:
        raise SystemExit(
            "索引由 jieba 分词构建，但当前环境未安装 jieba；"
            "请先 `pip install jieba`，或用 char 模式重建索引"
        )
    return chunks, idx


def _record(chunk, score):
    return {
        "id": chunk["id"],
        "source": chunk["source"],
        "section": chunk.get("section", ""),
        "page": chunk.get("page"),
        "score": round(score, 4),
        "text": chunk["text"],
    }


def _dedupe_and_quota(ranked, chunks, top_k):
    """按 (source, section) 去重，并按来源软配额选取，不足再按分数回填。"""
    seen_sections = set()
    unique = []
    for doc_id, score in ranked:
        chunk = chunks[doc_id]
        key = (chunk["source"], chunk.get("section", ""))
        if key in seen_sections:
            continue
        seen_sections.add(key)
        unique.append((doc_id, score))

    quota = max(1, int(round(SOURCE_QUOTA_RATIO * top_k)))
    picked, per_source, rest = [], {}, []
    for doc_id, score in unique:
        source = chunks[doc_id]["source"]
        if len(picked) < top_k and per_source.get(source, 0) < quota:
            picked.append((doc_id, score))
            per_source[source] = per_source.get(source, 0) + 1
        else:
            rest.append((doc_id, score))
    for doc_id, score in rest:
        if len(picked) >= top_k:
            break
        picked.append((doc_id, score))
    return picked[:top_k]


def bm25_search(query, chunks, idx, top_k):
    """章节加权 BM25 + 短语加成 + 覆盖度过滤；无命中返回 []。"""
    mode = idx.get("tokenizer", tk.MODE_CHAR)
    terms = tk.query_terms(query, mode)
    if not terms:
        return []

    N = idx["N"]
    avgdl = idx["avgdl"] or 1.0
    k1 = idx.get("k1", 1.2)
    b = idx.get("b", 0.6)
    postings = idx["postings"]
    doc_len = idx["doc_len"]

    # 覆盖度分母只算用户原话里的词，别名扩展词不参与，否则阈值会被虚高
    total_weight = sum(weight for _, weight, alias in terms if not alias) or 1.0
    scores = {}
    cover = {}
    for term, q_weight, _alias in terms:
        plist = postings.get(term)
        if not plist:
            continue
        dft = len(plist) // 2          # 扁平倒排表：[doc_id, tfw, doc_id, tfw, ...]
        idf = math.log(1 + (N - dft + 0.5) / (dft + 0.5))
        for pos in range(0, len(plist), 2):
            doc_id = plist[pos]
            tfw = plist[pos + 1]
            denom = tfw + k1 * (1 - b + b * doc_len[doc_id] / avgdl)
            scores[doc_id] = scores.get(doc_id, 0.0) + q_weight * idf * tfw * (k1 + 1) / denom
            cover[doc_id] = cover.get(doc_id, 0.0) + q_weight

    if not scores:
        return []

    # 覆盖度过滤：只命中一两个虚词/单字的块在这里被清掉
    threshold = MIN_COVERAGE * total_weight
    kept = [d for d in scores if cover[d] >= threshold]
    if not kept:
        return []

    ranked = sorted(
        ((doc_id, scores[doc_id]) for doc_id in kept),
        key=lambda item: (-item[1], item[0]),
    )
    picked = _dedupe_and_quota(ranked, chunks, top_k)
    return [_record(chunks[doc_id], score) for doc_id, score in picked]


def fallback_substring(query, chunks, top_k):
    """兜底：整句（归一化后）出现在章节路径或正文中的块。"""
    needle = tk.normalize_text(query).strip()
    if len(needle) < 2:
        return []
    hits = []
    for chunk in chunks:
        hay = tk.normalize_text(
            (chunk.get("section_path") or chunk.get("section") or "") + " " + chunk["text"]
        )
        if needle in hay:
            hits.append(chunk)
    hits = hits[:top_k]
    return [_record(chunk, FALLBACK_SCORE) for chunk in hits]


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
    if not results:
        results = fallback_substring(query, chunks, top_k)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
