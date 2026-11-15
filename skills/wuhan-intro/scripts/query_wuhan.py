#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""武汉知识问答：query 为唯一变量。

用法:
    python3 query_wuhan.py "武汉城市圈一体化建设"
    python3 query_wuhan.py "武汉的建置沿革是怎样的"

可选环境变量:
    WUHAN_DIFY_API_KEY  覆盖默认 API Key（未设置时用 dify_client.DEFAULT_API_KEY）
    WUHAN_DIFY_BASE_URL 覆盖默认服务地址（默认 https://dify.aoaerp.com）
    WUHAN_DIFY_USER     覆盖默认用户标识（默认 wuhan-skill-user）
    WUHAN_DIFY_CONVERSATION_ID  传入会话ID以延续上下文

实现全部在 dify_client.py；本文件只声明本技能的入参与环境变量前缀。
"""

import dify_client

CONFIG = dify_client.DifyConfig(
    env_prefix="WUHAN",
    inputs_type="wuhan",
    default_user="wuhan-skill-user",
    default_api_key=dify_client.DEFAULT_API_KEY,
)

if __name__ == "__main__":
    dify_client.run(CONFIG, usage_hint="query_wuhan.py '武汉城市圈一体化建设'")
