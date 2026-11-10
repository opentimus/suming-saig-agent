<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->

# 武汉知识库 API 说明

## 接口

`POST https://dify.aoaerp.com/v1/chat-messages`

请求头：

- `Authorization: Bearer <API_KEY>`
- `Content-Type: application/json`

请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `inputs` | object | 固定为 `{"type": "wuhan"}`，不允许改动 |
| `query` | string | **唯一变量**，用户关于武汉的问题 |
| `response_mode` | string | 固定 `blocking`（阻塞式，一次返回完整答案） |
| `conversation_id` | string | 传空字符串开启新会话；传入上次返回的 `conversation_id` 可延续上下文 |
| `user` | string | 用户标识，用于服务端区分调用方 |

等价的 curl 调用：

```bash
curl -X POST 'https://dify.aoaerp.com/v1/chat-messages' \
  --header 'Authorization: Bearer app-D2u0KJJJzTQBZ7DhuEBU5oNC' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "inputs": {"type":"wuhan"},
    "query": "武汉城市圈一体化建设",
    "response_mode": "blocking",
    "conversation_id": "",
    "user": "abc-123"
  }'
```

## 响应（blocking）

`event: message` 事件，主要字段：

- `answer`：回答正文（Markdown 文本）
- `conversation_id`：本次会话 ID，多轮追问时回传
- `message_id`：消息 ID
- `metadata.usage`：token 用量
- `metadata.retriever_resources`：命中的知识库文档片段列表

## 错误处理

- HTTP 400：参数缺失或格式错误（`code` 为 `invalid_param` 等）
- HTTP 401：API Key 无效
- HTTP 404：应用不存在或不可用
- HTTP 500：服务内部错误

脚本 `scripts/query_wuhan.py` 已处理上述错误并以非零退出码输出原始响应。

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `WUHAN_DIFY_API_KEY` | `app-D2u0KJJJzTQBZ7DhuEBU5oNC` | 覆盖 API Key |
| `WUHAN_DIFY_BASE_URL` | `https://dify.aoaerp.com` | 覆盖服务地址 |
| `WUHAN_DIFY_USER` | `wuhan-skill-user` | 覆盖用户标识 |
| `WUHAN_DIFY_CONVERSATION_ID` | 空 | 延续既有会话 |
