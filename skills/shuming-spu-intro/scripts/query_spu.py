#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""数命 SPU 知识问答：query 为唯一变量。

用法:
    python3 query_spu.py "数命SPU的定义是什么"
    python3 query_spu.py "数命SPU具备哪些能力"

可选环境变量:
    SPU_DIFY_API_KEY  覆盖默认 API Key（未设置时用 dify_client.DEFAULT_API_KEY）
    SPU_DIFY_BASE_URL 覆盖默认服务地址（默认 https://dify.aoaerp.com）
    SPU_DIFY_USER     覆盖默认用户标识（默认 spu-skill-user）
    SPU_DIFY_CONVERSATION_ID  传入会话ID以延续上下文

实现全部在 dify_client.py；本文件只声明本技能的入参与环境变量前缀。
"""

import dify_client

CONFIG = dify_client.DifyConfig(
    env_prefix="SPU",
    inputs_type="spu",
    default_user="spu-skill-user",
    default_api_key=dify_client.DEFAULT_API_KEY,
)

if __name__ == "__main__":
    dify_client.run(CONFIG, usage_hint="query_spu.py '数命SPU的定义是什么'")
