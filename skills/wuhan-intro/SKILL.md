---
name: wuhan-intro
display_name: 武汉城市介绍
display_name_en: Wuhan City Intro
description: 介绍武汉城市情况并回答武汉相关问题，涵盖自然地理、地方人文、建置沿革、民族宗教、社会经济、城市建设、交通科教等主题。通过调用武汉知识库 Dify 问答接口获取权威资料，query 为唯一变量。
description_zh: 介绍武汉城市情况，覆盖自然地理、人文历史、社会经济、交通科教等，基于武汉地方志知识库作答。
description_en: Introduce the city of Wuhan, covering geography, culture, history, economy, transport and education via the Wuhan local gazetteer knowledge base.
examples_zh:
- "介绍一下武汉的自然地理和江河"
- "武汉的建置沿革是怎样的"
- "武汉城市圈一体化建设有哪些举措"
examples_en:
- "Introduce Wuhan's geography and rivers"
- "What is the administrative history of Wuhan"
- "What are the measures for Wuhan metropolitan area integration"
version: 1.0.0
author: 武汉海辞科技有限公司
allowed-tools: Bash(python3)
---

<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->

# 武汉城市介绍技能

## 目的

基于武汉地方志知识库（Dify 应用）回答关于武汉的问题，用于生成城市介绍、整理专题资料、核对地方志事实。所有内容必须来自知识库接口返回结果，不得凭记忆编造。

## 何时使用

用户提出与武汉相关的查询时使用，典型场景：

- 自然地理：地形地貌、江河水系、气候、自然资源、行政区划
- 建置沿革：历史建制变迁、行政区划演变、重大历史事件
- 地方人文：方言、民俗、饮食、名胜古迹、非物质文化遗产、名人
- 民族宗教：民族构成、宗教信仰、寺观教堂、宗教活动场所
- 社会经济与建设：人口、经济、交通、教育科研、武汉城市圈一体化

## 工作流程

档位协议以 `agents/jing-xiaowu.md` 的「回答档位」为准。本技能在 L0 快答默认调用知识库 **1 次**；L1+ 每次仅针对用户选定的方向追加 **1 次**。

1. 将用户原问题直接改写为一个明确的 `query`（中文，保留关键实体与限定词如时间、区域、领域）。不拆分 query、不按主题补问、不串联其他技能；问题过宽（如「介绍一下武汉」）时仍只调用 1 次，把其余专题留作可深入方向。
2. 执行脚本获取答案：
   ```bash
   python3 ~/.codebuddy/skills/wuhan-intro/scripts/query_wuhan.py "武汉城市圈一体化建设"
   ```
   脚本位置相对于本 SKILL.md 为 `scripts/query_wuhan.py`。接口固定入参 `inputs = {"type": "wuhan"}`、`response_mode = "blocking"`，除 `query` 外不修改其他字段。
3. 基于返回的 `answer` 组织 L0 快答：一句话结论 + 不超过 5 条要点，只摘取本次 stdout 原文、不改写事实；忠实引用事实与数据，标注来源为「武汉知识库（地方志）」；接口未覆盖的内容明确说明，不要自行补充未经核实的信息。
4. 快答末尾列出 2—3 个本技能的可深入方向，例如「自然地理与江河」「建置沿革」「地方人文与社会经济」，并提示用户回复编号或说「展开 XX」。给完方向即结束本轮，不自动继续调用。
5. 用户点选某一方向后，仅针对该方向追加 1 次调用，复用上一条命令 stderr 中的 `conversation_id`：
   ```bash
   WUHAN_DIFY_CONVERSATION_ID=<上次的conversation_id> python3 scripts/query_wuhan.py "其中交通一体化有哪些具体举措"
   ```
   给出该方向的完整逐条内容，再给下一层方向；一次只展开一个方向，不把其余主题一次补齐。
6. 接口返回错误（HTTP 401/404/500 等）时，向用户说明调用失败并给出原始错误信息，不要改用自身记忆回答，不重试、不换技能再调。

## 资源

- `scripts/query_wuhan.py`：查询脚本，接受 `query` 位置参数，输出回答正文；元数据（conversation_id、token 用量、引用文档数）输出到 stderr。
- @references/api_reference.md：接口字段、响应结构、错误码与环境变量说明，需要排查调用问题或调整配置时查阅。
