---
name: saig-intro
display_name: SAIG 数命SPU国际AI大赛介绍
display_name_en: SAIG International AI Competition Intro
description: 介绍SAIG 数命SPU国际AI大赛并回答与其相关的问题，涵盖大赛介绍、赛事时间安排、成绩公布时间与结果、SPU的定义等主题。通过调用SAIG大赛知识库 Dify 问答接口获取权威资料，query 为唯一变量。
description_zh: 介绍 SAIG 数命SPU国际AI大赛，覆盖大赛介绍、赛程时间、成绩公布、SPU 定义等，基于官方知识库作答。
description_en: Introduce the SAIG International AI Competition, covering overview, schedule, results, and SPU definition via the official knowledge base.
examples_zh:
- "介绍一下SAIG 数命SPU国际AI大赛"
- "SAIG大赛的报名和作品提交截止时间是什么时候"
- "比赛中 SPU 的含义是什么"
examples_en:
- "Introduce the SAIG International AI Competition"
- "When is the SAIG registration and submission deadline"
- "What does SPU mean in the competition"
version: 1.0.0
author: 武汉海辞科技有限公司
allowed-tools: Bash(python3)
---

<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->

# SAIG 数命SPU国际AI大赛介绍技能

## 目的

基于 SAIG 大赛知识库（Dify 应用）回答与 SAIG 数命SPU国际AI大赛相关的问题，用于生成大赛介绍文案、整理赛程时间线、核对成绩公布信息与 SPU 术语定义。所有事实内容必须来自知识库接口返回结果，不得凭记忆编造。

## 何时使用

用户提出与 SAIG 数命SPU国际AI大赛相关的查询时使用，典型场景：

- 大赛介绍：SAIG 是什么、大赛定位与背景、参赛对象、赛道与组别、举办形式
- 赛事时间安排：报名开始/截止时间、初赛复赛决赛时间点、作品提交窗口、关键里程碑
- 成绩公布：评审结果发布时间、成绩查询方式、晋级与获奖名单公示
- SPU 的定义：比赛中 SPU 的含义、与数命SPU（超级个体单元）的关系、参赛者如何以 SPU 身份参与
- 其他与赛事相关的问答与文案撰写需求

## 工作流程

档位协议以 `agents/jing-xiaowu.md` 的「回答档位」为准。本技能在 L0 快答默认调用知识库 **1 次**；L1+ 每次仅针对用户选定的方向追加 **1 次**。

1. 将用户原问题直接改写为一个明确的 `query`（中文，保留关键实体与限定词，如「介绍」「时间安排」「成绩公布」「SPU的定义」等）。不拆分 query、不按主题补问、不串联其他技能；介绍类需求（如「介绍一下SAIG大赛」）同样只调用 1 次。
2. 执行脚本获取答案：

   ```bash
   python3 ~/.codebuddy/skills/saig-intro/scripts/query_saig.py "介绍一下SAIG 数命SPU国际AI大赛"
   ```

   脚本位置相对于本 SKILL.md 为 `scripts/query_saig.py`。接口固定入参 `inputs = {"type": "saig"}`、`response_mode = "blocking"`，除 `query` 外不修改其他字段。

3. 基于返回的 `answer` 组织 L0 快答：一句话结论 + 不超过 5 条要点，只摘取本次 stdout 原文、不改写事实；忠实引用赛程日期、阶段名称与口径，标注来源为「SAIG大赛知识库」；接口未覆盖的内容明确说明，不要自行补充未经核实的信息。涉及时间信息时保持知识库返回的原始表述，不做推算或改写。
4. 快答末尾列出 2—3 个本技能的可深入方向，例如「赛事时间安排」「成绩公布与结果」「比赛中 SPU 的定义」，并提示用户回复编号或说「展开 XX」。给完方向即结束本轮，不自动继续调用。
5. 用户点选某一方向后，仅针对该方向追加 1 次调用，复用上一条命令 stderr 中的 `conversation_id`：

   ```bash
   SAIG_DIFY_CONVERSATION_ID=<上次的conversation_id> python3 scripts/query_saig.py "成绩什么时候公布"
   ```

   给出该方向的完整逐条内容，再给下一层方向；一次只展开一个方向，不把其余主题一次补齐。
6. 接口返回错误（HTTP 401/404/500 等）时，向用户说明调用失败并给出原始错误信息，不要改用自身记忆回答，不重试、不换技能再调。

## 资源

- `scripts/query_saig.py`：查询脚本，接受 `query` 位置参数，输出回答正文；元数据（conversation_id、token 用量、引用文档数）输出到 stderr。
- @references/api_reference.md：接口字段、响应结构、错误码与环境变量说明，需要排查调用问题或调整配置时查阅。
