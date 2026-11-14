<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->

# 武汉旅游线路接口说明

## 接口

`POST https://admin.aoaerp.com/api/lowcode/normal/dify/app/table/record/page?pageNum=1&pageSize=100`

> **路径不含 `/v1` 前缀。** `https://admin.aoaerp.com/v1/api/lowcode/...` 会返回 nginx 的 `405 Not Allowed`——该路径被当作静态资源处理，GET 兜底返回 aoa-portal 前端 SPA 页面，POST 则被拒绝。可用路径为 `/api/lowcode/...`。

请求头：

- `Authorization: Bearer <TOKEN>`
- `Content-Type: application/json`

请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `appName` | string | 固定 `SPU` |
| `tableName` | string | 固定 `旅遊线路`（繁体，勿改） |
| `record` | object | **必须存在**，可为空对象 `{}`；**省略该字段接口会返回空结果**（实测 `rows=0`） |

最小可用请求体：

```json
{"appName":"SPU","tableName":"旅遊线路","record":{}}
```

原始调用示例：

```bash
curl -X POST 'https://admin.aoaerp.com/api/lowcode/normal/dify/app/table/record/page?pageNum=1&pageSize=100' \
  --header 'Authorization: Bearer <TOKEN>' \
  --header 'Content-Type: application/json' \
  --data-raw '{"appName":"SPU","tableName":"旅遊线路","record":{}}'
```

## 过滤条件在服务端不生效（关键）

实测 `record.compositeQueryFieldList` 中的条件会被服务端忽略：

| 传入条件 | 期望结果 | 实际结果 |
| --- | --- | --- |
| `线路代号 lt G1` | 空 | `total=68`（全量） |
| `路线代号 lt G1` | 空 | `total=68`（全量） |
| `路线代号 eq G1` | 仅 G1 的记录 | `total=68`（全量） |

因此本 Skill **一律拉取全量，在脚本内按 `路线代号` 过滤**，不在接口层做条件查询。若将来接口支持了服务端过滤，仍需保留客户端过滤以保证行为稳定。

## 响应

```json
{
  "data": {
    "rows": [
      {
        "id": "reczz28SSfQglSeW",
        "payloadFieldList": [
          {"name":"排序","value":[{"text":"1","type":"text"}]},
          {"name":"推荐指数","value":"★★★"},
          {"name":"景点名称","value":[{"text":"祁万顺","type":"text"}]},
          {"name":"点评","value":[{"text":"1925年老店，推荐：煎包、豆皮、鱼糊粉","type":"text"}]},
          {"name":"类型","value":"早餐"},
          {"name":"花费时间","value":"0.5h"},
          {"name":"起止片区","value":"汉阳-武昌"},
          {"name":"路线代号","value":[{"text":"G1","type":"text"}]},
          {"name":"路线名","value":[{"text":"龟蛇主线","type":"text"}]}
        ]
      }
    ],
    "total": 68,
    "pageToken": "cGFnZVRva2VuOjEw"
  },
  "traceId": "-"
}
```

### 字段类型差异（解析时必须注意）

| 字段 | `value` 形态 |
| --- | --- |
| `排序`、`景点名称`、`点评`、`路线代号`、`路线名` | 数组：`[{"text": "...", "type": "text"}]` |
| `图片1`、`图片2`、`图片3` | 数组：`[{"link": "https://...", "text": "https://...", "type": "url"}]`（`link` 与 `text` 同为图片 URL） |
| `推荐指数`、`类型`、`花费时间`、`起止片区` | 纯字符串 |

> **图片字段注意**：元素比文本字段多一个 `link` 键，`scripts/query_route.py` 的 `field_url()` 优先取 `link` 再回落 `text`，并只接受 `http(s)` 开头的取值。
>
> 实测：全表 68 条记录的「图片1/2/3」去重后仅 3 个 URL，且所有记录的三图组合**完全一致**（同一组占位图），并非按景点区分的真实配图。脚本会在 stderr 给出「图片字段提示：全部 N 条记录均为同一组占位图」的告警；解析真实数据前，可加 `--no-image` 关闭图片输出。当图片按景点补齐后，该告警会自动消失。

`scripts/query_route.py` 的 `field_text()` 已同时兼容两种形态。

### 其他注意事项

- **字段名是 `路线代号` / `路线名`**，不是「线路代号」/「线路名」。
- **`排序` 字段是行程内顺序的唯一依据**：脚本按该字段数值**递增**排列同一线路的景点。
  - 值非数字或缺失的记录排在有值记录之后，相对顺序沿用接口返回顺序；若该字段整体不可用，则退化为接口返回（录入）顺序。
  - 值相同时（异常数据）保持接口返回顺序，并在 stderr 列出「排序值重复 / 缺失」提示，便于排查脏数据。
  - 实测存在质量问题：G4 缺 5 号（不影响排序），G8 有两条记录的 `排序` 均为 `1`（宝通寺、粮道街）。
  - 需要旧行为时用 `--no-sort`。
- 全表 `total=68`，`pageSize=100` 一页可取完，无需翻页。

## 错误处理

脚本以非零退出码退出并输出原始响应体：

| 情况 | 输出 |
| --- | --- |
| HTTP 401 | `请求失败 HTTP 401: <响应体>`（Token 无效或过期） |
| HTTP 404 / 405 | `请求失败 HTTP 40x: <响应体>`（检查是否误加了 `/v1` 前缀） |
| HTTP 500 | `请求失败 HTTP 500: <响应体>` |
| 网络异常 | `请求失败: <reason>` |
| `rows` 为空 | `接口未返回数据: <原始响应前 500 字符>` |

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `WUHAN_ROUTE_API_TOKEN` | 见 `scripts/query_route.py` 内置默认值 | 覆盖接口 Token |
| `WUHAN_ROUTE_BASE_URL` | `https://admin.aoaerp.com` | 覆盖服务地址 |
| `WUHAN_ROUTE_APP` | `SPU` | 覆盖应用名 |
| `WUHAN_ROUTE_TABLE` | `旅遊线路` | 覆盖表名 |
