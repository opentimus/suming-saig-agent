#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""tokenizer.py — saig-spu-rag 构建期与运行期共用的唯一分词实现。

索引与查询必须使用同一种切分方式，否则词表错位、检索静默劣化。因此：

- 文档侧：`tokenize(text, mode)`，mode 由索引里的 `tokenizer` 字段决定。
- 查询侧：`query_terms(text, mode)`，在文档侧基础上剥离意图词、加别名权重。

两种模式：
- `char-v2`（默认，零依赖）：中文按**连续汉字串**切二元组 + 非停用单字，
  英文/数字按词。旧实现把所有汉字摊平后再取二元组，跨标点、跨换行会拼出
  假词（如「…山。东湖…」拼出「山东」），这里按串切分修掉了该问题。
- `jieba-v1`（可选增强，需 `pip install jieba`）：`cut_for_search` 细分词，
  再补汉字串二元组覆盖词典外专名。

NFKC 归一让全角数字（《武汉概览》里的「1232．65」）与半角查询词对齐。
"""

import re
import unicodedata

DEFAULT_MODE = "char-v2"
MODE_CHAR = "char-v2"
MODE_JIEBA = "jieba-v1"
SUPPORTED_MODES = (MODE_CHAR, MODE_JIEBA)

# 功能字：作为单字进入索引几乎没有区分度，只在词内出现时保留
STOP_CHARS = set(
    "的了着过是在和与及等就都而并或之其为以于对从到被把个这那你我他她它们"
    "吗呢吧啊呀哦嗯很更最又还只可要想说因所但虽已经将使得太非常些每各该本"
    "有去来多好什怎如何哪谁时候一上下中"
)

# 查询侧的意图词/疑问词：只剥离，不新增，避免「是什么」「怎么」把结果带偏
INTENT_PHRASES = tuple(sorted({
    "介绍一下", "介绍", "讲解一下", "讲一下", "说说", "告诉我", "请问", "帮我",
    "帮忙", "我想知道", "想知道", "想知道", "怎么样", "怎么", "如何", "是什么",
    "什么", "有哪些", "哪些", "为什么", "多少", "多久", "多远", "多长", "在哪",
    "哪里", "是否可以", "可以", "是否", "能不能", "有没有", "一下", "推荐",
}, key=len, reverse=True))

# 口语到书面语的别名扩展：(查询中的说法) -> [补充检索词]，补充词权重 0.6
ALIASES = {
    "门票": ["票价", "开放时间"],
    "票价": ["门票"],
    "报名": ["参赛", "申请"],
    "赛制": ["比赛", "赛程"],
    "好吃": ["美食", "小吃", "过早"],
    "好玩": ["游玩", "景点", "打卡"],
    "小孩": ["亲子", "儿童"],
    "住宿": ["酒店", "民宿"],
    "怎么去": ["交通", "码头", "地铁"],
}

_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_ALNUM = re.compile(r"[a-z0-9]+")

_JIEBA = None


class TokenizerError(RuntimeError):
    """分词器不可用或与索引不匹配。"""


def jieba_module():
    """惰性导入 jieba；未安装时返回 None（不抛异常）。"""
    global _JIEBA
    if _JIEBA is None:
        try:
            import jieba  # noqa: PLC0415  （可选依赖，必须惰性导入）

            jieba.setLogLevel(60)
            _JIEBA = jieba
        except Exception:  # noqa: BLE001  （缺库/坏库一律视为不可用）
            _JIEBA = False
    return _JIEBA or None


def available_modes() -> list:
    modes = [MODE_CHAR]
    if jieba_module() is not None:
        modes.append(MODE_JIEBA)
    return modes


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def normalize_text(text: str) -> str:
    """NFKC + 小写，供检索侧做短语加成与整句子串兜底。"""
    return _normalize(text)


def _char_tokens(text: str) -> list:
    toks = _ALNUM.findall(text)
    for run in _CJK_RUN.findall(text):
        for ch in run:
            if ch not in STOP_CHARS:
                toks.append(ch)
        for i in range(len(run) - 1):
            toks.append(run[i:i + 2])
    return toks


def _jieba_tokens(text: str, jieba) -> list:
    toks = _ALNUM.findall(text)
    for word in jieba.cut_for_search(text):
        word = word.strip()
        if not word:
            continue
        if _CJK_RUN.fullmatch(word):
            if len(word) > 1:
                toks.append(word)
            elif word not in STOP_CHARS:
                toks.append(word)
        elif word.isalnum():
            toks.append(word)
    # 词典外专名（如「珞樱缤纷」）靠二元组兜底
    for run in _CJK_RUN.findall(text):
        for i in range(len(run) - 1):
            toks.append(run[i:i + 2])
    return toks


def tokenize(text: str, mode: str = DEFAULT_MODE) -> list:
    """文档侧分词：索引与统计都走这里。"""
    norm = _normalize(text)
    if mode == MODE_CHAR:
        return _char_tokens(norm)
    if mode == MODE_JIEBA:
        jieba = jieba_module()
        if jieba is None:
            raise TokenizerError(
                "索引使用 jieba-v1 分词构建，但当前环境未安装 jieba；"
                "请先 `pip install jieba`，或用 `python3 scripts/build_index.py` 重建 char-v2 索引"
            )
        return _jieba_tokens(norm, jieba)
    raise TokenizerError(f"未知分词模式「{mode}」，可选：{'、'.join(SUPPORTED_MODES)}")


def strip_intent(text: str) -> str:
    """剥离意图词/疑问词，只保留内容词。"""
    cleaned = text
    for phrase in INTENT_PHRASES:
        if phrase in cleaned:
            cleaned = cleaned.replace(phrase, " ")
    return cleaned


def is_single_char_term(term: str) -> bool:
    return len(term) == 1 and bool(_CJK_RUN.fullmatch(term))


def query_terms(text: str, mode: str = DEFAULT_MODE) -> list:
    """查询侧词项：[(term, weight, is_alias), ...]。

    内容词权重 1.0，单个汉字 0.2（区分度低），别名扩展词 0.6。
    is_alias=True 表示该词来自别名扩展而非用户原话：它只贡献分数，
    不计入覆盖度分母，否则「申请/参赛」这类扩展词会把阈值抬高、误杀正常块。
    """
    norm = _normalize(text)
    weights = {}
    for term in tokenize(strip_intent(norm) or norm, mode):
        weight = 0.2 if is_single_char_term(term) else 1.0
        if weight > weights.get(term, (0.0, False))[0]:
            weights[term] = (weight, False)
    for phrase, extras in ALIASES.items():
        if phrase not in norm:
            continue
        for extra in extras:
            for term in tokenize(extra, mode):
                weights.setdefault(term, (0.6, True))
    items = [(t, w, a) for t, (w, a) in weights.items()]
    return sorted(items, key=lambda item: (-item[1], item[0]))
