#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""Dify 聊天消息接口的公共客户端（唯一实现，禁止手改各技能的副本）。

本文件是 4 个 Dify 问答技能的唯一实现来源：
    skills/saig-intro/scripts/dify_client.py
    skills/shuming-spu-intro/scripts/dify_client.py
    skills/wuhan-intro/scripts/dify_client.py
    skills/wuhan-scenic-intro/scripts/dify_client.py

为什么不跨技能 import：技能按目录独立安装（宿主把每个 `skills/<name>/` 拷到技能目录下），
跨技能相对路径在安装后会失效。因此采用「单一来源 + 同步副本」：
修改本文件后执行 `python3 tools/sync_dify_client.py --write` 覆盖四份副本，
`--check` 可在 CI 或提交前校验副本是否漂移。

调用约定（各技能 query 脚本已封装，无需直接使用本模块）：
    python3 scripts/query_xxx.py "你的问题"
答案写 stdout，元数据（conversation_id / token / 引用文档数）写 stderr。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://dify.aoaerp.com"
TIMEOUT_SECONDS = 120
ENDPOINT_PATH = "/v1/chat-messages"

# 4 个 Dify 技能共用的知识库应用 Key。原先复制在 4 个脚本里，现集中到本文件一处；
# 生产环境建议改为只从环境变量读取（置空此值即可强制要求显式配置）。
DEFAULT_API_KEY = "app-D2u0KJJJzTQBZ7DhuEBU5oNC"


class DifyConfig:
    """一个 Dify 应用的调用配置；环境变量名由技能前缀派生，便于逐技能覆盖。"""

    def __init__(self, *, env_prefix: str, inputs_type: str, default_user: str,
                 default_api_key: str = "") -> None:
        self.env_prefix = env_prefix
        self.inputs_type = inputs_type
        self.default_user = default_user
        self.default_api_key = default_api_key
        self.base_url = os.environ.get(f"{env_prefix}_DIFY_BASE_URL", DEFAULT_BASE_URL)
        self.api_key = os.environ.get(f"{env_prefix}_DIFY_API_KEY", default_api_key)
        self.user = os.environ.get(f"{env_prefix}_DIFY_USER", default_user)
        self.conversation_env = f"{env_prefix}_DIFY_CONVERSATION_ID"

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}{ENDPOINT_PATH}"

    def require_api_key(self) -> str:
        if not self.api_key:
            raise SystemExit(
                f"缺少 API Key：请设置环境变量 {self.env_prefix}_DIFY_API_KEY"
            )
        return self.api_key


def ask(config: DifyConfig, query: str) -> dict:
    """发一次 blocking 请求，返回原始响应体；HTTP/网络错误按原始信息抛出。"""
    payload = {
        "inputs": {"type": config.inputs_type},
        "query": query,
        "response_mode": "blocking",
        "conversation_id": os.environ.get(config.conversation_env, ""),
        "user": config.user,
    }
    req = urllib.request.Request(
        config.endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.require_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"请求失败 HTTP {exc.code}: {body}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"请求失败: {exc.reason}")


def run(config: DifyConfig, argv: list[str] | None = None, usage_hint: str = "") -> None:
    """脚本入口：拼接 query、取 answer、stdout 正文 + stderr 元数据。"""
    args = sys.argv[1:] if argv is None else argv
    query = " ".join(args).strip()
    if not query:
        hint = f"，例如: python3 {usage_hint}" if usage_hint else ""
        raise SystemExit(f"请提供 query{hint}")

    data = ask(config, query)
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
