#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""
build_index.py — 构建 saig-spu-rag 技能的知识库索引。

流程：
  1. 扫描 references/*.md（技能自带的 Markdown 附件）作为唯一数据源，按 UTF-8 读取。
  2. 预处理 Markdown：剥离图片语法、把链接还原为可见文本。
  3. 按 Markdown 标题（`#`）、`【】` 小标题与常见章节标题分块，保留来源文件、
     叶子章节标题与「父级 > 叶子」的章节路径。
  4. 构建章节加权的 Okapi BM25 索引（BM25F 的单字段近似）：
     section 权重 3.0、正文 1.0，词频按字段加权后合并为一个加权词频。
  5. 剪枝：停用字不入索引；单字词项中 df/N > 0.6 的近通用字（的/区/汉/大/武…）
     直接丢弃——它们在几乎所有块里都出现，只会抬高噪声块的分数。
  6. 将分块与索引写入 data/chunks.json 与 data/index.json（格式 v2）。

运行一次即可，运行期检索不再依赖原始文件（技能可独立分发）。
分词实现统一由 tokenizer.py 提供，构建期与运行期必须是同一种模式。

用法：
    python3 scripts/build_index.py                  # 默认 char-v2，零依赖
    python3 scripts/build_index.py --tokenizer jieba  # 需 pip install jieba，仅本地对照
"""

import argparse
import json
import os
import re
import sys

import tokenizer as tk

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

INDEX_VERSION = 3
FIELD_WEIGHTS = {"section": 4.5, "text": 1.0}   # 评测集扫描后的取值
BM25_K1 = 1.5
BM25_B = 0.75
COMMON_SINGLE_DF_RATIO = 0.3   # 单字词项 df/N 超过该比例即视为近通用字，剪掉

# 章节标题识别（行首）：
#   ① Markdown 标题 # / ## / ... ② 【xxx】 ③ 第X章/节/目 ④ 数字编号标题
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
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
# 2. 分块（章节感知，保留父级标题）
# ---------------------------------------------------------------------------
def split_into_sections(text: str):
    """按标题把文本切成若干 section，返回 [(header, parent, [lines]), ...]。

    parent 只对「二级以上标题之下的小标题」有值，用于把「人口·民族宗教 >
    【人口分布】」这类上下文带进索引：查询「武汉人口」时标题字段能直接命中。
    """
    sections = []
    cur_header = ""
    cur_parent = ""
    cur_lines = []
    top_title = ""

    def flush():
        if cur_lines:
            sections.append((cur_header, cur_parent, list(cur_lines)))

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue

        m = MD_HEADING_RE.match(s)
        if m:
            flush()
            cur_lines = []
            level = len(m.group(1))
            title = m.group(2).strip()
            if level <= 2:
                top_title = title
                cur_header, cur_parent = title, ""
            else:
                cur_header, cur_parent = title, top_title
            continue

        m = SECTION_RE.match(s)
        if m:
            flush()
            cur_lines = []
            cur_header = m.group(1)
            cur_parent = top_title
            rest = s[m.end():].strip()   # 标题后的同行正文
            if rest:
                cur_lines.append(rest)
        else:
            cur_lines.append(s)

    flush()
    if not sections:
        sections.append(("", "", [""]))
    return sections


def _mk_chunk(source_name: str, header: str, parent: str, text: str):
    path = f"{parent} > {header}" if parent and parent != header else header
    return {
        "source": source_name,
        "section": header,
        "section_path": path,
        "page": None,   # Markdown 数据源无页码
        "text": text,
    }


def build_chunks_for_section(header: str, parent: str, lines, source_name: str):
    """把一个 section 的文本切成 <=CHUNK_SIZE 的字块（句级滚动 + 超长句硬切）。"""
    chunks = []
    full = "\n".join(lines)
    if len(full) <= CHUNK_SIZE:
        chunks.append(_mk_chunk(source_name, header, parent, full))
        return chunks

    sentences = re.split(r"(?<=[。！？；])", full)
    buf = ""
    for sent in sentences:
        while len(sent) > CHUNK_SIZE:          # 超长单句：硬切
            if buf:
                chunks.append(_mk_chunk(source_name, header, parent, buf.strip()))
                buf = ""
            chunks.append(_mk_chunk(source_name, header, parent, sent[:CHUNK_SIZE].strip()))
            sent = sent[CHUNK_SIZE:]
        if buf and len(buf) + len(sent) > CHUNK_SIZE:
            chunks.append(_mk_chunk(source_name, header, parent, buf.strip()))
            tail = buf.split("\n")[-OVERLAP_SENTENCES:]
            buf = "\n".join(tail) + sent
        else:
            buf += sent
    if buf.strip():
        chunks.append(_mk_chunk(source_name, header, parent, buf.strip()))
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
    for header, parent, lines in split_into_sections(text):
        if _looks_like_toc(header, lines):
            continue
        chunks.extend(
            build_chunks_for_section(header or doc_title, parent, lines, source_name)
        )
    return chunks


# ---------------------------------------------------------------------------
# 3. BM25 索引构建（章节加权 + 词项剪枝）
# ---------------------------------------------------------------------------
def build_bm25(chunks, mode: str):
    """返回索引字典：postings[term] = [doc_id, 加权词频, doc_id, 加权词频, ...]。

    加权词频 tfw = 4.5*tf(章节路径) + 1.0*tf(正文)，doc_len 用加权长度，
    等价于 BM25F 的单字段近似：标题命中比正文命中更值钱。
    倒排表用「扁平数组」而不是 [[id, w], ...]：同样的数据在 json 里少一层嵌套，
    解析耗时实测降到约 1/3（1.15MB/293ms → 0.95MB/101ms，高负载机器上的中位数）。
    """
    postings = {}
    doc_len = []
    for doc_id, chunk in enumerate(chunks):
        tf = {}
        section = chunk.get("section_path") or chunk.get("section") or ""
        for term in tk.tokenize(section, mode):
            tf[term] = tf.get(term, 0.0) + FIELD_WEIGHTS["section"]
        for term in tk.tokenize(chunk["text"], mode):
            tf[term] = tf.get(term, 0.0) + FIELD_WEIGHTS["text"]
        doc_len.append(round(sum(tf.values()), 3))
        for term, weight in tf.items():
            postings.setdefault(term, []).extend((doc_id, round(weight, 3)))

    total = len(chunks)
    dropped = {}
    for term in list(postings):
        if total <= 1:
            break
        if tk.is_single_char_term(term) and len(postings[term]) / 2 / total > COMMON_SINGLE_DF_RATIO:
            dropped[term] = len(postings.pop(term)) // 2
    avgdl = (sum(doc_len) / total) if total else 0.0
    return {
        "version": INDEX_VERSION,
        "tokenizer": mode,
        "fields": FIELD_WEIGHTS,
        "k1": BM25_K1,
        "b": BM25_B,
        "N": total,
        "avgdl": avgdl,
        "postings": postings,
        "doc_len": doc_len,
    }, dropped


# ---------------------------------------------------------------------------
# 4. 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="构建 saig-spu-rag 知识库索引")
    parser.add_argument(
        "--tokenizer", default="char", choices=["char", "jieba"],
        help="分词模式：char（默认，零依赖，随包分发）或 jieba（需 pip install jieba）",
    )
    args = parser.parse_args()
    mode = tk.MODE_CHAR if args.tokenizer == "char" else tk.MODE_JIEBA
    if mode == tk.MODE_JIEBA and tk.jieba_module() is None:
        print("[error] 未安装 jieba，无法用 jieba 模式构建；请 pip install jieba", file=sys.stderr)
        sys.exit(1)

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

    index, dropped = build_bm25(all_chunks, mode)

    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=1)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        # 紧凑分隔符：索引是纯机器读取的倒排表，去掉默认的 ", " / ": " 空格可省一批字节
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(INDEX_PATH) / 1024 / 1024
    print(f"\n[stat] 分词模式 {mode}，分块 {len(all_chunks)} 个，"
          f"词项 {len(index['postings'])} 个（剪枝近通用单字 {len(dropped)} 个），"
          f"索引 {size_mb:.2f}MB，平均加权长度 {index['avgdl']:.1f}")
    if dropped:
        top = sorted(dropped.items(), key=lambda kv: -kv[1])[:10]
        print("[stat] 剪枝示例：" + "、".join(f"{t}({n})" for t, n in top))
    print(f"[done] 数据源 {len(sources)} 份，写入：")
    print(f"       {CHUNKS_PATH}")
    print(f"       {INDEX_PATH}")


if __name__ == "__main__":
    main()
