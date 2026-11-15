#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""
build_index.py — 构建 saig-spu-rag 技能的知识库索引。

流程：
  1. 扫描 references/*.md（技能自带的 Markdown 附件）作为唯一数据源，按 UTF-8 读取。
  2. 预处理 Markdown：剥离图片语法、把链接还原为可见文本。
  3. 按 Markdown 标题（`#`）、`【】` 小标题与常见章节标题分块，保留来源文件与章节标题。
  4. 构建 Okapi BM25 倒排索引（中文采用「单字 + 二元组」分词，无需任何第三方库）。
  5. 将分块与索引写入 data/chunks.json 与 data/index.json。

运行一次即可，运行期检索不再依赖原始文件（技能可独立分发）。
纯 Python 3 标准库实现：无网络、无 subprocess、无绝对路径。
依赖：仅 Python 3 标准库。
"""

import os
import re
import json
import sys

# ---------------------------------------------------------------------------
# 0. 路径配置（全部相对脚本位置推导，不写死用户目录）
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REFERENCES_DIR = os.path.join(SKILL_DIR, "references")
DATA_DIR = os.path.join(SKILL_DIR, "data")
CHUNKS_PATH = os.path.join(DATA_DIR, "chunks.json")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")

CHUNK_SIZE = 520          # 单块目标字数上限
OVERLAP_SENTENCES = 1     # 超长块拆分时的句级重叠

# 章节标题识别（行首）：
#   ① Markdown 标题 # / ## / ... ② 【xxx】 ③ 第X章/节/目 ④ 数字编号标题
MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
SECTION_RE = re.compile(
    r"^(【[^】]{1,30}】"
    r"|第[一二三四五六七八九十百零0-9]+[章节目篇部]"
    r"|[\d]+[\.、]\s*\S{1,24}"
    r")"
)


# ---------------------------------------------------------------------------
# 1. 数据源发现（references/*.md）
# ---------------------------------------------------------------------------
def discover_sources():
    """返回按文件名排序的 [(source_name, path), ...]。"""
    if not os.path.isdir(REFERENCES_DIR):
        return []
    items = []
    for name in sorted(os.listdir(REFERENCES_DIR)):
        if not name.lower().endswith(".md"):
            continue
        if name.lower() == "sources.md":   # 旧来源清单，禁止作为数据源
            continue
        items.append((name, os.path.join(REFERENCES_DIR, name)))
    return items


def clean_markdown(text: str) -> str:
    """剥离图片语法、把链接还原为可见文本，并去掉简单 HTML 标签。"""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)         # 图片 -> 移除
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)     # [文字](url) -> 文字
    text = re.sub(r"<[^>]+>", "", text)                      # 简单 HTML 标签
    return text


# ---------------------------------------------------------------------------
# 2. 分块（章节感知）
# ---------------------------------------------------------------------------
def split_into_sections(text: str):
    """按标题把文本切成若干 section，返回 [(header, [lines]), ...]。"""
    sections = []
    cur_header = ""
    cur_lines = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue

        m = MD_HEADING_RE.match(s)
        if m:
            if cur_lines:
                sections.append((cur_header, cur_lines))
                cur_lines = []
            cur_header = m.group(1).strip()
            continue

        m = SECTION_RE.match(s)
        if m:
            if cur_lines:
                sections.append((cur_header, cur_lines))
                cur_lines = []
            header = m.group(1)
            rest = s[m.end():].strip()   # 标题后的同行正文
            cur_header = header
            if rest:
                cur_lines.append(rest)
        else:
            cur_lines.append(s)

    if cur_lines:
        sections.append((cur_header, cur_lines))
    if not sections:
        sections.append(("", [""]))
    return sections


def _mk_chunk(source_name: str, header: str, text: str):
    return {
        "source": source_name,
        "section": header,
        "page": None,   # Markdown 数据源无页码
        "text": text,
    }


def build_chunks_for_section(header: str, lines, source_name: str):
    """把一个 section 的文本切成 <=CHUNK_SIZE 的字块（句级滚动 + 超长句硬切）。"""
    chunks = []
    full = "\n".join(lines)
    if len(full) <= CHUNK_SIZE:
        chunks.append(_mk_chunk(source_name, header, full))
        return chunks

    sentences = re.split(r"(?<=[。！？；])", full)
    buf = ""
    for sent in sentences:
        while len(sent) > CHUNK_SIZE:          # 超长单句：硬切
            if buf:
                chunks.append(_mk_chunk(source_name, header, buf.strip()))
                buf = ""
            chunks.append(_mk_chunk(source_name, header, sent[:CHUNK_SIZE].strip()))
            sent = sent[CHUNK_SIZE:]
        if buf and len(buf) + len(sent) > CHUNK_SIZE:
            chunks.append(_mk_chunk(source_name, header, buf.strip()))
            tail = buf.split("\n")[-OVERLAP_SENTENCES:]
            buf = "\n".join(tail) + sent
        else:
            buf += sent
    if buf.strip():
        chunks.append(_mk_chunk(source_name, header, buf.strip()))
    return chunks


def _looks_like_toc(header: str, lines) -> bool:
    """识别目录/页号清单等低信息量区块，避免其占用检索结果。"""
    if re.sub(r"\s+", "", header or "") in {"目录", "目次", "contents"}:
        return True
    body = [ln.strip() for ln in lines if ln.strip()]
    if len(body) < 5:
        return False
    numbered = sum(1 for ln in body if re.search(r"\d{2,4}$", ln))
    return numbered / len(body) >= 0.6 and sum(len(ln) for ln in body) < 600


def chunk_source(source_name: str, text: str):
    """按章节切分单个 Markdown 数据源；无标题时以文件名主干作为章节名。"""
    doc_title = os.path.splitext(source_name)[0]
    chunks = []
    for header, lines in split_into_sections(text):
        if _looks_like_toc(header, lines):
            continue
        chunks.extend(
            build_chunks_for_section(header or doc_title, lines, source_name)
        )
    return chunks


# ---------------------------------------------------------------------------
# 3. 分词（中文：单字 + 二元组；英文/数字：词）
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str):
    text = text.lower()
    toks = _WORD_RE.findall(text)
    cjk = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    toks.extend(cjk)                       # 单字
    for i in range(len(cjk) - 1):
        toks.append(cjk[i] + cjk[i + 1])  # 二元组
    return toks


# ---------------------------------------------------------------------------
# 4. BM25 索引构建
# ---------------------------------------------------------------------------
def build_bm25(chunks):
    doc_tokens = [tokenize(c["text"]) for c in chunks]
    df = {}
    postings = {}      # term -> {doc_id: tf}
    doc_len = []
    for i, toks in enumerate(doc_tokens):
        doc_len.append(len(toks))
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        for t, f in tf.items():
            postings.setdefault(t, {})[i] = f
            df[t] = df.get(t, 0) + 1
    n = len(chunks)
    avgdl = (sum(doc_len) / n) if n else 0
    return {
        "version": 1,
        "k1": 1.5,
        "b": 0.75,
        "N": n,
        "avgdl": avgdl,
        "df": df,
        "postings": postings,
        "doc_len": doc_len,
    }


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------
def main():
    sources = discover_sources()
    if not sources:
        print(f"[error] 未在 {REFERENCES_DIR} 找到任何 .md 数据源", file=sys.stderr)
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    all_chunks = []
    for name, path in sources:
        try:
            with open(path, encoding="utf-8") as f:
                text = clean_markdown(f.read())
        except OSError as e:  # noqa: BLE001
            print(f"[warn] 读取失败 {name}: {e}", file=sys.stderr)
            continue
        chunks = chunk_source(name, text)
        all_chunks.extend(chunks)
        print(f"[md] {name} -> {len(chunks)} 块", flush=True)

    if not all_chunks:
        print("[error] 未能从数据源生成任何分块", file=sys.stderr)
        sys.exit(1)

    # 赋予全局稳定 id
    for i, c in enumerate(all_chunks):
        c["id"] = i

    index = build_bm25(all_chunks)

    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=1)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)

    print(f"\n[done] 数据源 {len(sources)} 份，分块 {len(all_chunks)} 个，写入：")
    print(f"       {CHUNKS_PATH}")
    print(f"       {INDEX_PATH}")


if __name__ == "__main__":
    main()
