#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""数命 SPU 知识问答：调用 Dify 聊天消息接口，query 为唯一变量。

用法:
    python3 query_spu.py "数命SPU的定义是什么"
    python3 query_spu.py "数命SPU具备哪些能力"

可选环境变量:
    SPU_DIFY_API_KEY  覆盖默认 API Key
    SPU_DIFY_BASE_URL 覆盖默认服务地址（默认 https://dify.aoaerp.com）
    SPU_DIFY_USER     覆盖默认用户标识（默认 spu-skill-user）
    SPU_DIFY_CONVERSATION_ID  传入会话ID以延续上下文
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("SPU_DIFY_BASE_URL", "https://dify.aoaerp.com")
API_KEY = os.environ.get("SPU_DIFY_API_KEY", "app-D2u0KJJJzTQBZ7DhuEBU5oNC")
USER = os.environ.get("SPU_DIFY_USER", "spu-skill-user")
ENDPOINT = f"{BASE_URL.rstrip('/')}/v1/chat-messages"

# 固定入参，query 之外的变量不允许改动
INPUTS = {"type": "spu"}


def ask(query: str) -> dict:
    payload = {
        "inputs": INPUTS,
        "query": query,
        "response_mode": "blocking",
        "conversation_id": os.environ.get("SPU_DIFY_CONVERSATION_ID", ""),
        "user": USER,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"请求失败 HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"请求失败: {e.reason}")


def main() -> None:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        raise SystemExit("请提供 query，例如: python3 query_spu.py '数命SPU的定义是什么'")

    data = ask(query)
    answer = data.get("answer") or data.get("data", {}).get("answer") or ""
    if not answer:
        raise SystemExit(f"未获取到回答: {json.dumps(data, ensure_ascii=False)[:500]}")

    print(answer)
    metadata = data.get("metadata") or {}
    if metadata:
        usage = metadata.get("usage") or {}
        retriever = metadata.get("retriever_resources") or []
        print(
            f"\n---\nconversation_id: {data.get('conversation_id', '')} | "
            f"tokens: {usage.get('total_tokens', '-')} | 引用文档: {len(retriever)}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
