#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""武汉景区知识问答：query 为唯一变量。

用法:
    python3 query_scenic.py "介绍一下东湖绿道"
    python3 query_scenic.py "黄鹤楼周边的半日游线路怎么安排"

可选环境变量:
    WUHAN_SCENIC_DIFY_API_KEY  覆盖默认 API Key（未设置时用 dify_client.DEFAULT_API_KEY）
    WUHAN_SCENIC_DIFY_BASE_URL 覆盖默认服务地址（默认 https://dify.aoaerp.com）
    WUHAN_SCENIC_DIFY_USER     覆盖默认用户标识（默认 wuhan-scenic-skill-user）
    WUHAN_SCENIC_DIFY_CONVERSATION_ID  传入会话ID以延续上下文

实现全部在 dify_client.py；本文件只声明本技能的入参与环境变量前缀。
注意 inputs.type 是 point（景区点位知识库），不是 scenic。
"""

import dify_client

CONFIG = dify_client.DifyConfig(
    env_prefix="WUHAN_SCENIC",
    inputs_type="point",
    default_user="wuhan-scenic-skill-user",
    default_api_key=dify_client.DEFAULT_API_KEY,
)

if __name__ == "__main__":
    dify_client.run(CONFIG, usage_hint="query_scenic.py '介绍一下东湖绿道'")
