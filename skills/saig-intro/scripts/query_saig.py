#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""SAIG 数命SPU国际AI大赛知识问答：query 为唯一变量。

用法:
    python3 query_saig.py "介绍一下SAIG 数命SPU国际AI大赛"
    python3 query_saig.py "SAIG大赛的赛事时间安排是怎样的"

可选环境变量:
    SAIG_DIFY_API_KEY  覆盖默认 API Key（未设置时用 dify_client.DEFAULT_API_KEY）
    SAIG_DIFY_BASE_URL 覆盖默认服务地址（默认 https://dify.aoaerp.com）
    SAIG_DIFY_USER     覆盖默认用户标识（默认 saig-skill-user）
    SAIG_DIFY_CONVERSATION_ID  传入会话ID以延续上下文

实现全部在 dify_client.py；本文件只声明本技能的入参与环境变量前缀。
"""

import dify_client

CONFIG = dify_client.DifyConfig(
    env_prefix="SAIG",
    inputs_type="saig",
    default_user="saig-skill-user",
    default_api_key=dify_client.DEFAULT_API_KEY,
)

if __name__ == "__main__":
    dify_client.run(CONFIG, usage_hint="query_saig.py '介绍一下SAIG 数命SPU国际AI大赛'")
