---
name: shuming-spu-intro
display_name: 数命SPU介绍
display_name_en: Shuming SPU Intro
description: 介绍数命SPU并回答与数命SPU相关的问题，涵盖SPU定义、超级个体的能力模型、内部SPU模式、社区功能与应用场景等主题。通过调用数命SPU知识库 Dify 问答接口获取权威资料，query 为唯一变量。
description_zh: 介绍数命SPU（超级个体单元），覆盖定义、能力模型、SPU 模式、社区功能与应用场景，基于官方知识库作答。
description_en: Introduce Shuming SPU (Super-individual Unit), covering definition, capability model, SPU modes, community features and use cases via the official knowledge base.
examples_zh:
- "数命SPU的定义是什么"
- "SPU具备哪些能力"
- "如何成为或运作一个SPU"
examples_en:
- "What is the definition of Shuming SPU"
- "What capabilities does an SPU have"
- "How to become or operate an SPU"
version: 1.0.0
author: 武汉海辞科技有限公司
allowed-tools: Bash(python3)
---

<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->

# 数命SPU介绍技能

## 目的

基于数命SPU知识库（Dify 应用）回答与数命SPU相关的问题，用于生成介绍文案、整理能力/模式清单、核对SPU术语与概念。所有事实内容必须来自知识库接口返回结果，不得凭记忆编造。

## 何时使用

用户提出与数命SPU相关的查询时使用，典型场景：

- SPU 定义：SPU 是什么、SPU 全称与含义（超级个体单元）、数命SPU的定位与理念
- 能力模型：SPU 具备的能力，如独立判断、AI 工具调用、任务组织、交付与责任承担
- SPU 模式：数命SPU内部的SPU模式分类、运作方式与协作机制
- 社区功能：技术问答、学习资源分享、项目协作、行业动态讨论、专家在线答疑
- 应用与路径：如何加入/成为SPU、SPU适用于哪些场景、对个人成长与职业发展的价值

## 工作流程

档位协议以 `agents/jing-xiaowu.md` 的「回答档位」为准。本技能在 L0 快答默认调用知识库 **1 次**；L1+ 每次仅针对用户选定的方向追加 **1 次**。

1. 将用户原问题直接改写为一个明确的 `query`（中文，保留关键实体与限定词，如「定义」「能力」「模式」「社区」等）。不拆分 query、不按主题补问、不串联其他技能；介绍类需求（如「介绍一下数命SPU」）同样只调用 1 次。
2. 执行脚本获取答案：
   ```bash
   python3 ~/.codebuddy/skills/shuming-spu-intro/scripts/query_spu.py "数命SPU的定义是什么"
   ```
   脚本位置相对于本 SKILL.md 为 `scripts/query_spu.py`。接口固定入参 `inputs = {"type": "spu"}`、`response_mode = "blocking"`，除 `query` 外不修改其他字段。
3. 基于返回的 `answer` 组织 L0 快答：一句话结论 + 不超过 5 条要点，只摘取本次 stdout 原文、不改写事实；忠实引用概念与表述，标注来源为「数命SPU知识库」；接口未覆盖的内容明确说明，不要自行补充未经核实的信息。
4. 快答末尾列出 2—3 个本技能的可深入方向，例如「SPU 能力模型」「内部 SPU 模式」「社区功能与应用场景」，并提示用户回复编号或说「展开 XX」。给完方向即结束本轮，不自动继续调用。
5. 用户点选某一方向后，仅针对该方向追加 1 次调用，复用上一条命令 stderr 中的 `conversation_id`：
   ```bash
   SPU_DIFY_CONVERSATION_ID=<上次的conversation_id> python3 scripts/query_spu.py "其中SPU模式具体有哪些"
   ```
   给出该方向的完整逐条内容，再给下一层方向；一次只展开一个方向，不把其余主题一次补齐。
6. 接口返回错误（HTTP 401/404/500 等）时，向用户说明调用失败并给出原始错误信息，不要改用自身记忆回答，不重试、不换技能再调。

## 资源

- `scripts/query_spu.py`：查询脚本，接受 `query` 位置参数，输出回答正文；元数据（conversation_id、token 用量、引用文档数）输出到 stderr。
- @references/api_reference.md：接口字段、响应结构、错误码与环境变量说明，需要排查调用问题或调整配置时查阅。
