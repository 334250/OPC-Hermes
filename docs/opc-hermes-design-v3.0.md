# OPC-Hermes 全自动化智能体管理系统 —— 架构设计白皮书 v3.0

> **项目代号**：OPC-Hermes（Orchestrated Professional Colleagues）
> **仓库地址**：<https://github.com/334250/OPC-Hermes.git>
> **核心理念**：在 Hermes Agent 运行时之上，构建一支具备角色分工、记忆隔离、自动进化能力的 AI 数字员工团队。
>
> 版本：v3.0
> 状态：Design Phase
> 作者：OPC-Hermes 架构组

---

## 目录

1. [项目定位与设计哲学](#1-项目定位与设计哲学)
2. [与 Hermes Agent 的关系](#2-与-hermes-agent-的关系)
3. [系统架构总览](#3-系统架构总览)
4. [Agent 角色体系](#4-agent-角色体系)
   - 4.1 分层设计 + 三类 Agent 角色（Leader / Worker / Skill）
   - 4.2 角色 Agent 统一模板
   - 4.3 角色 Agent 完整清单
5. [复杂度评级系统](#5-复杂度评级系统)
   - 5.1-5.4 评级 Skill 定义与成本分析
   - 5.5 模型控制：三层优先级（用户 > Leader > 自动路由）
6. [记忆架构](#6-记忆架构)
   - 6.1 门控记忆原则
   - 6.2 三层物理存储 + 内部门控
   - 6.3 运行时数据流
   - 6.4 核心数据结构（TaskProtocol / ProgressReport / SummaryBridge）
   - 6.5 记忆冲突解决
7. [质量评估系统](#7-质量评估系统)
8. [自进化引擎](#8-自进化引擎)
9. [多 Agent 协同编排](#9-多-agent-协同编排)
   - 9.1 五种协同模式（含 Star Delegation——本文档核心模式）
   - 9.2 具体工作流示例：文档制作全流程
   - 9.3 修订/反馈闭环
   - 9.4 Agent 间通信协议
   - 9.5 循环依赖检测
   - 9.6 DAG 编排器
   - 9.7 工作流故障处理（超时/质量异常/工具错误/并行隔离）
   - 9.8 中断与恢复（实时存档/恢复点/幂等）
   - 9.9 用户交互模式（计划确认/后台执行/进度通知/取消）
   - 9.10 产物管理（本地存储/版本关联/中间产物）
10. [共享基础设施](#10-共享基础设施)
11. [安全护栏](#11-安全护栏)
12. [实施路线图](#12-实施路线图)
13. [附录](#13-附录)

---

## 1. 项目定位与设计哲学

### 1.1 OPC-Hermes 是什么

OPC-Hermes 是一个**构建在 Hermes Agent 之上的多 Agent 管理层**。它不替换 Hermes Agent 的核心循环，而是通过注入角色定义、记忆隔离、复杂度路由、质量评估和自进化管道，将单个通用 Agent 升级为一支可编排、可评估、可进化的数字员工团队。

### 1.2 四个核心设计原则

| 原则 | 说明 |
|------|------|
| **不修改 Hermes Agent 源码** | 以插件、配置注入、外部编排的方式工作；Hermes Agent 升级时 OPC-Hermes 不受影响 |
| **记忆天生隔离** | 项目记忆、评估记忆、知识库三者物理/逻辑分离，评估 Agent 不污染执行 Agent 的上下文 |
| **复杂度即 Skill** | 复杂度判定不是每个 Agent 的内嵌逻辑，而是一个可复用、可独立进化的共享 Skill |
| **进化有据可查** | 每一次模型切换、工具替换、Prompt 变更都必须经过数据支撑的优化提案 → 人工审批 → 手动切换，全程版本化 |

### 1.3 与传统 Agent 框架的差异

```
传统框架:  "帮我画个架构图" → 单一 Agent → 单一模型 → 单一工具 → 输出
OPC-Hermes: "帮我画个架构图"
              → Leader Agent 解析意图，输出计划与用户确认
              → ComplexityRater 判定为 MEDIUM
              → 路由到画图 Agent（Gemini-Flash + draw.io）
              → Evaluator Agent 评分
              → 指标写入 Eval Memory
              → Optimizer 周期性扫描 → 发现优化机会 → 生成提案 → 人工审批 → 手动切换
```

---

## 2. 与 Hermes Agent 的关系

### 2.1 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                      OPC-Hermes（管理层）                      │
│                                                              │
│  Leader Agent  │  ComplexityRater  │  Memory Layer           │
│  (任务调度中枢)  │  (复杂度评级)      │  (门控记忆)              │
│                                                              │
│  Evaluator     │  Optimizer        │  Knowledge Base         │
│  (质量评估)     │  (自动优化)        │  (用户上传 + 爬虫)       │
│                                                              │
│  Agent List     │  Proposal Engine  │  手动切换管理          │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│                 Python import（不改源码）                       │
├──────────────────────────────────────────────────────────────┤
│                    Hermes Agent（运行时）                       │
│                                                              │
│  AIAgent        │  Tool Registry    │  Gateway (22 平台)      │
│  (核心循环)      │  (70+ 工具)       │  (Telegram/Discord/...) │
│                                                              │
│  Session Store  │  Cron Scheduler   │  Plugin System          │
│  (SQLite+FTS5)  │  (定时任务)        │  (扩展点)               │
│                                                              │
│  Provider        │  Prompt Builder   │  Batch Runner          │
│  Resolution      │  (Prompt 构建)    │  (轨迹生成)             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 七个集成点

| # | OPC-Hermes 需求 | 如何在 Hermes Agent 上实现 | 侵入性 |
|---|----------------|--------------------------|--------|
| 1 | **角色 Agent** | 每个角色 = 不同的 system prompt + toolset 组合。角色定义通过 `AGENTS.md`、`.hermes/context/` 或 Leader 动态构建注入；工具范围通过 Plugin 运行时追加的 TOOLSETS 条目限定 | 不修改源码（Plugin + 配置驱动） |
| 2 | **复杂度判定** | 实现为 Hermes Agent 的一个 Tool/Skill，Leader Agent 在路由前调用；使用最便宜模型执行判定 | 不修改源码（通过 Plugin register_tool 注册） |
| 3 | **记忆操作** | `save_context`、`get_summary` 等记忆 API 通过 Plugin 的 `register_tool()` 注册。Worker 通过 prompt 引导在适当时机调用。Memory Layer 作为独立 Python 模块被工具函数 import | 不修改源码（通过 Plugin register_tool 注册新工具） |
| 4 | **质量评估** | Evaluator Agent 是一个普通 Hermes Agent 实例，配置只读权限 + 独立 session，不写入项目记忆 | 不修改源码（标准 Agent 实例） |
| 5 | **自动优化** | 通过 Cron 的 `create_job()` API 注册定时任务；生成优化提案推送到 WebUI Dashboard 供用户人工审批 | 不修改源码（复用 cron create_job API） |
| 6 | **Agent 间通信** | Leader 复用 Hermes Agent 已有的 `delegate_tool`（`tools/delegate_tool.py`）派发 Worker——每个 Worker 在 `ThreadPoolExecutor` 线程中作为子 Agent 实例运行（同进程）。`delegate_tool` 原生支持：并行 batch 模式、可配置超时（默认 600s）、心跳监控、`DelegateEvent` 进度事件流。OPC 在此之上封装 `OPCWorkerDispatcher`，负责记忆注入（通过 context 参数传入 Summary Bridge 摘要）和结果收集 | 不修改源码（复用 delegate_tool + Plugin 封装 ~150 行） |
| 7 | **部署附加组件** | OPC-Hermes 新增以下独立组件，通过 Plugin 系统挂载：`memory_layer/`（SQLite 独立文件）、`agent_list/`（JSON/YAML 注册表）、`artifact_store/`（本地目录）、`model_prefs/`（用户模型偏好配置） | 新增文件（通过 pip 包或 ~/.hermes/plugins/ 安装，非侵入） |

### 2.3 命名约定

| 名称 | 指代 |
|------|------|
| **Hermes Agent** | Nous Research 开源的底层 Agent 运行时 |
| **OPC-Hermes** | 本项目——构建在 Hermes Agent 之上的多 Agent 管理层 |
| **Leader Agent** | OPC-Hermes 的任务调度中枢——接收用户请求、拆解子任务、分发 Worker、汇总结果；等同于传统意义上的 Orchestrator |
| **Worker Agent / 角色 Agent** | OPC-Hermes 管理的带角色分工的执行 Agent 实例 |

---

## 3. 系统架构总览

### 3.1 全景图

```
                            用户请求
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        Hermes Agent Gateway                              │
│                        (消息平台接入层)                                    │
│                    Telegram / Discord / 微信 / ...                        │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ 路由到 Leader Agent
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     Leader Agent（调度中枢 = Orchestrator）                │
│                                                                          │
│  ┌────────────┐   ┌────────────────┐   ┌──────────────────────────┐     │
│  │ 意图解析    │──▶│ ComplexityRater│──▶│ Worker 发现 & 匹配        │     │
│  │ (LLM 推理) │   │ (共享 Skill)   │   │ (查询 Agent List)         │     │
│  └────────────┘   └────────────────┘   └────────────┬─────────────┘     │
│                                                     │                   │
│                          ┌──────────────────────────┼──────────┐        │
│                          │  计划生成 → 用户确认 → 执行调度           │        │
│                          │  · DAG 拆解 & 循环检测         │        │
│                          │  · 缺失 Agent 自动生成 & 注册   │        │
│                          │  · 记忆门控规则定义             │        │
│                          │  · 进度汇报 & 修订分发          │        │
│                          └──────────────────────────┼──────────┘        │
└─────────────────────────────────────────────────────┼────────────────────┘
                                                      │
        ┌─────────────────────────────────────────────┼──────────────┐
        │               Worker Agent 层                │              │
        │                                             │              │
        │  ┌──────────┐ ┌──────────┐ ┌──────────┐    │              │
        │  │ 调研Worker│ │ 书写Worker│ │ 绘图Worker│    │              │
        │  │          │ │          │ │          │    │              │
        │  │ skills:  │ │ skills:  │ │ skills:  │    │              │
        │  │ · 网页搜索│ │ · 章节撰写│ │ · 流程图  │    │              │
        │  │ · 论文检索│ │ · 风格调整│ │ · 数据图  │    │              │
        │  └──────────┘ └──────────┘ └──────────┘    │              │
        │                                             │              │
        │  ┌──────────┐ ┌──────────┐ ┌──────────┐    │              │
        │  │ 排版Worker│ │ 审稿Worker│ │  ...     │    │              │
        │  │          │ │          │ │          │    │              │
        │  │ skills:  │ │ skills:  │ │          │    │              │
        │  │ · 格式排版│ │ · 语法检查│ │          │    │              │
        │  └──────────┘ └──────────┘ └──────────┘    │              │
        └─────────────────────────────────────────────┘              │
                                                      │
        ┌─────────────────────────────────────────────┼──────────────┐
        │                 旁系系统                     │              │
        │                                             │              │
        │  ┌──────────────────┐  ┌──────────────────┐ │              │
        │  │ Evaluator Agent  │  │ Optimizer        │ │              │
        │  │ (质量评估)        │  │ (自动优化引擎)    │ │              │
        │  │ · 输入输出评分    │  │ · 指标扫描       │ │              │
        │  │ · 知识仲裁       │  │ · 提案生成       │ │              │
        │  │ · Leader 拆解评估 │  │ · 手动切换管理   │ │              │
        │  │ · 仅在 Eval Mem  │  │ · 版本回滚       │ │              │
        │  │   中读写         │  │                  │ │              │
        │  └──────────────────┘  └──────────────────┘ │              │
        └─────────────────────────────────────────────┘              │
                                                      │
        ┌─────────────────────────────────────────────┼──────────────┐
        │                 共享存储                     │              │
        │                                             │              │
        │  ┌────────────┐ ┌────────────┐ ┌──────────┐│              │
        │  │ Agent List │ │ Memory     │ │ Artifact ││              │
        │  │ (Agent注册表)│ │ Layer     │ │ Store    ││              │
        │  │            │ │ (门控记忆)  │ │ (产物存储)││              │
        │  └────────────┘ └────────────┘ └──────────┘│              │
        └─────────────────────────────────────────────┘
```

### 3.2 请求生命周期

```
用户在 Telegram 发送: "帮我做一份 Q2 销售分析 PPT"

0. Gateway 路由:
   → 识别用户 → 加载用户配置 → 选择/创建 Leader Agent 实例

1. Leader Agent 意图解析 (LLM 推理):
   → 识别: 这是一个复合任务
   → 查询 Agent List: 需要的 Worker = [数据分析, 画图, PPT制作]
   → 数据分析和画图在 List 中匹配成功 ✅
   → PPT制作匹配失败 ❌ → Leader 自动生成一个 PPT 制作 Worker → 注册到 Agent List

2. Leader 输出计划 → 用户确认:
   ┌────────────────────────────────────────────┐
   │ 📋 任务计划: Q2 销售分析 PPT               │
   │                                            │
   │ 协同模式: Pipeline                          │
   │                                            │
   │ Step 1: 数据分析Worker (MEDIUM)             │
   │   模型: claude-sonnet-4                     │
   │   Skills: [pandas分析, scipy统计]           │
   │   输出: 销售趋势数据 + 洞察                  │
   │                                            │
   │ Step 2: 画图Worker (SIMPLE)                 │
   │   模型: minicpmv4.6                         │
   │   Skills: [echarts图表]                     │
   │   输出: 3张图表                              │
   │                                            │
   │ Step 3: PPT制作Worker (MEDIUM) 🆕 新生成    │
   │   模型: claude-sonnet-4                     │
   │   Skills: [python-pptx]                     │
   │   输出: .pptx 文件                          │
   │                                            │
   │ 记忆规则:                                    │
   │   画图Worker ← 从数据分析Worker 获取数据摘要  │
   │   PPT Worker ← 从 前两个Worker 获取全部输出  │
   │                                            │
   │ [确认执行] [修改计划] [取消]                  │
   └────────────────────────────────────────────┘

3. 用户点击 "确认执行" → Leader 按 DAG 调度:
   Step 1: 数据分析Worker 执行 → 输出: 数据+洞察
           实时记忆存档 → 标记恢复点 ✓
   Step 2: 画图Worker 执行 → 输出: 3张图表
           实时记忆存档 → 标记恢复点 ✓
   Step 3: PPT制作Worker 执行 → 输出: .pptx
           实时记忆存档 → 标记恢复点 ✓

4. Evaluator Agent 评分（全程旁系监听）:
   → 对每个 Worker 的输入/输出质量打分
   → 对 Leader 的拆解质量评分
   → 写入 Eval Memory（不污染 Project Memory）

5. Leader 汇总结果 → 交付用户

6. 用户打分:
   → 对最终产物评分 (1-5星)
   → 对各 Worker 表现反馈
   → 反馈写入 Eval Memory → Optimizer 定期扫描 → 优化 Agent List
```

---

## 4. Agent 角色体系

### 4.1 Agent 角色三层模型

OPC-Hermes 区分三种 Agent 角色，Leader Agent 即为调度中枢（同义于 Orchestrator）：

| 角色类型 | 职责 | 记忆关系 | 生命周期 |
|---------|------|---------|---------|
| **Leader Agent**（调度中枢） | 接收用户任务，LLM 推理拆解子任务，匹配/生成 Worker，输出计划与用户确认，调度执行，收集进度，汇总输出，处理修订 | 与 Worker **不共享记忆**。仅通过 TaskProtocol + ProgressReport 了解全局 | 用户发起任务时创建/复用，任务完成后归档 |
| **Worker Agent**（执行者） | 接受 Leader 的 TaskProtocol，调用自身 skills 完成子任务，返回结果 | 与其 skills 共享记忆；与其他 Worker 的记忆共享规则由 Leader 在计划中**按需定义**（非硬编码） | 子任务创建，完成后释放；多工作流并发时为独立实例 |
| **Skill**（技能） | Worker 的具体能力单元 | 寄生于调用它的 Worker 的记忆空间 | 无状态，每次调用即销毁 |

### 4.1.1 Leader Agent 详细设计

**① 来源**：系统提供默认 Leader Agent（满足基本调度功能），用户可自定义修改。用户通过 Hermes Agent 的模型选择来指定 Leader 使用的 LLM。Leader 使用 LLM 进行推理（拆解任务、匹配 Worker、分析修订意见）。

**② Worker 发现机制：Agent List**

```
Agent List（全局注册表，文件系统或 DB 存储）:

┌──────────────────────────────────────────────────────────────────┐
│ Agent List                                                       │
├────────────┬────────────┬────────────────┬────────┬──────────────┤
│ ID         │ 类型       │ 能力描述        │ 质量分  │ 版本         │
├────────────┼────────────┼────────────────┼────────┼──────────────┤
│ research   │ Worker     │ 调研、信息搜集   │ 4.2★   │ v2.1.0       │
│ writing    │ Worker     │ 文档撰写        │ 4.5★   │ v1.3.0       │
│ diagram    │ Worker     │ 流程图、架构图   │ 4.0★   │ v2.3.1       │
│ format     │ Worker     │ 排版、格式处理   │ 3.8★   │ v1.0.0       │
│ review     │ Worker     │ 审稿、质量审查   │ 4.1★   │ v1.1.0       │
│ ...        │ ...       │ ...            │ ...    │ ...          │
├────────────┴────────────┴────────────────┴────────┴──────────────┤
│ Skills List（全局技能注册表）                                      │
├────────────┬────────────┬────────────────┬────────┬──────────────┤
│ web_search │ Skill      │ 网页搜索        │ 4.3★   │ v1.2.0       │
│ paper_fetch│ Skill      │ 论文检索        │ 3.9★   │ v1.0.0       │
│ chapter_w  │ Skill      │ 章节撰写        │ 4.6★   │ v2.0.0       │
│ grammar_ck │ Skill      │ 语法检查        │ 4.4★   │ v1.5.0       │
│ ...        │ ...       │ ...            │ ...    │ ...          │
└────────────┴────────────┴────────────────┴────────┴──────────────┘
```

**③ 匹配流程**：Leader 拆解任务 → 确定所需 Worker 类型 → 在 Agent List 中搜索匹配

```
Leader 拆解结果: 需要 [调研Worker, 书写Worker, 审稿Worker]
                      │            │            │
                      ▼            ▼            ▼
Agent List 搜索:    research ✅   writing ✅   review ❓
                                               │
                                    找到 "review" Worker的描述:
                                    "审稿、质量审查..."
                                               │
                                    Leader LLM 分析:
                                    "审稿Worker" 与需求 "审核Agent"
                                    匹配度 92% → ✅ 直接使用
                                               │
                                    假设匹配失败 (无合适Worker):
                                               │
                                    Leader 自动生成新 Worker:
                                    · 基于默认模板 + 需求描述
                                    · 生成 system_prompt + skills 绑定
                                    · 注册到 Agent List
                                    · 标记 🆕 (待用户确认)
```

**④ 自动生成与 List 更新**：

- 当 Agent List 中缺少满足需求的 Worker 时，Leader 基于需求描述和默认模板自动生成**草案**。

**重要限制**：自动生成仅生成 system prompt（角色定义、能力描述、复杂度判定参数、模型路由偏好），**不生成新工具**。Worker 只能绑定 Agent List 中已有 Skills List 的工具。如果所需工具不在 Skills List 中，Leader 会标记 `missing_tools: [...]` 并在计划中提示用户手动注册。

- 新生成的 Worker 草案**不会立即投入使用**。Leader 在计划确认阶段向用户展示草案：

```
Leader 判断缺少 Worker → 自动生成草案 → 计划确认时展示:
┌────────────────────────────────────────────────────────────┐
│ 🆕 检测到需要 [PPT制作Worker]，已自动生成草案:               │
│                                                            │
│   角色: PPT制作                                             │
│   模型: claude-sonnet-4                                     │
│   Skills: [python-pptx]                                    │
│   System Prompt: (点击展开)                                 │
│     "你是一位专业PPT设计师，根据用户需求生成高质量演示文稿..."  │
│                                                            │
│   [确认使用] [修改配置] [取消(手动创建)]                      │
└────────────────────────────────────────────────────────────┘
```

- 用户确认后 → 注册到 Agent List（标记 version: 0.1.0-draft, status: staging），开始执行
- 用户修改后 → 更新草案，再次预览 → 确认后注册
- 用户取消 → Leader 提示用户手动创建或调整任务范围
- 任务完成后 → 用户评分:
  - 质量分达标（≥ 3.0★）→ status 升级为 production
  - 质量分不达标 → status 改为 deprecated，从活跃 Agent List 中移除
- 用户始终可对已注册的 Worker 进行后续修改（调整 prompt、增减 skills 绑定）

**⑤ 任务完成后的优化更新**：

```
任务完成 → 用户打分 (1-5★, 可选详细反馈)
              │
              ├── 对最终产物评分 → 更新 Leader 的质量分
              ├── 对各 Worker 评分 → 更新各 Worker 在 Agent List 中的质量分
              └── 对 Skills 间接评分 → 更新 Skills List 中的质量分
              │
              ▼
         Optimizer 定期扫描:
         · 质量分持续上升的 Worker/Skill → 提升为默认推荐
         · 质量分持续下降的 → 标记 deprecated，减少匹配优先级
         · 用户自定义的 Worker 质量超过默认 → 替换默认
```

**⑥ Worker 间记忆规则——可配置，非硬编码**：

Leader 在输出计划时，同时定义各 Worker 之间的记忆共享规则。规则由 Leader 推理决定 + 用户可调整：

```
示例 1（文档制作场景）:
  画图Worker ← 获取 书写Worker 的摘要（需了解正文内容才能画图）
  审稿Worker ← 不获取任何 Worker 的记忆（只看最终产物做输入输出评审）

示例 2（竞品分析场景）:
  竞品Worker_A ←→ 竞品Worker_B: 全文共享（需要交叉验证数据）
  汇总Worker   ←  获取 A、B 的摘要（只需结论，不需要原始爬虫数据）
```

### 4.1.2 循环依赖防止规则

1. Worker 之间不直接通信——必须通过 Summary Bridge 和 Leader
2. 跨 Worker 委托经 Leader 检查调用栈，同一 Agent 出现 2 次 → 终止并返回已有结果
3. 每个任务维护 `call_stack: List[worker_id]`，路由前做去重检查

### 4.2 角色 Agent 统一模板

每个 Worker Agent 是 Hermes Agent 的一个具体配置实例，由以下要素定义：

```yaml
agent:
  id: "diagram_agent"
  display_name: "画图 Agent"
  domain: "creative"               # 所属领域（用于分类和发现）
  role: "专业图表设计师"

  # 一、system prompt（注入到 Hermes Agent 的 prompt_builder）
  system_prompt: |
    你是一位专业图表设计师。根据用户需求生成高质量图表。
    你的能力范围包括: 流程图、架构图、时序图、ER图、数据图表、思维导图。
    你不能做的: 视频制作、3D建模、UI高保真原型（→ 交给视觉设计Agent）。

    在执行任务前，先判断复杂度级别，然后选择合适的工具:
    - 简单图表: 使用 Mermaid 文本生成
    - 中等复杂度: 使用 draw.io Python 库
    - 复杂架构图: 使用 PlantUML

  # 二、复杂度判定参数（供 ComplexityRater 使用）
  complexity_criteria:
    SIMPLE:
      conditions:
        - "图元数量 <= 10"
        - "关系/连接 <= 5"
        - "无嵌套/多层结构"
      example: "画一个简单的登录流程图"
    MEDIUM:
      conditions:
        - "图元数量 10~30"
        - "有分组/层次结构"
        - "需要配色/风格指定"
      example: "画一个微服务架构图，5个服务+API网关"
    COMPLEX:
      conditions:
        - "图元数量 > 30"
        - "多子系统/多层级"
      example: "画完整企业级系统架构图"

  # 三、模型路由表（按复杂度级别）
  model_routing:
    SIMPLE:
      primary: {model: "minicpmv4.6", max_cost: 0.0005}
      fallback: [{model: "gemini-2.5-flash", max_cost: 0.001}]
    MEDIUM:
      primary: {model: "gemini-2.5-flash", max_cost: 0.005}
      fallback: [{model: "claude-sonnet-4", max_cost: 0.01}]
    COMPLEX:
      primary: {model: "claude-sonnet-4", max_cost: 0.05}
      fallback: [{model: "gpt-4o", max_cost: 0.05}]

  # 四、工具链（三级降级）
  tool_chain:
    flowchart:
      tier_1: {tool: "draw.io_python", desc: "高质量矢量图"}
      tier_2: {tool: "mermaid_cli", desc: "文本生成图表"}
      tier_3: {tool: "text_description", desc: "纯文本描述"}
    data_chart:
      tier_1: {tool: "echarts_python", desc: "交互式图表"}
      tier_2: {tool: "matplotlib", desc: "静态图表"}
    creative_image:
      tier_1: {tool: "stable-diffusion-xl", desc: "高质量生成"}
      tier_2: {tool: "dalle-3", desc: "备选生成"}

  # 五、toolset（映射到 Hermes Agent toolsets.py）
  toolset: "diagram_toolset"

  # 六、可委托的子任务（声明式，供 Leader Agent 使用）
  can_delegate_to:
    - {agent: "visual_design_agent", for: ["高保真UI原型", "Logo设计"]}

  # 七、学习管道配置
  learning:
    knowledge_sources:
      - source: "zhihu"
        topics: ["图表设计", "数据可视化", "流程图"]
        priority: "high"
      - source: "github"
        topics: ["diagram", "mermaid", "drawio", "chart"]
        priority: "medium"
    focus_areas:
      - "新绘图工具/库的出现"
      - "模型在图表生成上的能力对比"
```

### 4.3 角色 Agent 完整清单

| 领域 | Worker Agent | 核心能力 | 主要模型 | 关键工具 |
|------|-------------|---------|---------|---------|
| **技术** | 代码书写 | 全栈开发、Bug修复、重构、测试生成 | claude-sonnet-4 / deepseek-v3 | docker_sandbox, git, linter |
| **技术** | 技术文档 | API文档、README、变更日志 | claude-sonnet-4 | sphinx, mkdocs |
| **创意** | 画图 | 流程图/架构图/数据图/创意图像 | 按复杂度路由 | draw.io, mermaid, echarts, SDXL |
| **创意** | PPT制作 | 从大纲/文档生成PPT | claude-sonnet-4 / gpt-4o | python-pptx, Google Slides API |
| **创意** | 视觉设计 | 图片编辑/海报/UI原型/Logo | gemini-2.5-flash / SDXL | pillow, rembg, figma API |
| **文档** | Word文档 | 技术/商业/学术/行政文档 | claude-sonnet-4 / gpt-4o | python-docx, pandoc |
| **文档** | 文案写作 | 社交媒体/广告/品牌/SEO | gpt-4o-mini / claude-sonnet-4 | semrush_api, custom_rules |
| **文档** | 翻译 | 50+语言对，领域自适应 | gpt-4o-mini / gpt-4o | custom_glossary_db, comet_metric |
| **业务** | 产品经理 | 需求分析/PRD/竞品/路线图 | claude-sonnet-4 / gpt-4o | web_search, rice_calculator |
| **业务** | 数据分析 | 采集→清洗→分析→可视化 | claude-sonnet-4 / gpt-4o | pandas, scipy, duckdb |
| **自动化** | 浏览器 | 表单填写/抓取/工作流 | minicpmv4.6 / gpt-4o-mini | playwright, playwright_stealth |
| **自动化** | 邮件 | 收发/分类/回复/附件 | gpt-4o-mini / claude-sonnet-4 | imap+smtp, Graph API |

---

## 5. 复杂度评级系统

### 5.1 设计原则

复杂度评级不嵌入每个 Agent，而是作为一个**共享 Skill**：

```
用户任务 → Leader Agent
              │
              ▼
     ┌─────────────────────┐
     │  ComplexityRater     │  ← 共享 Skill
     │  (轻量模型执行)       │
     │                     │
     │  输入:               │
     │   · 用户原始任务     │
     │   · Agent criteria  │
     │                     │
     │  输出:               │
     │   · level: 枚举值    │
     │   · confidence: 0-1 │
     │   · reasoning: 理由 │
     └─────────┬───────────┘
               │
               ▼
     Leader Agent 用 level 查 Agent 的 model_routing 表
```

### 5.2 评级 Skill 定义

```python
class ComplexityRater:
    """
    共享复杂度评级 Skill。
    所有 Agent 共用此实例，通过 agent_id 区分判定标准。
    """

    def __init__(self, model: str = "minicpmv4.6"):
        self.model = model           # 判定模型（最便宜的即可）
        self.cache: Dict[str, ComplexityRating] = {}  # 相似任务缓存

    def rate(
        self,
        task: str,
        agent_id: str,
        agent_criteria: dict
    ) -> ComplexityRating:
        """
        task: 用户原始输入
        agent_id: 目标 Agent ID
        agent_criteria: 该 Agent 的复杂度判定标准

        返回:
          ComplexityRating(level, confidence, reasoning)
        """

        # Step 1: 缓存查询（语义相似度）
        cache_key = self._hash(task, agent_id)
        if cached := self.cache.get(cache_key):
            return cached

        # Step 2: LLM 判定
        prompt = f"""
        你是一个复杂度评级器。根据以下标准，判断任务属于哪个级别。

        Agent: {agent_id}
        任务: {task}

        判定标准:
        {agent_criteria}

        输出 JSON:
        {{"level": "SIMPLE"|"MEDIUM"|"COMPLEX", "confidence": 0.0-1.0, "reasoning": "..."}}
        """

        result = self._call_llm(prompt)

        # Step 3: 缓存写入 + 返回
        self.cache[cache_key] = result
        return result
```

### 5.3 判定成本分析

| 判定模型 | 单次成本 | 延迟 |
|----------|---------|------|
| minicpmv4.6 | ~$0.00001 | ~300ms |
| gpt-4o-mini | ~$0.00005 | ~500ms |

**成本悖论解决方案**：
- SIMPLE 任务占比按 70% 估算，每次判定成本 $0.00001
- 判定后 SIMPLE 任务用小模型（$0.0005）而非大模型（$0.015）
- 节省: 70% × ($0.015 - $0.0005) - $0.00001 = **$0.01014/task**
- **净收益为判定成本的 1000 倍+**

### 5.4 判定准确率追踪

```python
class ComplexityAccuracyTracker:
    """
    追踪判定准确率，反向优化判定标准
    """

    def record(self, rating: ComplexityRating, actual_result: ExecutionResult):
        """
        rating: 判定时的级别
        actual: 实际执行结果
        """
        # 如果判定 SIMPLE 但实际执行中触发了 fallback → 低估
        # 如果判定 COMPLEX 但小模型就完成了 → 高估
        discrepancy = self._compare(rating, actual_result)
        self.metrics[rating.agent_id].append(discrepancy)

        # 定期分析 → 生成 criteria 优化建议 → 提交 Optimizer
```

### 5.5 模型控制：三层优先级

模型选择并非完全自动，也非完全手动，而是采用**三层优先级**：

```
┌──────────────────────────────────────────────────────────────────┐
│                    模型选择优先级（从高到低）                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  第 1 层: 用户配置（最高优先级）                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 用户在系统配置中设定的模型偏好，覆盖一切自动路由：             │  │
│  │                                                            │  │
│  │ 全局偏好:                                                   │  │
│  │   preferred_provider: "anthropic"   # 优先 Claude 系列      │  │
│  │   max_cost_per_call: 0.02           # 单次调用成本上限      │  │
│  │   quality_floor: 0.85               # 自动路由最低质量要求   │  │
│  │                                                            │  │
│  │ 按 Agent 级别覆盖:                                          │  │
│  │   code_agent:                                               │  │
│  │     model: "claude-sonnet-4"        # 代码始终用 Sonnet     │  │
│  │   diagram_agent:                                             │  │
│  │     SIMPLE: "minicpmv4.6"           # 简单图用轻量模型      │  │
│  │     MEDIUM: "gemini-2.5-flash"                               │  │
│  │                                                            │  │
│  │ 按 Skill 级别覆盖:                                          │  │
│  │   skill(web_search):                                        │  │
│  │     model: "gpt-4o-mini"            # 搜索始终用一个模型     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              ↓ 用户未配置时                      │
│  第 2 层: Leader 推荐（中等优先级）                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Leader Agent 在生成计划时根据任务特征推荐模型组合：            │  │
│  │                                                            │  │
│  │ 推荐逻辑（LLM 推理）:                                        │  │
│  │   · 任务紧急? → 偏好低延迟模型                               │  │
│  │   · 任务涉及敏感数据? → 偏好本地模型                          │  │
│  │   · 参考历史评分: 类似任务上次用 X 模型得分高 → 推荐 X       │  │
│  │   · 参考用户全局偏好: 用户偏好 Claude → 优先推荐 Claude 系列  │  │
│  │                                                            │  │
│  │ 推荐结果在计划确认阶段展示，用户可一键修改：                   │  │
│  │   "Leader 建议: 调研用 mini → 你是对的"                       │  │
│  │   "Leader 建议: 书写用 Sonnet → 不，改用 GPT-4o"              │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              ↓ 未推荐时                         │
│  第 3 层: 复杂度自动路由（兜底）                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ complexity_criteria 中定义的 model_routing 表：              │  │
│  │   SIMPLE  → primary + fallback                              │  │
│  │   MEDIUM  → primary + fallback                              │  │
│  │   COMPLEX → primary + fallback                              │  │
│  │ 完全自动，无需用户介入                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**模型切换发生时**：
- 切换记录写入 Eval Memory（原模型、新模型、触发层级、原因）
- Optimizer 周期性分析切换模式 → 如果某个用户总是覆盖某类推荐 → 自动更新其偏好配置
- 切换不影响工作流中其他 Worker——各 Worker 的模型选择独立

### 5.6 模型能力兼容性校验

三层优先级确定了候选模型后，在执行前增加**能力兼容性检查层**——防止选出的模型不具备任务所需的基础能力（如视觉、工具调用、长上下文）。

```python
class CapabilityChecker:
    """
    模型能力矩阵 —— 在模型选择流程的最后一步执行。
    检查候选模型是否具备任务所需的能力，不兼容时自动降级或提示用户。
    """

    CAPABILITY_MATRIX = {
        "gpt-4o":           {"vision": True,  "tool_calling": True,  "ctx_len": 128000},
        "gpt-4o-mini":      {"vision": True,  "tool_calling": True,  "ctx_len": 128000},
        "claude-sonnet-4":  {"vision": True,  "tool_calling": True,  "ctx_len": 200000},
        "gemini-2.5-flash": {"vision": True,  "tool_calling": True,  "ctx_len": 1048576},
        "deepseek-v3":      {"vision": False, "tool_calling": True,  "ctx_len": 65536},
        "minicpmv4.6":      {"vision": True,  "tool_calling": False, "ctx_len": 8192},
    }

    def validate(self, candidate_model: str, required: set, task_ctx: dict) -> bool:
        """检查候选模型是否具备所有必需能力"""
        caps = self.CAPABILITY_MATRIX.get(candidate_model)
        if not caps:
            return False  # 未知模型，保守拒绝

        if "vision" in required and not caps["vision"]:
            return False
        if "tool_calling" in required and not caps["tool_calling"]:
            return False
        if caps["ctx_len"] < task_ctx.get("estimated_tokens", 0):
            return False
        return True

    def find_alternative(self, required: set, task_ctx: dict,
                         preferred_provider: str = None) -> Optional[str]:
        """在模型列表中寻找具备所需能力的最优替代"""
        candidates = []
        for model, caps in self.CAPABILITY_MATRIX.items():
            if self.validate(model, required, task_ctx):
                score = self._score(model, caps, preferred_provider, task_ctx)
                candidates.append((score, model))
        return max(candidates)[1] if candidates else None
```

**校验流程**：

```
模型选择流程（完整版，含能力校验）:
  用户偏好/Leader推荐/自动路由 → 得出候选模型
      │
      ▼
  CapabilityChecker.validate(候选模型, required_caps)
      │
      ├── ✅ 通过 → 使用候选模型
      └── ❌ 失败 →
            ├── 自动在模型列表中查找具备所需能力的替代模型（同 provider 优先）
            ├── 找到替代 → 切换 + 通知用户:
            │     "模型 minicpmv4.6 不支持 tool_calling，已自动切换到 gpt-4o-mini"
            └── 找不到 → 提示用户:
                  "当前模型列表中没有同时满足 [vision, tool_calling] 的模型，
                   请在 Skills List 中添加支持这些能力的模型"
```

**能力矩阵的维护**：
- `CAPABILITY_MATRIX` 作为配置文件存储在 `opc_hermes/config/capability_matrix.yaml`，支持用户扩展
- 当用户添加新模型到 Hermes Agent 时，系统提示同时填写能力声明
- Optimizer 可根据实际执行结果反向校验能力声明（如声明了 vision 但调用时返回不支持错误 → 标记异常）

---

## 6. 记忆架构

### 6.1 设计原则：可配置门控记忆

OPC-Hermes 的记忆管理核心思想是**门控（Gated Memory）**——不是所有 Agent 都能看到彼此的记忆。

**关键原则：记忆共享规则不硬编码——由 Leader Agent 在每个工作流的计划阶段按需定义，用户可调整。**

**运行时注入机制**：
- **Leader 进程**：Leader 不是独立进程——它就是 Gateway Agent 本身。通过 `pre_gateway_dispatch` hook 注入 Leader 行为 prompt，使同一个 Agent 实例获得调度能力。Leader 通过 Hermes Agent 原生的 `delegate_task` 工具派发 Worker。
- **Worker 进程**：每个 Worker 通过 `delegate_tool` 在 `ThreadPoolExecutor` 线程中运行（同进程、独立 conversation）。Worker 的 context 参数包含角色 system prompt + 上游 Summary Bridge 摘要。记忆操作（`opc_save_context`、`opc_write_to_bridge` 等）注册为 Worker 可用的工具，通过 prompt 引导 Worker 在适当时机调用。
- **Evaluator 进程**：独立的 Agent 实例（可通过 `on_session_end` hook 触发，或作为 cron 异步执行），只读 Project Memory，写入 Eval Memory。

系统提供以下默认规则，Leader 可根据任务需要覆盖：

```
默认记忆门控规则（Leader 可在计划中覆盖）：
┌────────────────────────┬──────────────────────────────────────────────────┐
│ 关系                   │ 默认记忆共享模式                                   │
├────────────────────────┼──────────────────────────────────────────────────┤
│ Leader ↔ Worker        │ ❌ 不共享记忆                                     │
│                        │ 仅通过 TaskProtocol + ProgressReport 通信         │
├────────────────────────┼──────────────────────────────────────────────────┤
│ Worker ↔ 其 Skills     │ ✅ 完全串联，共享同一记忆空间                       │
│                        │ Skill 寄生于 Worker 的记忆空间                     │
├────────────────────────┼──────────────────────────────────────────────────┤
│ Worker ↔ Worker        │ ⚠️ 按需配置（非硬编码）                            │
│                        │ 选项 A: 摘要桥接（默认）——只传精简摘要              │
│                        │ 选项 B: 全文共享——Worker A 可读 Worker B 完整上下文 │
│                        │ 选项 C: 完全隔离——Worker 之间不交换任何信息         │
│                        │ 选项 D: 单向提示——A 可向 B 发送特定记忆提示         │
├────────────────────────┼──────────────────────────────────────────────────┤
│ 用户 → Leader          │ 修改意见通过 Leader 分发                            │
│                        │ Leader 不公开用户原始消息给 Worker                  │
└────────────────────────┴──────────────────────────────────────────────────┘

配置示例（Leader 在计划中输出）：
  文档制作场景:
    画图Worker ← 获取书写Worker 的摘要 (选项 A: 需了解正文才能画图)
    审稿Worker ← 与其他Worker 完全隔离 (选项 C: 只看最终产物做评审)

  竞品分析场景:
    竞品Worker_A ←→ 竞品Worker_B: 全文共享 (选项 B: 需交叉验证数据)
    汇总Worker   ←  获取 A、B 的摘要 (选项 A)
```

### 6.2 三层物理存储 + 内部门控

物理上仍然分为三层存储，但**项目记忆内部有门控分区**：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          记忆层总览                                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │              项目记忆 (Project Memory — SQLite+FTS5)          │        │
│  │                                                              │        │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  │        │
│  │  │ Leader Task Mem  │  │ Worker Context  │  │ Summary      │  │        │
│  │  │ (领导任务记忆)    │  │ Memory          │  │ Bridge       │  │        │
│  │  │                 │  │ (Worker上下文)   │  │ (摘要桥接)    │  │        │
│  │  │ 存储:           │  │                 │  │              │  │        │
│  │  │ · 任务协议      │  │ 每个 Worker 一个 │  │ 存储:         │  │        │
│  │  │ · 进度汇报      │  │ 独立分区:        │  │ · Worker 输出 │  │        │
│  │  │ · 最终产物      │  │                 │  │   摘要        │  │        │
│  │  │ · 用户反馈      │  │ Worker_A:       │  │ · 关键决策    │  │        │
│  │  │                 │  │ · 执行全链路    │  │ · 依赖关系    │  │        │
│  │  │ 谁可写:         │  │ · 工具调用链    │  │              │  │        │
│  │  │ · Leader Agent  │  │ · 中间产物      │  │ 谁可写:       │  │        │
│  │  │                 │  │ · 与skills共享  │  │ · 各 Worker   │  │        │
│  │  │ 谁可读:         │  │                 │  │              │  │        │
│  │  │ · Leader Agent  │  │ Worker_B: ...   │  │ 谁可读:       │  │        │
│  │  │ · Leader Agent  │  │ Worker_C: ...   │  │ · 所有 Worker │  │        │
│  │  │                 │  │                 │  │ · Leader      │  │        │
│  │  │ 隔离:           │  │ 谁可写:         │  │              │  │        │
│  │  │ 仅 Leader 可见  │  │ · 该 Worker     │  │ 隔离:         │  │        │
│  │  │                 │  │ · 其 skills     │  │ 摘要内容      │  │        │
│  │  │                 │  │                 │  │ 不包含raw数据 │  │        │
│  │  │                 │  │ 谁可读:         │  │              │  │        │
│  │  │                 │  │ · 该 Worker     │  │              │  │        │
│  │  │                 │  │ · 其 skills     │  │              │  │        │
│  │  │                 │  │ · Evaluator     │  │              │  │        │
│  │  └─────────────────┘  └─────────────────┘  └──────────────┘  │        │
│  └──────────────────────────────────────────────────────────────┘        │
│                                                                          │
│  ┌───────────────────────────────┐  ┌───────────────────────────────┐    │
│  │ 评估记忆 (Eval Memory)         │  │ 知识库 (Knowledge Base)        │    │
│  │ SQLite 独立文件                │  │ SQLite + 向量索引 (chromadb)   │    │
│  │                               │  │                               │    │
│  │ 谁可写: 仅 Evaluator Agent    │  │ 谁可写: 用户上传 + 爬虫        │    │
│  │ 谁可读: Evaluator + Optimizer │  │ 谁可读: 所有 Agent（只读）     │    │
│  │                               │  │                               │    │
│  │ 存储:                         │  │ 存储:                          │    │
│  │ · 输入/输出快照                │  │ · 结构化知识                    │    │
│  │ · 评分结果 + 理由              │  │ · 模板 & 方法论                 │    │
│  │ · 优化建议                    │  │ · 工具评测数据                  │    │
│  │                               │  │ · 模型/工具对比                 │    │
│  └───────────────────────────────┘  └───────────────────────────────┘    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**存储引擎配置**：

OPC-Hermes 采用单用户本地部署模式，每工作流（一个 Leader + 多个 Worker）为独立实例。SQLite 在此场景下完全足够，但需要开启 WAL（Write-Ahead Logging）模式以支持并发读写：

```sql
-- 项目记忆数据库初始化
PRAGMA journal_mode=WAL;       -- Leader 写 ProgressReport 与 Worker 写 Context 可并发
PRAGMA synchronous=NORMAL;     -- 平衡安全性与性能
PRAGMA foreign_keys=ON;        -- 确保 TaskProtocol ↔ ProgressReport 引用完整性
PRAGMA busy_timeout=5000;      -- 写锁等待 5s 后超时报错而非无限阻塞
```

WAL 模式下，读写互不阻塞：Leader 写入 `leader_task_memory` 的同时，Worker 可以读取 `summary_bridge` 中的上游摘要。

### 6.3 门控记忆的运行时数据流

以"制作一份技术白皮书"为例，展示记忆如何在各 Agent 间流动：

```
时间线 →

1. 用户: "帮我写一份关于微服务架构的技术白皮书"
   └─→ Leader Agent 创建任务协议 (TaskProtocol)
       存储位置: Leader Task Memory
       内容: {task_id, 总体目标, 子任务清单, 标准要求}

2. Leader → Worker A（调研Agent）: "调研微服务最新最佳实践"
   └─→ 传递: TaskProtocol 的子集 {子任务id, 主题, 格式要求}
   └─→ Worker A 执行: skill(网页搜索) → skill(论文检索)
       记忆: Worker A ↔ skills 共享 Worker Context A

3. Worker A → Summary Bridge: 写入调研摘要
       内容: {关键发现 (≤500字), 参考来源列表, 对下游的建议}
       注意: 调研原始数据、爬虫日志不清洗进入摘要桥

4. Leader 收到 Worker A 进度汇报 → 更新 Leader Task Memory

5. Leader → Worker B（书写Agent）: "基于调研摘要写白皮书正文"
   └─→ 传递: TaskProtocol 子集 + Summary Bridge 中的调研摘要
   └─→ 注意: Worker B 看不到 Worker A 的完整上下文——只看摘要
   └─→ Worker B 执行: skill(章节撰写) → skill(风格调整)
       记忆: Worker B ↔ skills 共享 Worker Context B

6. Worker B → Summary Bridge: 写入正文摘要

7. Leader → Worker C（排版Agent）: "排版白皮书"
   └─→ 传递: 正文摘要 + 排版要求

8. Worker D（审稿Agent）并行: "审查完整内容"
   └─→ 传入: 所有 Worker 的 Summary Bridge 汇总
   └─→ 输出: 审稿意见（写入 Summary Bridge）

9. Evaluator Agent（旁系，全程监听）:
   └─→ 对步骤 2-8 的输入/输出快照打分 → 写入 Eval Memory
   └─→ 注意: Evaluator 只读不写，不进入 Leader/Worker 的记忆链路

10. Leader 汇总 → 产出最终白皮书 → 交付用户
```

### 6.4 核心数据结构

```python
@dataclass
class TaskProtocol:
    """Leader 向 Worker 分发的任务协议——这是他们之间唯一的通信载体"""
    task_id: str
    parent_task_id: str
    leader_id: str
    worker_id: str
    description: str                 # 任务描述
    input_summaries: List[str]       # 从 Summary Bridge 提取的上游摘要（非完整上下文）
    shared_context_access: List[str] # Leader 授权可读取完整上下文的 Worker ID 列表（共享模式 B 时生效）
    format_requirements: dict        # 输出格式要求
    deadline: Optional[datetime]
    priority: int                    # 0-10

@dataclass
class ProgressReport:
    """Worker 向 Leader 汇报进度——Leader 通过它了解完成度"""
    task_id: str
    worker_id: str
    status: str                      # IN_PROGRESS | BLOCKED | DONE
    completion_pct: float            # 0.0-1.0
    summary_for_bridge: str          # 写入 Summary Bridge 的摘要
    blockers: List[str]              # 阻塞原因（如有）
    key_decisions: List[str]         # 关键决策记录
    metrics: dict                    # 耗时、token 消耗等

@dataclass
class SummaryBridgeEntry:
    """Summary Bridge 中的一条记录——Worker 间仅通过此交换信息。
    
    摘要不限制字数，但强制结构化以保证下游 Worker 能快速精准定位信息。
    各字段职责明确分离：核心结论 vs 数据指标 vs 证据 vs 来源 vs 注意事项 vs 改进建议。
    """
    entry_id: str
    source_worker: str
    target_workers: List[str]        # 哪些下游 Worker 需要此摘要（空=所有）
    
    # ── 结构化摘要字段（不限字数，但要求精炼）──
    summary: str                     # 核心结论（不限字数，自由文本）
    key_metrics: dict                # 数据指标字典，例: {"总服务数": 12, "QPS峰值": 3500}
    data_evidence: List[str]         # 数据证据列表，例: ["来源A显示X增长23%", "来源B显示Y下降5%"]
    references: List[str]            # 引用来源（URL/DOI/文件路径），必须可追溯
    caveats: List[str]               # 注意事项/已知局限，例: ["来源A数据截止至2025Q4", "X指标不含海外用户"]
    suggestions: List[str]            # 改进建议列表，例: ["建议下游Worker重点关注X趋势", "数据源B可信度较低建议交叉验证"]

    def is_complete(self) -> bool:
        """校验摘要完整性：6 个强制字段全部非空"""
        return bool(
            self.summary and self.key_metrics and self.data_evidence
            and self.references and self.caveats and self.suggestions
        )

class GatedMemoryLayer:
    """
    门控记忆层的统一入口。
    封装物理三层存储，并在项目记忆内部实施门控。
    """

    def __init__(self):
        self.project_mem = ProjectMemory()    # SQLite+FTS5，内部含门控分区
        self.eval_mem = EvalMemory()          # 独立 SQLite
        self.knowledge_base = KnowledgeBase() # SQLite + 向量索引

    # ── Leader 接口 ──
    def create_task_protocol(self, task: TaskProtocol):
        """Leader 创建任务协议 → 写入 Leader Task Memory"""
        self.project_mem.leader_partition.save(task)

    def receive_progress_report(self, report: ProgressReport):
        """Leader 接收 Worker 进度汇报 → 更新 Leader Task Memory"""
        self.project_mem.leader_partition.update(report)
        # 同时更新 Summary Bridge
        self.project_mem.summary_bridge.upsert(
            source_worker=report.worker_id,
            summary=report.summary_for_bridge,
            key_decisions=report.key_decisions,
        )

    def get_task_completion(self, task_id: str) -> dict:
        """Leader 查询各 Worker 的完成度"""
        reports = self.project_mem.leader_partition.query_reports(task_id)
        return {
            r.worker_id: {"status": r.status, "completion": r.completion_pct}
            for r in reports
        }

    # ── Worker 接口 ──
    def get_worker_context(self, worker_id: str, task_id: str) -> WorkerContext:
        """Worker 获取自己的完整上下文（含其 skills 的历史）"""
        return self.project_mem.worker_partition(worker_id).get_full_context(task_id)

    def save_worker_context(self, worker_id: str, task_id: str, data: dict):
        """Worker 及其 skills 写入上下文（共享同一分区）"""
        self.project_mem.worker_partition(worker_id).save(task_id, data)

    def get_upstream_summaries(self, worker_id: str, task_id: str) -> List[SummaryBridgeEntry]:
        """Worker 从 Summary Bridge 获取上游 Worker 的摘要（不是完整上下文）"""
        return self.project_mem.summary_bridge.query(
            target_worker=worker_id,
            task_id=task_id,
        )

    def write_to_summary_bridge(self, entry: SummaryBridgeEntry):
        """Worker 完成子任务后写入摘要桥，供下游 Worker 使用"""
        self.project_mem.summary_bridge.write(entry)

    def get_full_upstream_context(self, worker_id: str, task_id: str,
                                   upstream_worker_id: str) -> Optional[WorkerContext]:
        """
        全文共享模式（共享模式 B）专用——下游 Worker 直接读取上游 Worker 的完整上下文。
        调用前 Leader 必须在 TaskProtocol.shared_context_access 中声明授权。
        """
        # 权限校验: 检查 Leader 是否授权了此访问
        task_protocol = self.project_mem.leader_partition.get_task(task_id)
        if worker_id not in task_protocol.shared_context_access:
            raise MemoryAccessDenied(
                f"Worker '{worker_id}' 未被授权访问 '{upstream_worker_id}' 的完整上下文。"
                f"请 Leader 在 shared_context_access 中声明授权。"
            )
        return self.project_mem.worker_partition(upstream_worker_id).get_full_context(task_id)

    # ── Leader 写、Worker 不可写 ──
    def save_user_feedback(self, task_id: str, feedback: str):
        """用户修改意见 → 仅 Leader 可写入和读取"""
        self.project_mem.leader_partition.save_feedback(task_id, feedback)

    # ── 评估记忆接口 ──
    def save_evaluation(self, eval_data: EvaluationRecord):
        """仅 Evaluator Agent 可调用"""
        self.eval_mem.save(eval_data)

    def get_quality_trend(self, agent_id: str, window: str = "7d"):
        """Optimizer 读取质量趋势"""
        return self.eval_mem.query_trend(agent_id, window)

    # ── 知识库接口 ──
    def upload_knowledge(self, source: str, content: Union[str, bytes]):
        """用户上传"""
        parsed = self._parse_content(source, content)
        self.knowledge_base.ingest(parsed, source_type="user_upload")

    def search_knowledge(self, query: str, top_k: int = 10):
        """Agent 只读查询。chromadb 不可用时自动降级为 FTS5 全文搜索。"""
        try:
            return self.knowledge_base.hybrid_search(query, top_k)
        except Exception as e:
            logger.warning(f"语义搜索不可用（chromadb 异常），降级为 FTS5 全文搜索: {e}")
            return self.knowledge_base.fts_search(query, top_k)
```

### 6.5 记忆冲突解决

| 冲突场景 | 裁决机制 |
|---------|---------|
| Leader Task Memory 与 Worker Context 冲突 | Leader 的 TaskProtocol 为权威版本；Worker 可记录"实际执行偏离协议"供复盘 |
| Worker A 摘要 vs Worker B 摘要（矛盾信息） | 不做自动裁决——标记 `conflict: true` 通知 Leader 做人工/LLM 裁定 |
| 同一 Worker 新旧上下文矛盾 | 时间戳优先；用户标记的上下文永不过期 |
| 用户知识 vs 爬虫知识 | 用户上传 > 爬虫内容（不可覆盖） |
| 优化建议冲突（切模型 A vs 模型 B） | 人工对比 → 数据决策 |

### 6.6 Schema 版本迁移策略

`TaskProtocol`、`ProgressReport`、`SummaryBridgeEntry` 等数据结构存储在 SQLite 中，随项目演进必然新增/删除/重命名字段。必须保证向后兼容——旧格式数据在新版本代码中可读、可转换。

```python
# opc_hermes/memory/schema_migration.py

SCHEMA_VERSION_KEY = "opc_hermes_schema_version"

MIGRATIONS: Dict[int, Migration] = {
    1: Migration(
        version=1,
        description="初始 schema（TaskProtocol 无 shared_context_access）",
        forward="ALTER TABLE task_protocol ADD COLUMN shared_context_access TEXT DEFAULT '[]'",
        rollback="ALTER TABLE task_protocol DROP COLUMN shared_context_access",
    ),
    2: Migration(
        version=2,
        description="SummaryBridgeEntry 增加 caveats_enabled 字段",
        forward="ALTER TABLE summary_bridge ADD COLUMN caveats_enabled INTEGER DEFAULT 1",
        rollback="ALTER TABLE summary_bridge DROP COLUMN caveats_enabled",
    ),
}

class SchemaMigrator:
    """启动时自动检测 schema 版本，按需执行前向迁移。"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def ensure_latest(self):
        current = self._read_version()
        target = max(MIGRATIONS.keys())
        if current >= target:
            return
        for version in range(current + 1, target + 1):
            migration = MIGRATIONS[version]
            self._apply_forward(migration)
            self._write_version(version)

    def _apply_forward(self, migration: Migration):
        """执行前向迁移 + 记录回滚脚本路径"""
        self._execute_sql(migration.forward)
        # 写入回滚脚本到 disk，供紧急回退使用
        self._write_rollback_script(migration.version, migration.rollback)
```

**迁移原则**：
- **增量式**：每次 schema 变更 = 一个新的 migration，不修改历史 migration
- **非破坏性**：所有 `ALTER TABLE ... ADD COLUMN` 必须带 `DEFAULT` 值
- **自动执行**：`GatedMemoryLayer.__init__()` 中自动调用 `SchemaMigrator.ensure_latest()`
- **回滚脚本**：每次前向迁移同时生成对应的 `.rollback.sql` 写入 `~/.hermes/opc/memory/migrations/`

---

## 7. 质量评估系统

### 7.1 Evaluator Agent（旁系）

Evaluator Agent 是 OPC-Hermes 的关键创新：**一个不参与任务执行、只负责评分的独立 Agent**。

```yaml
evaluator_agent:
  id: "evaluator"
  display_name: "质量评估 Agent"
  role: "旁系质量审计"
  
  # 关键特征
  design:
    memory_isolation: true       # 写入 Eval Memory，不写入 Project Memory
    read_only_project_mem: true  # 只读项目记忆中的输入/输出快照
    restricted_toolset: true     # 仅允许 opc_evaluator toolset 内工具（opc_capture_snapshot/opc_score_output/opc_write_evaluation），禁止通用工具（文件/Shell/终端）
    parallel_to_main_flow: true  # 评估不阻塞主流程

  evaluation_pipeline:
    - step: "capture"
      action: "从 Project Memory 读取已完成任务的输入/输出快照"
    
    - step: "score"
      action: "对每个维度打分"
      dimensions:
        worker_accuracy:
          description: "Worker 输出是否符合任务要求"
          weight: 0.30
        worker_quality:
          description: "Worker 输出本身的质量水平"
          weight: 0.25
        leader_decomposition:
          description: "Leader 的任务拆解是否合理、完整、无遗漏"
          weight: 0.20
        efficiency:
          description: "是否选择了合适的复杂度级别和工具"
          weight: 0.10
        memory_rule_quality:
          description: "Leader 定义的记忆共享规则是否合理"
          weight: 0.05
        user_satisfaction:
          description: "用户反馈信号（评分/点赞/踩/沉默/追问）"
          weight: 0.10
    
    - step: "reason"
      action: "生成评分理由和改进建议（区分: 对 Worker 的建议、对 Leader 的建议）"
    
    - step: "store"
      action: "写入 Eval Memory（独立 DB）"

  model: "claude-sonnet-4"      # 评分需要高质量判断力
```

### 7.1.1 大小 Evaluator 交叉验证机制

为防止 Evaluator 自身产生系统性偏差污染整个优化管道，引入双 Evaluator 架构：

```
┌──────────────────────────────────────────────────────────────────┐
│                     双 Evaluator 架构                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  小 Evaluator（常规评分）          大 Evaluator（主线复核）         │
│  ┌──────────────────────┐       ┌──────────────────────────┐     │
│  │ · 每次任务执行后触发   │       │ · 仅在异常信号出现时触发   │     │
│  │ · 评分维度:           │       │ · 职责: 检查小 Evaluator  │     │
│  │   accuracy / quality  │       │   的评分是否偏离设计主线   │     │
│  │   / efficiency /      │       │ · 不参与常规评分维度      │     │
│  │   leader_decomp /     │       │ · 不写入 Eval Memory     │     │
│  │   memory_rule /       │       │   （避免自我引用循环）    │     │
│  │   user_satisfaction   │       │                          │     │
│  │ · 写入 Eval Memory    │       │                          │     │
│  └──────────┬───────────┘       └────────────┬─────────────┘     │
│             │                                │                   │
│             │        触发条件                  │                   │
│             │  ┌─────────────────────┐        │                   │
│             ├──│ 连续 3 次评分骤降    │────────┤                   │
│             │  │ (overall 下降 >0.15)│        │                   │
│             │  └─────────────────────┘        │                   │
│             │  ┌─────────────────────┐        │                   │
│             ├──│ leader_decomposition│────────┤                   │
│             │  │ 维度持续 ≤ 0.5      │        │                   │
│             │  └─────────────────────┘        │                   │
│             │                                │                   │
│             ▼                                ▼                   │
│   Eval Memory                    review_flag 写入 Eval Memory    │
│   （存储评分）                    ┌──────────────────────────┐   │
│                                  │ reviewed: true           │   │
│                                  │ verdict: "偏严/偏松/正常" │   │
│                                  │ adjustment: ±0.05        │   │
│                                  │ summary: "复核结论..."   │   │
│                                  └──────────────────────────┘   │
│                                                                  │
│   Optimizer 读取 Eval Memory 时加权调整:                          │
│   被复核标记为"偏严"的评分 → 上浮 0.05                             │
│   被复核标记为"偏松"的评分 → 下调 0.05                             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**关键设计决策**：
- 大 Evaluator 使用比小 Evaluator 更强的模型（如 claude-opus-4），确保复核权威性
- 大 Evaluator **不写入独立评分**，仅写入 `review_flag` 标记——避免 Evaluator 评分与复核评分之间的递归引用
- 触发是异常驱动的（非周期性的），最小化额外成本
- `review_flag` 在 Eval Memory 中作为评分记录的附加字段，而非独立表

### 7.2 评分尺度

```python
class EvaluationRecord:
    """单次评估记录"""
    task_id: str
    agent_id: str
    complexity_level: str        # 判定时的复杂度
    actual_complexity: str       # 实际执行后反推的复杂度
    
    input_snapshot: str          # 用户原始输入
    output_snapshot: str         # Agent 最终输出
    
    scores:
        accuracy: float          # 0.0 - 1.0
        quality: float           # 0.0 - 1.0
        efficiency: float        # 0.0 - 1.0
        user_satisfaction: float # 0.0 - 1.0
        overall: float           # 加权总分
    
    reasoning: str               # 评分理由
    improvement_suggestions: List[str]
    
    metadata:
        model_used: str
        tools_used: List[str]
        latency_ms: int
        cost_usd: float
        fallback_triggered: bool
```

### 7.3 评分的消费方

| 消费者 | 如何使用 |
|--------|---------|
| **Optimizer** | 扫描评分趋势，发现质量下降 → 触发优化审查；发现某模型组合持续高分 → 提案推广 |
| **Leader Agent** | 实时读取评分，同一任务跑多个 Agent 时选最优结果返回用户 |
| **用户** | 可选地展示"本次任务质量评分: 8.7/10" |
| **知识库** | 高分输出的输入/输出对被提取为最佳实践模板 |

---

## 8. 自进化引擎

### 8.1 核心澄清：进化 ≠ 魔法

OPC-Hermes 的自进化引擎**不做**"从知乎自动读懂模型性价比"这类 NLP 魔术。而是两条实际可行的管道：

```
自进化引擎
├── 管道 1: 用户主动上传
│   用户将知识视频/文档/URL 上传 → 内容解析 → 结构化提取 → 写入知识库
│   触发方式: 手动 / 定时导入 / API
│
└── 管道 2: 自动爬虫
    配置知识源列表 → cron 定时爬取 → 去重清洗 → 质量评分 → 写入知识库
    触发方式: Hermes Agent Cron 模块调度
```

### 8.2 管道 1：用户上传

```python
class KnowledgeUploadPipeline:
    """用户主动上传知识"""

    SUPPORTED_FORMATS = {
        "video": ["mp4", "webm", "mov"],
        "document": ["pdf", "docx", "md", "txt", "html"],
        "url": ["*"],
        "image": ["png", "jpg", "webp"],
    }

    def upload(self, file_path: str, agent_scope: Optional[str] = None):
        """
        上传流程:
        1. 格式检测 → 选择解析器
        2. 内容提取（视频→whisper转录，PDF→markitdown，图片→OCR）
        3. 结构化提取（NER、分类、标签）
        4. 质量去重（避免重复写入已有知识）
        5. 事务写入知识库（SQLite + chromadb 双写，含补偿）
        """
        parser = self._select_parser(file_path)
        raw_content = parser.extract(file_path)
        structured = self._structure(raw_content)
        deduped = self._deduplicate(structured)

        # 5. 事务写入（先 SQLite，后 chromadb，失败时补偿）
        knowledge_id = self.knowledge_base.ingest_sqlite(
            deduped,
            source="user_upload",
            scope=agent_scope,
            priority="high"
        )
        try:
            self.knowledge_base.ingest_chroma(knowledge_id, deduped)
        except Exception as e:
            # chromadb 写入失败 → 回滚 SQLite 记录，避免双写不一致
            self.knowledge_base.delete_sqlite(knowledge_id)
            logger.error(f"知识入库失败（chromadb 写入异常，已回滚 SQLite）: {e}")
            raise KnowledgeIngestError(
                f"知识 '{deduped.get('title', file_path)}' 向量化失败，请检查 chromadb 服务状态"
            )
```

### 8.3 管道 2：自动爬虫

```python
class CrawlPipeline:
    """自动爬虫管道"""

    def __init__(self):
        self.sources: Dict[str, CrawlSource] = {}
        # 每个 Agent 注册自己的爬虫源
        # 由 Hermes Agent 的 cron/ 模块定时调度

    def register_source(self, agent_id: str, config: CrawlSource):
        """Agent 注册知识源"""
        self.sources[f"{agent_id}:{config.name}"] = config

    def execute(self, source_key: str):
        """
        爬取流程:
        1. 检查 robots.txt / 合规策略
        2. 速率控制 + 代理轮换
        3. 内容爬取 (Scrapy / Playwright)
        4. 去重清洗
        5. 质量评分（来源权威度 + 内容新鲜度 + 相关性）
        6. 写入知识库（标记 source_type=crawler, priority=low）
        """

    def schedule_all(self):
        """cron 入口: 遍历所有注册源，按各自的 interval 触发"""
        for key, source in self.sources.items():
            if source.should_run_now():
                self.execute(key)
```

#### 8.3.1 去重策略

爬虫管道步骤 4 的"去重清洗"采用三层递进策略，按计算成本从低到高排列：

| 层次 | 算法 | 适用场景 | 计算成本 |
|------|------|---------|---------|
| **第 1 层：精确去重** | **SHA-256 哈希** | 完全相同的内容（文件级/段落级） | O(1)，最低 |
| **第 2 层：近似去重** | **MinHash + LSH** (Locality-Sensitive Hashing) | 文本相似度 >80% 但非完全相同的文档（改写/洗稿），如 Datasketch 库 | O(n)，中等 |
| **第 3 层：语义去重** | **Embedding + 余弦相似度** (chromadb) | 意思相同但表述不同的文本 | 依赖向量索引，OPC 已引入 chromadb |

**推荐组合**（适配 OPC-Hermes 的规模）：

```python
class DedupPipeline:
    """
    混合递进去重管道。
    OPC-Hermes 规模（日入库 < 1 万条）推荐: 第 1 层（SHA-256 精确）+ 第 2 层（chromadb 语义）足矣。
    MinHash+LSH 近似层仅在日入库 > 1 万条时启用，代码中已省略。
    """

    def __init__(self, chroma_client=None):
        self.seen_hashes: Set[str] = set()    # SHA-256 去重
        self.chroma = chroma_client            # 语义去重（复用知识库的 chromadb 实例）

    def is_duplicate(self, content: str) -> tuple[bool, str]:
        """
        返回 (是否重复, 匹配层)。
        三层中任一命中即判定为重复，不再继续后续检查。
        """
        # 第 1 层: SHA-256 哈希（拦截精确重复）
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        if content_hash in self.seen_hashes:
            return True, "exact_hash"
        self.seen_hashes.add(content_hash)

        # 第 2 层: chromadb 向量相似度（拦截语义重复）
        if self.chroma:
            results = self.chroma.query(
                query_texts=[content[:500]],  # 前 500 字符做向量检索
                n_results=1,
            )
            if results["distances"] and results["distances"][0][0] < 0.05:
                return True, "semantic_similarity"

        return False, "unique"
```

**选型说明**：
- 如果每日入库量 <1 万条：第 1 + 3 层足矣（chromadb 已引入，零额外成本），MinHash 层可省略
- 如果每日入库量 >1 万条：建议在第 2 层增加 MinHash+LSH（如 `datasketch` 库），在向量检索前先拦截大量近似重复，降低 chromadb 的查询压力
- SHA-256 哈希集合使用 Bloom Filter 可进一步降低内存占用

### 8.4 从知识到优化：Evaluate → Propose → Test → Deploy

```
知识库（静态知识）
     │
     ▼
Optimizer 定时扫描（cron 每小时/每天）
     │
     ├─ 扫描 Eval Memory → 发现质量下降 Agent
     ├─ 扫描 Knowledge Base → 发现新工具/模型信息
     │
     ▼
生成优化提案（OptimizationProposal）
     │
     ├─ 是什么: 模型切换 / 工具替换 / Prompt 优化 / 阈值调整
     ├─ 为什么: 数据支撑（评分下降 / 新工具评测结果 / 成本对比）
     ├─ 预期收益: 质量 ↑X% / 成本 ↓Y%
     └─ 风险等级: LOW / MEDIUM / HIGH
     │
     ▼
推送优化提案到 WebUI Dashboard
     │
     ├─ 提案卡片展示: 类型 / 数据支撑 / 预期收益 / 风险等级
     ├─ LOW/MEDIUM 风险: 用户可直接点击 [应用]
     └─ HIGH 风险: 需额外确认，展示详细影响分析
     │
     ▼
用户审批:
     ├─ [应用] → 模型/工具/Prompt 切换 → 记录到 Eval Memory（提案ID + 切换时间）
     ├─ [忽略] → 提案归档，7 天后同类提案不重复推送
     └─ [稍后] → 提案保留在 Dashboard，下次登录仍可见
     │
     ▼
应用后监控:
     切换后连续观察 7 天质量/成本/延迟指标
     质量显著下降 → 自动告警 + 一键回滚到切换前版本
     质量正常     → 提案标记为 "successful"，同类场景自动推荐
```

### 8.5 Optimizer 核心逻辑

```python
class Optimizer:
    """
    后台持续运行: 监控 → 发现 → 提案 → 推送 Dashboard → 等待人工审批
    """

    def tick(self):
        """每个 cron 周期执行一次"""

        for agent_id in self.agent_list.list_active():
            # 1. 收集数据
            metrics = self.eval_mem.get_stats(agent_id, time_range="7d")
            new_knowledge = self.kb.search(f"优化机会 {agent_id}", top_k=10)

            # 2. 规则引擎
            proposals = []

            # 规则: SIMPLE 任务占比 > 50% 且还在用贵模型
            if metrics.simple_ratio > 0.5 and metrics.avg_cost > self.thresholds.cost_high:
                cheaper = self._find_cheaper_model(agent_id, quality_floor=0.95)
                if cheaper:
                    proposals.append(OptimizationProposal(
                        type="model_switch",
                        detail=cheaper,
                        expected_impact=f"成本预计降低 {cheaper.cost_reduction_pct}%",
                        risk="LOW"
                    ))

            # 规则: 质量连续 7 天下降
            if metrics.quality_trend == "declining" and metrics.days_declining >= 7:
                proposals.append(OptimizationProposal(
                    type="emergency_review",
                    detail={"agent": agent_id, "severity": "HIGH"},
                    expected_impact="阻止质量继续下降",
                    risk="HIGH"  # 需要人工审批
                ))

            # 规则: 工具链频繁触发 fallback
            if metrics.fallback_rate > 0.1:
                better_tool = self._find_better_tool(agent_id, new_knowledge)
                if better_tool:
                    proposals.append(OptimizationProposal(
                        type="tool_switch",
                        detail=better_tool,
                        risk="MEDIUM"
                    ))

            # 3. 推送提案到 Dashboard，等待人工审批
            for p in proposals:
                self._push_to_dashboard(p)
```

---

## 9. 多 Agent 协同编排

### 9.1 五种协同模式

#### 模式 1：Pipeline（顺序管道）

```
Agent A → Agent B → Agent C

适用: 有明确先后依赖的线性任务
示例: 数据分析 → 画图 → PPT 生成
```

#### 模式 2：Scatter-Gather（并行分发 → 汇总）

```
        ┌── Agent A（角度1）──┐
任务 ───┼── Agent B（角度2）──┼── 汇总 Agent → 结果
        └── Agent C（角度3）──┘

适用: 需要多角度同时分析的任务
示例: 竞品调研 → 同时爬知乎/GitHub/行业报告 → 汇总报告
```

#### 模式 3：Consensus（多 Agent 投票）

```
        ┌── 技术 Agent（视角: 可行性）
任务 ───┼── 产品 Agent（视角: 需求匹配）
        └── 数据 Agent（视角: 数据支撑）
                  │
                  ▼
            加权投票 → 决策

适用: 高风险决策，需要多角色验证
示例: 评估一个技术方案是否值得投入
```

#### 模式 4：Hierarchy（层级委托）

```
          Leader Agent
         ┌─────┼─────┐
    Worker A  Worker B  ...
      │   │
   Skill1  Skill2

适用: 超大型任务的分层拆解
示例: 完整产品从 0 到 1 开发
```

#### 模式 5：Star Delegation（星形委托 + 摘要桥接）—— 本文档核心模式

```
                        用户
                         │
                         ▼
                  ┌─────────────┐
                  │ Leader Agent │  ← 接收任务、拆解、分发、汇总
                  └──┬──┬──┬──┬──┘
                     │  │  │  │
        ┌────────────┘  │  │  └────────────┐
        ▼               ▼  ▼               ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ Worker A │  │ Worker B │  │ Worker C │  │ Worker D │
  │ (调研)   │  │ (书写)   │  │ (排版)   │  │ (审稿)   │
  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
       │              │              │              │
       └──────────────┼──────────────┼──────────────┘
                      │              │
                 ┌────▼──────────────▼────┐
                 │    Summary Bridge      │  ← 摘要，非完整上下文
                 │  (Worker 间仅通过摘要   │
                 │   桥接，不直接通信)      │
                 └────────────────────────┘

记忆边界:
· Leader ↔ Worker:        ❌ 不共享记忆，仅 TaskProtocol + ProgressReport
· Worker ↔ 其 Skills:      ✅ 完全串联，共享 Worker Context
· Worker ↔ Worker:         ⚠️ 默认通过 Summary Bridge（摘要），共享模式 B 下可通过 `get_full_upstream_context()` 读取完整上下文
· 用户 ↔ Leader:           修改意见经 Leader 分发给相关 Worker
```

**适用场景**: 需要多个专业 Agent 协作完成一个复杂产物（文档、报告、PPT）且要求统一调度。

**关键特征**:
1. Leader 拥有全局视图但不介入细节——通过 ProgressReport 了解完成度
2. 每个 Worker 独立工作，与自己的 skills 深度耦合，但不被其他 Worker 干扰
3. Summary Bridge 保证信息传递效率——Worker 只需知道上游做了什么，不需要看原始数据
4. 修订流程由 Leader 统一管控——用户改一句话，Leader 判断需要通知哪些 Worker

### 9.2 具体工作流示例：文档制作全流程

#### 场景: 用户要求制作一份技术白皮书

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     文档制作工作流 —— 完整生命周期                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  阶段 1: 任务拆解（Leader Agent）                                        │
│  ─────────────────────────────                                           │
│  用户: "帮我写一份关于微服务架构的技术白皮书，需要包含架构图和数据对比"      │
│                                                                         │
│  Leader Agent 拆解:                                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 子任务 1: 调研 → Worker(调研Agent)                                │   │
│  │   skills: [网页搜索, 论文检索, 竞品分析]                           │   │
│  │   输出: 调研摘要 (≤500字) + 参考来源                               │   │
│  │   依赖: 无                                                        │   │
│  │                                                                   │   │
│  │ 子任务 2: 正文撰写 → Worker(书写Agent)                             │   │
│  │   skills: [章节撰写, 风格调整, 技术写作]                           │   │
│  │   输入: 调研摘要 (来自 Summary Bridge)                              │   │
│  │   输出: 正文摘要 (≤500字) + 章节列表                                │   │
│  │   依赖: 子任务 1 完成                                              │   │
│  │                                                                   │   │
│  │ 子任务 3: 图表绘制 → Worker(绘图Agent) [并行]                      │   │
│  │   skills: [流程图, 数据图表, 架构图]                               │   │
│  │   输入: 正文摘要 + 图表需求列表                                     │   │
│  │   输出: 图表摘要 + 图片文件路径                                    │   │
│  │   依赖: 子任务 2 正文摘要可用即可开始                               │   │
│  │                                                                   │   │
│  │ 子任务 4: 排版 → Worker(排版Agent)                                 │   │
│  │   skills: [格式排版, 目录生成, 页眉页脚]                            │   │
│  │   输入: 正文摘要 + 图表摘要                                         │   │
│  │   输出: 排版后文档 (.docx)                                         │   │
│  │   依赖: 子任务 2 + 子任务 3 完成                                    │   │
│  │                                                                   │   │
│  │ 子任务 5: 审稿 → Worker(审稿Agent) [与排版并行或接续]               │   │
│  │   skills: [语法检查, 一致性审查, 引用核查]                          │   │
│  │   输入: 排版后文档 + 所有 Summary Bridge 条目                       │   │
│  │   输出: 审稿意见摘要                                               │   │
│  │   依赖: 子任务 4 产出版本                                           │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  阶段 2: 执行                                                            │
│  ─────────                                                              │
│                                                                         │
│  step 1: Leader → Worker(调研): TaskProtocol{topic, format}             │
│           Worker(调研) 调用 skills 完成调研                               │
│           Worker(调研) → Summary Bridge: 调研摘要                        │
│           Worker(调研) → Leader: ProgressReport{DONE, 100%}              │
│                                                                         │
│  step 2: Leader → Worker(书写): TaskProtocol{调研摘要, 结构要求}          │
│           Worker(书写) 调用 skills 撰写正文                               │
│           Worker(书写) → Summary Bridge: 正文摘要 + 图表需求列表          │
│           Worker(书写) → Leader: ProgressReport{DONE, 100%}              │
│                                                                         │
│  step 3: [并行]                                                          │
│           Leader → Worker(绘图): TaskProtocol{正文摘要, 图表规格}         │
│           Leader → Worker(排版): TaskProtocol{正文摘要, 排版模板}         │
│           两者并行执行...                                                 │
│                                                                         │
│  step 4: Leader → Worker(审稿): TaskProtocol{排版后文档, 审稿标准}       │
│           Worker(审稿) 调用 skills 审查                                   │
│           Worker(审稿) → Summary Bridge: 审稿意见                        │
│                                                                         │
│  step 5: Leader 汇总所有 Summary Bridge 条目 + 最终产物 → 交付用户        │
│                                                                         │
│  全程: Evaluator Agent（旁系）对每个 step 的输入/输出快照评分             │
│                                                                         │
│  阶段 3: 用户修订                                                         │
│  ────────────                                                            │
│                                                                         │
│  用户: "第三章太长了，精简一下。还有那个架构图换个颜色。"                    │
│                                                                         │
│  Leader Agent 分析修改意见:                                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ "第三章太长了" → 涉及 Worker(书写Agent)                           │   │
│  │ "架构图换个颜色" → 涉及 Worker(绘图Agent)                          │   │
│  │                                                                   │   │
│  │ Leader 判断: 排版、审稿不需要重新触发（改动幅度小）                 │   │
│  │ Leader 只向受影响的 Worker 分发修订任务:                           │   │
│  │                                                                   │   │
│  │ Leader → Worker(书写): TaskProtocol{修订: "第三章精简30%"}         │   │
│  │ Leader → Worker(绘图): TaskProtocol{修订: "架构图配色调整"}         │   │
│  │                                                                   │   │
│  │ 两 Worker 并行执行修订:                                            │   │
│  │ 各自的 Worker Context 保留原始版本，修订生成新版                    │   │
│  │ 修订完成后更新 Summary Bridge                                      │   │
│  │                                                                   │   │
│  │ Leader 汇总修订版本 → 交付用户                                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.3 修订/反馈闭环

用户修改意见的处理流程——这是传统 Agent 框架最薄弱的环节，OPC-Hermes 通过 Leader 统一管控：

```python
class RevisionHandler:
    """
    处理用户修订意见 → 分析影响面 → 只通知受影响 Worker
    """

    def handle_feedback(self, leader_id: str, task_id: str, feedback: str):
        # 1. 存储用户反馈到 Leader Task Memory（Worker 不可见原始反馈）
        memory.save_user_feedback(task_id, feedback)

        # 2. Leader 分析反馈 → 拆解为修订子任务
        revisions = self._analyze_feedback(feedback, task_id)
        # 例如: [
        #   {target: "writing_agent", action: "精简第三章", scope: "chapter_3"},
        #   {target: "diagram_agent", action: "调整架构图配色", scope: "arch_diagram"},
        # ]

        # 3. 判断哪些 Worker 需要重新触发
        affected_workers = self._identify_affected_workers(revisions)
        # 规则:
        # - 局部修改 → 只通知直接相关的 Worker
        # - 结构性修改（如"重写第二章"）→ 通知下游 Worker（排版/审稿）也重做
        # - 全文修改 → 通知所有 Worker

        # 4. 判断是否需要重新审稿/排版
        needs_re_review = self._structural_change(revisions)
        needs_re_format = self._layout_impact(revisions)

        if needs_re_review:
            affected_workers.append("review_agent")
        if needs_re_format:
            affected_workers.append("format_agent")

        # 5. 分发修订任务（仅给受影响的 Worker）
        for worker_id in affected_workers:
            revision_task = self._build_revision_task(
                worker_id,
                revisions,
                upstream_summaries=self._get_relevant_summaries(worker_id, task_id),
                previous_version_ref=self._get_previous_version(worker_id, task_id),
            )
            # Leader → Worker: 仅 TaskProtocol，不共享原始反馈
            self._dispatch_revision(leader_id, worker_id, revision_task)

        # 6. 等待受影响 Worker 完成修订 → 更新 Summary Bridge → Leader 汇总
        return self._await_and_aggregate(affected_workers)

    def _analyze_feedback(self, feedback: str, task_id: str) -> List[Revision]:
        """
        用 LLM 分析用户反馈，映射到具体 Worker 和 scope。
        输入: "第三章太长了，精简一下。还有那个架构图换个颜色。"
        输出: 结构化修订指令
        """
        ...

    def _identify_affected_workers(self, revisions: List[Revision]) -> List[str]:
        """
        修订影响面分析:
        · 内容修改（文字/数据） → writing_agent
        · 视觉修改（图/配色）   → diagram_agent
        · 格式修改（字体/页码） → format_agent
        · 结构性修改（增删章节）→ writing_agent + format_agent + review_agent
        """
        ...
```

### 9.4 Agent 间通信协议

```python
@dataclass
class AgentMessage:
    """Agent 间统一通信格式"""
    msg_id: str                       # UUID
    from_agent: str                   # Agent ID
    to_agent: str                     # Agent ID 或 "leader"
    msg_type: str                     # TASK_DELEGATE | RESULT | QUERY | FEEDBACK
    session_id: str                   # 关联会话

    task: Optional[dict] = None       # 委托的任务
    result: Optional[dict] = None     # 执行结果

    priority: int = 0                 # 0-10
    context: Optional[dict] = None    # 传递的上下文
    call_stack: List[str] = []        # 调用链（用于循环检测）

    metrics: Optional[dict] = None    # 执行指标
```

### 9.5 循环依赖检测

```python
class CycleDetector:
    """防止 Agent 间委托形成循环"""

    MAX_DEPTH = 5                     # 最大委托深度
    MAX_SAME_AGENT_CALLS = 2          # 同一 Agent 在同一条链中的最大出现次数

    def check(self, message: AgentMessage) -> bool:
        """
        返回 True = 安全，False = 检测到循环/过深
        """

        # 检查 1: 深度限制
        if len(message.call_stack) >= self.MAX_DEPTH:
            self._log(f"MAX_DEPTH exceeded: {message.call_stack}")
            return False

        # 检查 2: 同一 Agent 重复出现
        occurrences = Counter(message.call_stack)
        if occurrences.get(message.to_agent, 0) >= self.MAX_SAME_AGENT_CALLS:
            self._log(f"Agent {message.to_agent} called twice in chain")
            return False

        return True
```

### 9.6 DAG 编排器

> **核心机制**：复用 Hermes Agent 已有的 `delegate_tool`（`tools/delegate_tool.py`）。
> Leader 不自建进程管理器，而是通过 `delegate_task` 的 batch 模式原生支持并行派发。
> OPC-Hermes 在此之上封装 `OPCWorkerDispatcher`，负责记忆注入和结果收集。

```python
class OPCWorkerDispatcher:
    """
    OPC-Hermes 的 Worker 派发层——delegate_tool 的 OPC 封装。
    
    不替代 delegate_tool，而是在其上层增加：
    - 记忆门控注入（通过 delegate_task 的 context 参数）
    - Summary Bridge 更新（阶段完成后提取摘要）
    - DAG 拓扑排序执行
    
    底层能力由 delegate_tool 提供：
    - 并行 batch 执行（ThreadPoolExecutor，max_workers=8）
    - 可配置超时（delegation.child_timeout_seconds，默认 600s）
    - 心跳监控（每 30s 检测子 Agent 活跃度）
    - DelegateEvent 进度事件流（通过 Gateway SSE 推送给用户）
    - 超时诊断（0-API-call 时自动 dump 堆栈）
    """

    def __init__(self, agent_list: AgentList, memory: GatedMemoryLayer):
        self.agent_list = agent_list
        self.memory = memory

    def execute_dag(self, plan: ExecutionPlan, parent_agent) -> Dict[str, WorkerResult]:
        """
        将 DAG 计划转换为 delegate_task 调用序列。
        按拓扑排序逐阶段执行，每阶段内的任务并行。
        """
        from tools.delegate_tool import delegate_task
        
        results = {}
        
        for stage in plan.topological_stages():
            if stage.is_parallel():
                # 利用 delegate_tool 原生 batch 模式——并行启动多个子 Agent
                batch_tasks = [
                    {
                        "goal": task.description,
                        "context": self._build_worker_context(task),
                        "toolsets": task.toolsets + ["opc_memory"],
                        "role": "leaf",  # Worker 不能再委托
                    }
                    for task in stage.tasks
                ]
                batch_result = delegate_task(
                    tasks=batch_tasks,
                    parent_agent=parent_agent,
                )
                results.update(self._parse_batch_result(batch_result, stage))
            else:
                # 串行单任务
                task = stage.tasks[0]
                result = delegate_task(
                    goal=task.description,
                    context=self._build_worker_context(task),
                    toolsets=task.toolsets + ["opc_memory"],
                    role="leaf",
                    parent_agent=parent_agent,
                )
                results[task.id] = self._parse_result(result)
            
            # 阶段完成后更新 Summary Bridge（从 Worker 输出中提取摘要）
            self._update_summary_bridge(stage, results)
        
        return results

    def _build_worker_context(self, task: SubTask) -> str:
        """
        构建注入给子 Agent 的 context 字符串。
        这是 OPC-Hermes 记忆门控的实际注入点——
        通过 delegate_tool 的 context 参数传递，Worker 启动时即可见。
        """
        parts = []
        
        # 1. Worker 角色定义（system prompt）
        worker_config = self.agent_list.get(task.worker_id)
        parts.append(f"[角色定义]\n{worker_config.system_prompt}")
        
        # 2. 上游摘要（从 Summary Bridge 获取，实现记忆门控）
        if task.input_summaries:
            parts.append("[上游 Worker 信息]")
            for summary in task.input_summaries:
                parts.append(
                    f"- 来源: {summary.source_worker}\n"
                    f"  核心结论: {summary.summary}\n"
                    f"  关键指标: {summary.key_metrics}\n"
                    f"  注意事项: {', '.join(summary.caveats)}"
                )
        
        # 3. 记忆工具使用指引
        parts.append(
            "[记忆规则]\n"
            "完成任务后，你必须调用 opc_write_to_bridge 工具写入工作摘要，"
            "供下游 Worker 参考。摘要需包含：核心结论、关键数据、注意事项。"
        )
        
        return "\n\n".join(parts)

    def _update_summary_bridge(self, stage, results):
        """阶段完成后，从 Worker 输出中提取摘要写入 Summary Bridge。"""
        for task in stage.tasks:
            result = results.get(task.id)
            if result and result.status == "DONE":
                # Worker 应已通过 opc_write_to_bridge 工具主动写入
                # 此处做兜底：如果 Worker 忘记调用，从输出中自动提取
                if not self.memory.has_bridge_entry(task.id):
                    auto_summary = self._extract_summary_from_output(result.output)
                    self.memory.write_to_summary_bridge(SummaryBridgeEntry(
                        source_worker=task.worker_id,
                        summary=auto_summary,
                        key_metrics={},
                        data_evidence=[],
                        references=[],
                        caveats=["[自动提取] Worker 未主动调用 opc_write_to_bridge"],
                        suggestions=[],
                    ))
```

**配置**：

```yaml
# config.yaml — delegation 配置段（Hermes Agent 既有配置项）
delegation:
  child_timeout_seconds: 1800    # Worker 超时 30 分钟（适配 COMPLEX 任务）
  max_spawn_depth: 2             # Leader(depth=0) → Worker(depth=1)
  max_iterations: 100            # Worker 单次对话最多 100 轮 tool call
```

### 9.7 工作流故障处理

> **核心机制**：`delegate_tool` 已内置超时管理、心跳监控和超时诊断。
> OPC-Hermes 仅需处理 delegate_tool 返回的错误/超时结果，无需自建故障检测。

#### Worker 超时处理

```
delegate_tool 已内置的超时能力（无需 OPC 重建）：

1. child_timeout_seconds（默认 600s，OPC 配置为 1800s）
   · 超时后 delegate_tool 自动 cancel future + 调用 child.interrupt()
   · 返回超时错误信息给 Leader（LLM 可感知）

2. 心跳监控（每 30s 检测子 Agent 活跃度）
   · 空闲超 450s（15 cycles × 30s）→ 标记 stale
   · 卡在工具超 1200s（40 cycles × 30s）→ 标记 stale

3. 超时诊断（0-API-call 超时时自动 dump Python 堆栈）
   · 写入诊断文件供调试

OPC-Hermes 仅需在 Leader prompt 中引导 LLM 处理超时结果：
· delegate_task 返回包含 "timed out" 的 JSON → Leader 判断:
  - 任务可降级 → 用更小模型重试
  - 任务不可降级 → 向用户汇报并请求决策
```

按复杂度级别配置超时：

```yaml
# OPC 配置中按复杂度设定不同超时（由 OPCWorkerDispatcher 读取）
opc_hermes:
  workflow:
    default_timeouts:
      SIMPLE: 120      # 2 分钟
      MEDIUM: 600      # 10 分钟
      COMPLEX: 1800    # 30 分钟
```

#### 质量异常处理

```
Worker 输出质量极差:

  Leader 接收 Worker 结果
      │
      ▼
  Evaluator 评分 < 阈值 (默认 0.6)
      │
      ▼
  Leader 判断处理策略:
      │
      ├── 可降级处理: 切换 fallback 模型/工具 → 重试 1 次
      │    例: claude-sonnet-4 输出差 → 降级到 gpt-4o → 重试
      │
      ├── 需要重做: 保留原上下文，重新生成 → 重试 1 次
      │    例: 调研结果明显偏题 → 重写 TaskProtocol → 重新调研
      │
      └── 不可挽救: 向用户汇报，等待用户决策
           例: 所有模型输出都不符合要求 → 汇总问题 → 提交用户
```

#### 格式/工具错误处理

```
Worker 执行中遇到格式或工具错误:

  1. Worker 自身 skills 优先处理
     例: 排版Worker → skill(格式排版) 遇到 docx 格式错误
     → skill 内部尝试修复（换 pandoc 参数、换编码）

  2. Skill 无法处理 → Worker 上报 Leader
     例: skill 尝试了所有恢复策略均失败

  3. Leader 评估严重性:
     严重（产物无法使用）→ 提交用户评判
     轻微（格式瑕疵可忽略）→ 标记 warning，继续执行

  4. 错误日志全程记录 → 最终提交 Leader → Leader 向用户汇报
```

#### 并行执行中的错误隔离

```
Worker B (绘图) 和 Worker C (排版) 并行执行:

  Worker B 报错 ❌ → 不影响 Worker C 继续执行 ✅
  
  处理:
  1. Worker B 错误写入日志（不中断并行组）
  2. Worker C 正常完成
  3. 并行组全部结束后:
     Leader 收集:
       · 成功结果 (Worker C)
       · 错误日志 (Worker B)
       · 报警汇总
     → 根据错误严重性决定: 重试 B / 跳过 B / 提交用户
```

### 9.8 中断与恢复

> **核心机制**：delegate_tool 已内置 `child.interrupt()` 终止子 Agent 的能力。
> OPC-Hermes 在此基础上通过 OPC Memory Layer 实现跨会话的恢复点。

```
恢复机制（基于 delegate_tool + OPC Memory）:

1. 实时记忆存档（OPC Memory Layer 负责）
   · 每个 Worker 通过 opc_save_context 工具实时写入执行状态
   · Summary Bridge 在每个 DAG 阶段完成后更新
   · 不依赖内存——系统重启后 SQLite 数据仍在

2. 恢复点标记（Leader Task Memory）
   · 每个 DAG 阶段完成时 → Leader 在 Task Memory 中标记 ✓
   · 包含：已完成的阶段列表 + 各 Worker 的输出摘要
   · 恢复时只需重做未标记的阶段

3. 中断处理（两种场景）

   场景 A: 用户主动取消
   · 用户发 "取消" → pre_gateway_dispatch hook 拦截
   · 调用 delegate_tool 的 pause_spawning() → 阻止新 Worker 启动
   · 正在运行的 Worker 通过 child.interrupt() 终止
   · Leader 汇报已完成的部分结果给用户

   场景 B: 系统异常（进程崩溃/重启）
   · Gateway 重启 → 新会话中用户发 "继续上次任务"
   · pre_gateway_dispatch hook 检测到 Task Memory 中有未完成任务
   · 注入恢复 prompt → Leader 读取 Task Memory → 跳过已完成阶段
   · 仅对未完成阶段重新调用 delegate_task

4. 幂等保证
   · 每个 Worker 子任务有唯一 task_id
   · OPCWorkerDispatcher 执行前检查: task_id 是否已有 Summary Bridge 记录
   · 有 → 跳过该阶段（幂等）
   · 无 → 正常执行
```

### 9.9 用户交互模式

```
┌──────────────────────────────────────────────────────────────────┐
│                    用户交互时间线                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 用户发起任务                                                  │
│     "帮我写一份技术白皮书"                                         │
│                                                                  │
│  2. Leader 生成计划                                               │
│     ┌──────────────────────────────────────────┐                 │
│     │ 📋 任务计划已生成:                         │                 │
│     │                                          │                 │
│     │ 子任务:                                   │                 │
│     │  1. 调研Worker → 搜集微服务资料            │                 │
│     │  2. 书写Worker → 撰写白皮书正文            │                 │
│     │  3. 绘图Worker → 生成架构图和数据图        │                 │
│     │  4. 排版Worker → 格式排版                 │                 │
│     │  5. 审稿Worker → 质量审查                 │                 │
│     │                                          │                 │
│     │ 预估耗时: ~8分钟                           │                 │
│     │ 预估成本: $0.15                           │                 │
│     │                                          │                 │
│     │ 记忆规则:                                  │                 │
│     │  绘图 ← 书写摘要 / 审稿与其他隔离          │                 │
│     │                                          │                 │
│     │ [▶ 确认执行] [✏️ 修改计划] [✖ 取消]        │                 │
│     └──────────────────────────────────────────┘                 │
│                                                                  │
│  3. 用户确认 → 执行开始，用户可关闭对话                              │
│     · Leader 开始调度 Worker                                     │
│     · 用户通过 Hermes 进度通知获知进度                             │
│                                                                  │
│  4. 执行中（后台模式）                                             │
│     · 用户可随时查询进度: "进度？"                                 │
│     · 用户可取消: "取消" → Leader 终止所有 Worker                   │
│     · 用户可取消单个: "取消排版" → 只终止该 Worker                   │
│     · Leader 仅在遇到严重事故时主动中断:                            │
│       系统重启/关机、严重报错导致 Agent 无法继续、                   │
│       两次重试后仍失败 → 向用户汇报当前状态                          │
│                                                                  │
│  5. 执行完成 → 通知用户                                           │
│     "您的中小企业数字化白皮书已完成，点击下载 →"                     │
│                                                                  │
│  6. 用户修订循环                                                   │
│     用户提修改 → Leader 分析影响面 → 仅通知受影响 Worker             │
│     → 用户确认修订计划 → 执行修订 → 交付新版本                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**进度通知机制**：复用 Hermes Agent Gateway 的消息推送能力。Leader 在每个 Worker 完成时通过 Gateway 向用户发送进度更新。用户可随时回复"进度"查询当前状态。

**中间审批的最小化原则**：Leader 不会在执行过程中弹出审批对话框。唯一的中断点是——计划生成后执行前、以及严重事故导致无法继续时。这避免了"用户需要时刻盯着屏幕"的体验。

### 9.10 产物管理

```
产物存储:

{opc_artifact_root}/                    ← 系统配置的产物根目录
├── {task_id}/                          ← 每个工作流一个目录
│   ├── final/                          ← 最终产物（交付用户）
│   │   ├── 技术白皮书_v1.docx
│   │   ├── 技术白皮书_v2.docx          ← 修订版本
│   │   └── 架构图_v1.png
│   │
│   ├── intermediate/                   ← 中间产物（保留，可清理）
│   │   ├── research_raw/               ← 调研原始数据
│   │   ├── draft_chapters/             ← 各章节草稿
│   │   └── review_notes/               ← 审稿意见
│   │
│   └── manifest.json                   ← 产物清单（版本、来源 Worker）
│
└── ...

产物清单示例:
{
  "task_id": "doc-2026-001",
  "artifacts": [
    {"file": "final/技术白皮书_v1.docx", "version": 1,
     "producer": "format_worker", "size": 245760},
    {"file": "final/技术白皮书_v2.docx", "version": 2,
     "producer": "format_worker", "parent_version": 1},
    {"file": "final/架构图_v1.png", "version": 1,
     "producer": "diagram_worker"}
  ]
}
```

- **存储位置**：本地文件系统，根目录在系统配置中设定
- **最终产物**：长期保留，可被用户下载和引用
- **中间产物**：单独目录存放，可配置自动清理策略（如 30 天后删除）
- **版本关联**：修订产生新版本，manifest 记录父子关系
- **访问方式**：复用 Hermes Agent Gateway 的文件传输能力（如 Telegram 文件消息、Discord 附件等）

---

## 10. 共享基础设施

```
┌──────────────────────────────────────────────────────────────────┐
│                     OPC-Hermes 共享基础设施                        │
├────────────────┬─────────────────────────────────────────────────┤
│                │                                                 │
│ Agent List     │ Worker + Skill 的全局注册表（文件系统或 DB）         │
│                │ · Worker 注册: 系统默认 + 用户自定义 + Leader 自动生成│
│                │ · Skill 注册: 全局共享，各 Worker 按需绑定          │
│                │ · 发现: "我需要调研 → 查 Agent List 匹配 Worker"    │
│                │ · 质量分: 用户评分驱动的动态排序                    │
│                │ · 版本: 每次优化更新质量分和版本号                  │
│                │                                                 │
│ LLM Gateway    │ 统一模型调用代理层——所有 Agent 通过 Gateway 调模型     │
│                │                                                    │
│                │ 设计要点：                                           │
│                │ · 复用 Hermes Agent 的 Provider Resolution 机制     │
│                │   (providers/ 目录下各厂商的 API 封装)               │
│                │ · Gateway 在 Provider 层之上增加三件事：             │
│                │   1. 成本追踪：每次调用后记录 token 量 → opc_cost.db │
│                │   2. 速率限制：滑动窗口限流（按 Agent/分钟）         │
│                │   3. 负载均衡：同一模型多 API Key 时轮询分发         │
│                │ · 架构：                                            │
│                │   Agent.llm_call()                                  │
│                │     → LLMGateway.intercept(model, messages)         │
│                │       → RateLimiter.check(model, agent_id)          │
│                │       → CostTracker.estimate(model, messages)       │
│                │       → ProviderSelector.pick(model)  # 负载均衡    │
│                │       → hermes.providers.{model}.chat(messages)     │
│                │       → CostTracker.record(actual_tokens)           │
│                │     → return response                               │
│                │ · 不替换 Hermes Agent 的 Provider 实现，仅在其      │
│                │   `ChatProvider.chat()` 调用前后插入拦截逻辑        │
│                │                                                     │
│ 版本仓库       │ 每个 Agent 历史配置的 Git 存储（GitOps）             │
│ (GitOps)      │                                                    │
│                │ 设计要点：                                           │
│                │ · 源码仓库: github.com/334250/OPC-Hermes.git        │
│                │ · 存储位置: ~/.hermes/opc/gitops/agents/            │
│                │ · 技术: gitpython 库操作 Git                        │
│                │ · Commit 触发: 用户修改配置 / Optimizer 更新质量分  │
│                │   / 新 Worker 注册 → 自动 commit                   │
│                │ · Commit 粒度: 每个变更一个 commit                  │
│                │ · 回滚 API:                                         │
│                │   POST /api/opc/agents/{id}/rollback                │
│                │   → git checkout {hash} → reload config             │
│                │ · 本地 Git 管理，远程 push 为用户可选操作           │
│                │                                                 │
│ 监控 & 告警    │ 全系统指标聚合与本地可视化                             │
│                │ · 每个 Agent: 调用量 / 成本 / 质量 / 延迟          │
│                │ · 异常告警: 成本超标 / 质量骤降 / Agent 离线       │
│                │ · 技术栈: SQLite 指标表 + WebUI Dashboard           │
│                │ · 导出: 支持 JSON/CSV 导出供外部工具分析           │
│                │                                                 │
│ 沙箱           │ 代码/工具的安全执行环境                            │
│                │ · 复用 Hermes Agent 的 Terminal backends          │
│                │ · Docker sandbox 为 Tier-1 隔离                   │
│                │                                                 │
│ 安全护栏       │ 全系统的安全边界（见第 11 节）                      │
│                │                                                 │
└────────────────┴─────────────────────────────────────────────────┘
```

---

## 11. 安全护栏

### 11.1 成本护栏

OPC-Hermes 不做人工硬限制（不限制最长运行时间、不限制 Worker/Skill 数量、不限制修订循环次数），但通过成本预算防止意外失控：

```yaml
cost_guardrails:
  global:
    daily_budget: 50.0              # 全局日预算（可配置）
    alert_threshold: 0.8            # 预算消耗 80% 时告警
    # 注意: 不设置 per_task_budget——单个复杂任务可以消耗更多预算

  per_agent:
    daily_budget: ~                  # 每个 Agent 可选独立预算
    # 不限制 per_call_cap——让 Leader 根据任务复杂度和用户确认自主分配

  auto_cutoff:
    enabled: true
    trigger: "global_daily_budget_exceeded"
    action: "stop_new_tasks_and_alert"  # 超全局预算 → 停止新任务 + 通知，不中断运行中的任务

  design_principle: >
    信任 Leader Agent 的调度判断 + 用户确认机制。
    不做"单任务最多5个Worker"或"最多3轮修订"之类的硬限制——
    限制应该来自预算约束，而非流程约束。
```

### 11.2 内容安全

```yaml
content_guardrails:
  blocked_topics:
    - "武器制造"
    - "毒品合成"
    - "色情内容"
    - "黑客攻击工具"
    - "个人信息伪造"

  pii_detection:
    enabled: true
    patterns: ["phone", "id_card", "bank_card", "address"]
    action: "mask_and_log"         # 检测到 → 脱敏 + 记录

  injection_prevention:
    enabled: true
    strategy: "input_sanitization + role_boundary_enforcement"
    # 用户输入 → 经过清洗后再拼入 prompt
    # Agent 角色边界: 代码 Agent 不能执行"帮我写一篇小红书文案"
```

### 11.3 操作护栏

```yaml
operation_guardrails:
  require_human_approval:
    - "新 Agent 上线"
    - "模型主选方案变更"
    - "全局日预算调整"
    - "工具链 tier-1 替换"

  auto_rollback:
    triggers:
      quality_drop_gt: 0.10        # 质量下降 > 10%
      error_rate_gt: 0.05          # 错误率 > 5%
      cost_exceed_pct: 1.20        # 成本 > 预算 120%
    action: "rollback_to_previous_version + alert"

  tool_execution_safety:
    code_agent:
      forbidden_commands: ["rm -rf /", "format", "shutdown", ":(){ :|:& };:"]
      require_approval: ["sudo", "pip install", "npm install -g", "docker rm"]
      network_isolation: true       # 默认不允许访问外部网络
```

### 11.4 权限模型

OPC-Hermes 是单用户本地部署系统，无多用户隔离需求。权限设计简化为**操作风险分级**：

```yaml
permissions:
  risk_levels:                    # 操作按风险分级，非按角色分级
    safe:                          # 直接执行，不需确认
      - "use_agents"               # 使用 Agent
      - "view_tasks"               # 查看任务
      - "upload_knowledge"         # 上传知识（本地文件，安全）
      - "view_eval_reports"        # 查看评估报告

    cautious:                      # 首次执行时提示确认，可记住选择
      - "trigger_crawl"            # 手动触发爬虫（可能产生网络请求）
      - "modify_agent_config"      # 修改 Agent 配置
      - "adjust_budget"            # 调整预算上限

    restricted:                    # 每次都需要用户确认
      - "approve_high_risk"        # 审批高风险命令执行
      - "install_packages"         # pip/npm install 等系统级操作
```

> 多用户场景（如团队共享 Agent List）由 Hermes Agent 的 Gateway 层鉴权，不在 OPC 范围。

---

## 12. 实施路线图

### 12.1 总览

```
Phase 0 ─ 基础集成（2 周）
  └─ 里程碑: 3 个角色 Agent 在 Hermes Agent 上独立运行，记忆工具可用，CLI 皮肤上线，模型偏好生效

Phase 1 ─ 记忆与评估（3 周）
  └─ 里程碑: Agent 结果可量化评分，三层记忆隔离生效

Phase 2 ─ 自动优化基础版（3 周）
  └─ 里程碑: 一个 Agent 完成 1 次自动模型切换

Phase 3 ─ 多 Agent 协同（3 周）
  └─ 里程碑: 跨 Agent 任务自动拆分 + 协同执行

Phase 4 ─ 全自治运行（持续）
  └─ 里程碑: 7 天无人工介入
```

### 12.1.1 冷启动策略

**问题定义**：系统首次部署时，所有数据驱动的智能管道均处于"空转"状态——没有历史评分、没有质量趋势、没有知识积累。从第 0 天到"数据足够驱动决策"之间存在一个无方向的随机游走期。

| 组件 | Cold Start 状态 | 后果 |
|------|----------------|------|
| **Eval Memory** | 评分记录为零 | Optimizer 无法判断质量趋势，所有阈值判断短路 |
| **Agent List 质量分** | 所有 Worker/Skill `quality_score = 0.0` | Leader 无法根据历史表现择优路由 |
| **ComplexityRater 缓存** | `self.cache = {}` 完全空 | 每个任务都需调用 LLM 判定，零成本节省 |
| **Knowledge Base** | 空库 | Agent 语义搜索永远返回空，只能依赖模型训练数据 |
| **历史基线缺失** | 无历史评分数据 | Optimizer 提案缺乏历史对比依据，初期提案置信度低 |

**缓解策略**：

```
冷启动缓解措施:

1. 预置种子评分数据:
   ┌────────────────────────────────────────────────────────────┐
   │ 系统初始部署时，附带 100 条典型任务的模拟评分:               │
   │ · 覆盖 SIMPLE / MEDIUM / COMPLEX 三个复杂度级别              │
   │ · 覆盖所有系统默认 Worker 类型                               │
   │ · 标记 score_source: "preset"（区别于真实评分）              │
   │ · Optimizer 读取时对 preset 评分给予较低置信度权重（0.5x）   │
   └────────────────────────────────────────────────────────────┘

2. Agent List 预设质量分:
   ┌────────────────────────────────────────────────────────────┐
   │ 系统默认 Worker 预设初始质量分 3.5★:                         │
   │ · 标记 score_source: "preset"                               │
   │ · 真实评分积累 ≥ 10 条后，preset 分自动失效                  │
   │ · 用户自定义 Worker 初始分 0.0，标记 "unrated"              │
   └────────────────────────────────────────────────────────────┘

3. ComplexityRater 预填缓存:
   ┌────────────────────────────────────────────────────────────┐
   │ 预置 50 条高频任务类型 × 复杂度判定结果的缓存条目:            │
   │ · "写一篇技术博客" → MEDIUM (0.7)                            │
   │ · "修复一个typo" → SIMPLE (0.95)                             │
   │ · "重构整个模块"→ COMPLEX (0.85)                             │
   │ · 标记 cache_source: "preset"，ttl: 30天                    │
   │ · 真实判定后自动覆盖                                          │
   └────────────────────────────────────────────────────────────┘

4. 渐进式激活 Optimizer:
   ┌────────────────────────────────────────────────────────────┐
   │ 不要求部署即全功能运行:                                      │
   │ · Week 1: 仅收集数据，不触发优化提案                         │
   │ · Week 2: 触发 LOW 风险提案（需 ≥ 30 条真实评分）            │
   │ · Week 4: 触发 MEDIUM 风险提案（需 ≥ 100 条真实评分）        │
   │ · Week 8: 全功能运行                                         │
   └────────────────────────────────────────────────────────────┘
```

### 12.2 Phase 0：基础集成（第 1-2 周）

**目标**：验证"角色 Agent = system prompt + toolset"的可行性，跑通一个最简链路。

| 任务 | 详情 | 产出 |
|------|------|------|
| 0.1 | 配置 3 个角色 Agent（代码、画图、文档）——每个 = 一个带专用 system prompt 和 toolset 的 Hermes Agent 实例 | agent_configs/ 目录 |
| 0.2 | 实现 AgentList——Worker + Skill 全局注册表，支持按 ID 和能力匹配 | agent_list.py |
| 0.3 | 实现 ComplexityRater Skill——共享复杂度判定，注入到 Hermes Agent Tool Registry | complexity_rater.py |
| 0.4 | 实现基础 Leader Agent——接收用户输入 → ComplexityRater 判定 → 路由到对应 Worker → 返回结果 | leader_agent.py |
| 0.5 | Hermes CLI 皮肤优化——为 OPC-Hermes 定制 CLI 界面（Rich 主题、OPC 品牌色、工作流状态面板、Agent List 浏览命令） | cli_skin/ |
| 0.6 | 模型偏好配置——实现三层优先级（用户配置 > Leader 推荐 > 自动路由），支持按 Agent/Workflow/Skill 级别覆盖 | model_prefs.py |
| 0.7 | 端到端测试：3 种不同类型任务各跑通 10 次 | 测试报告 |

### 12.3 Phase 1：记忆与评估（第 3-5 周）

**目标**：建立三层记忆空间和旁系评估体系。

| 任务 | 详情 | 产出 |
|------|------|------|
| 1.1 | 参考 CrewAI Memory 设计实现三层记忆空间（Project / Eval / KB） | memory_layer/ |
| 1.2 | 实现 Evaluator Agent——只读 Project Mem，只写 Eval Mem | evaluator.py |
| 1.3 | 评分维度定义 + 评分 Prompt 模板 | eval_prompts/ |
| 1.4 | 知识库基础版：用户上传 → 解析 → 存储 → 检索 | knowledge_base.py |
| 1.5 | Agent 接入记忆层：每次执行自动写入 Project Mem，Evaluator 异步评分 | 集成代码 |

### 12.4 Phase 2：自动优化基础版（第 6-8 周）

**目标**：跑通一次完整的自动优化闭环。

| 任务 | 详情 | 产出 |
|------|------|------|
| 2.1 | 实现 Optimizer 基础版——cron 定时扫描 Eval Mem + KB | optimizer.py |
| 2.2 | 实现 Optimizer 提案引擎——cron 扫描 Eval Mem + KB → 生成 OptimizationProposal → 推送到 Dashboard | optimizer.py |
| 2.3 | 实现版本仓库（GitOps）——每次配置变更 = 一次 commit，支持一键回滚 | version_repo/ |
| 2.4 | 爬虫通道 v0.1——手动配置 3 个知乎话题 + 2 个 GitHub topic | crawl_pipeline.py |
| 2.5 | 端到端测试：用户从 Dashboard 审批并应用一个模型切换提案，验证回滚可用 | 测试报告 |

### 12.5 Phase 3：多 Agent 协同（第 9-11 周）

**目标**：用户一个复合请求 → 自动拆解 → 多 Agent 协同执行。

| 任务 | 详情 | 产出 |
|------|------|------|
| 3.1 | 实现 DAG 编排器——意图解析 → 子任务拆解 → 拓扑执行 | dag_executor.py |
| 3.2 | 实现 Agent 间通信协议 + 上下文传递 | agent_message.py |
| 3.3 | 四种协同模式实现（Pipeline / Scatter-Gather / Consensus / Hierarchy） | orchestration_modes/ |
| 3.4 | 循环检测 + 深度限制 | cycle_detector.py |
| 3.5 | 端到端测试："做一份 Q2 销售分析 PPT"（数据→画图→PPT） | 测试报告 |

### 12.6 Phase 4：全自治运行（持续）

**目标**：系统可以无人值守运行。

| 任务 | 详情 | 产出 |
|------|------|------|
| 4.1 | Grafana 监控大屏——所有 Agent 的调用量/成本/质量/延迟实时可视 | dashboard/ |
| 4.2 | 自动告警 + 自动回滚 | alerting/ |
| 4.3 | 新 Agent 模板化注册——填写 YAML → 自动生成 Agent 实例 | agent_template.yaml |
| 4.4 | 稳定性测试——7 天无人介入，系统正常运转 | 稳定性报告 |

---

## 13. 附录

### 附录 A：术语表

| 术语 | 定义 |
|------|------|
| **OPC-Hermes** | 本项目——Hermes Agent 之上的多 Agent 管理层 |
| **Hermes Agent** | Nous Research 开源的底层 Agent 运行时 |
| **Leader Agent** | OPC-Hermes 的调度中枢（同义 Orchestrator），负责意图解析、任务拆解、Worker 匹配/生成、DAG 编排、进度收集、修订分发 |
| **Worker Agent / 角色 Agent** | 具有明确角色定义、独立记忆空间、可被 Leader 调度的执行单元 |
| **Skill** | Worker 的专项能力单元，全局注册、跨 Worker 共享，寄生在调用它的 Worker 的记忆空间中 |
| **Agent List** | Worker + Skill 的全局注册表，Leader 通过它发现、匹配、管理 Agent |
| **ComplexityRater** | 共享的复杂度评级 Skill，所有 Agent 共用 |
| **Evaluator Agent** | 不参与任务执行的旁系评估 Agent |
| **项目记忆 (Project Memory)** | 执行 Agent 的上下文、结果、工具链记录 |
| **评估记忆 (Eval Memory)** | Evaluator Agent 的评分数据，与项目记忆物理隔离 |
| **知识库 (Knowledge Base)** | 用户上传 + 爬虫采集的结构化知识 |
| **Optimizer** | 后台持续运行的自动优化引擎 |

### 附录 B：Agent 注册模板

```yaml
# 新增角色 Agent 的标准注册模板
agent:
  id: "agent_unique_id"
  display_name: "中文名称"
  domain: "tech|creative|document|business|automation"
  role: "角色一句话描述"
  version: "1.0.0"
  status: "draft|staging|production|deprecated"

  system_prompt: |
    你是一个[角色]。你的职责是[...]。
    你能做: [...]
    你不能做: [...]（→ 委托给 [其他Agent]）

  complexity_criteria:
    SIMPLE:
      conditions: [...]
      example: "..."
    MEDIUM:
      conditions: [...]
      example: "..."
    COMPLEX:
      conditions: [...]
      example: "..."

  model_routing:
    SIMPLE: {primary: {model, max_cost}, fallback: [{model, max_cost}]}
    MEDIUM: {primary: {model, max_cost}, fallback: [{model, max_cost}]}
    COMPLEX: {primary: {model, max_cost}, fallback: [{model, max_cost}]}

  tool_chain:
    task_type_1:
      tier_1: {tool, desc}
      tier_2: {tool, desc}
      tier_3: {tool, desc}
    # ... 更多任务类型

  toolset: "corresponding_hermes_toolset_name"

  # ── Agent List 注册字段 ──
  quality_score: 0.0               # 用户评分驱动的质量分，初始 0.0
  generated_by: "user|crawler|leader"  # 来源: 用户创建/爬虫/Leader 自动生成
  skills_bound: ["web_search", "paper_fetch"]  # 绑定的 skills（引用 Skills List）

  learning:
    knowledge_sources: [...]
    focus_areas: [...]

  quality:
    self_check: true
    evaluator_model: "minicpmv4.6"
    thresholds:
      overall: 0.7
      accuracy: 0.8
```

### 附录 C：关键设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 复杂度判定的归属 | 共享 Skill 而非 Agent 内嵌 | 避免每个 Agent 重复实现；判定逻辑可独立进化 |
| 记忆隔离方式 | 独立 SQLite 文件 | 简单、零依赖、与 Hermes Agent 的方案一致 |
| 评估 Agent 的位置 | 旁系（不参与主流程） | 避免评分污染执行上下文；评分独立可信 |
| Agent 间通信 | 通过 Leader Agent，非 P2P | 防止循环依赖；统一调度和监控 |
| 工具链降级 | 三级静态声明 + 运行时选择 | 平衡灵活性和可预测性 |
| 版本管理 | Git + 符号链接 current/ | 简单可靠，回滚即 checkout |
| 优化审批模式 | 全部提案需人工审批，无自动执行 | 单用户场景下自动 A/B 无意义；用户手动决策更可靠 |
| 自进化来源 | 用户上传 + 爬虫，不做 NLP 自动推理 | 务实可靠，逐步自动化 |
| Orchestrator 与 Leader 的关系 | 合并：Leader Agent 即为调度中枢 | 消除双头管理，单一职责 |
| Worker 发现机制 | Agent List + Leader 自动匹配/生成 | Leader 自主完成 Worker 发现，缺失时自动生成并注册 |
| Worker 间记忆规则 | Leader 按需定义，非硬编码 | 画图 Worker 可能需要文档摘要，审稿 Worker 可能需要完全隔离 |
| Leader ↔ Worker 记忆 | 不共享，仅 TaskProtocol + ProgressReport | 保护 Worker 上下文不被 Leader 细节污染；Leader 只需知道完成度 |
| 工作流不设硬限制 | 不限最长运行时间、Worker 数、Skills 数、修订次数 | 限制来自预算而非流程；信任 Leader + 用户确认 |
| 用户交互模式 | 计划确认 + 后台执行 + 仅严重事故中断 | 用户不需要盯屏幕；最小化审批中断 |
| 模型控制 | 三层优先级：用户配置 > Leader 推荐 > 复杂度自动路由 | 平衡用户控制和自动化；用户可精细到 Skill 级别指定模型 |
| 记忆注入机制 | 记忆操作注册为 Hermes Agent 工具，Worker prompt 引导调用 | 不修改 Hermes Agent 核心循环，零侵入 |
| Worker 自动生成限制 | 仅生成 system prompt，不生成新工具 | 工具必须预先注册到 Skills List；承认 LLM 不能创建可执行代码 |
| Leader→Worker 通信 | AgentTaskDispatcher 异步派发 → subprocess 运行 Worker → SQLite 交换协议 | 新增 Worker 进程管理器，复用 Agent 实例化 |
| 故障恢复 | 实时记忆存档 + 恢复点标记 + 幂等执行 | 系统重启后可从最近恢复点继续，无需从头开始 |
| Skills 管理 | 全局 Skills List，Worker 自主挑选绑定 | Skills 跨 Worker 共享，版本由用户评分驱动优化 |
| 集成方式 | Plugin 系统 + 独立配置 + Cron API，不修改源码 | 源码验证确认：Hermes config 不支持未知键、cron 无 register() API、TOOLSETS 为运行时可变 dict；因此采用 Plugin 运行时注入方案而非源码 import |

### 附录 D：与同类框架的差异

| 框架 | Agent 角色 | 记忆隔离 | 自动进化 | 模型路由 | 与底层 Agent 的关系 |
|------|-----------|---------|---------|---------|-------------------|
| **CrewAI** | 有（Crew+Agent） | 有（Unified Memory + Scope） | ❌ | ❌ | 自建运行时 |
| **LangGraph** | 有（Subgraph） | 有（Checkpointer） | ❌ | ❌ | 自建运行时 |
| **AutoGen** | 有（Agent 类型） | 部分（ChatHistory） | ❌ | ❌ | 自建运行时 |
| **Anthropic Subagent** | 有（Handoff） | ❌ | ❌ | ❌ | 平台绑定 |
| **OPC-Hermes** | ✅ 角色分层 | ✅ 三层门控 | ✅ 用户上传+爬虫+评测 | ✅ 三层优先级 | **管理层（不替换运行时）** |

---

> **文档结束**
>
> OPC-Hermes 不是一个新 Agent 框架，而是让已有 Agent 框架"长出"一支数字员工团队的管理层。
> 它站在 Hermes Agent 的肩膀上——复用其稳定的运行时、丰富的工具、广泛的平台支持，
> 同时补上角色分工、记忆隔离、质量评估和自动进化这四个关键拼图。
>
> 最终愿景：**用户只需要说"帮我做 X"，OPC-Hermes 的 Leader Agent 自动拆解任务，匹配 Worker，生成计划与用户确认；执行过程中 Leader 调度各 Worker 协同完成，独立的 Evaluator 把关质量，Optimizer 持续进化——整个过程用户无需关心"用哪个模型""调哪个工具"这些底层细节。**

---

## 附录 E：架构修正（基于 Hermes Agent v0.15.1 源码验证）

> **版本**：v3.0.1 修正补丁
> **日期**：2026-06-06
> **修正依据**：对 Hermes Agent v0.15.1 源码的逐行验证
> **影响范围**：§9.6 DAG 编排器、§2.2 七个集成点（第 6 条）、整体 Leader 运行模型

---

### E.1 修正 1：Worker 派发机制——复用 delegate_tool，弃用 AgentTaskDispatcher

#### E.1.1 原设计问题

原 §9.6 设计了 `AgentTaskDispatcher`（基于 `multiprocessing.Process` + `ProcessPoolExecutor`），存在以下问题：

1. **超时机制误解**：设计文档引用 `model_tools.py` L145 的 `future.result(timeout=300)` 作为"300 秒硬超时"约束。但源码验证表明：该超时仅适用于 `run_sync()` 函数——一个将 async 协程桥接到同步执行的工具，不是全局 tool dispatch 超时。同步 tool 函数（如 `delegate_task`）不经过此路径。
2. **重复造轮子**：Hermes Agent 已有完善的子 Agent 编排工具 `delegate_tool`（[tools/delegate_tool.py](../hermes-agent/tools/delegate_tool.py)），具备并行 batch 模式、可配置超时（默认 600s）、心跳监控、`role="orchestrator"` 嵌套支持。
3. **跨进程 SQLite 问题**：`multiprocessing.Process` 跨进程无法共享 SQLite 连接，增加不必要的 IPC 复杂度。

#### E.1.2 源码证据

```python
# hermes-agent/model_tools.py L142-145 — 仅影响 async 工具
pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
future = pool.submit(_run_in_worker)
return future.result(timeout=300)  # ← 仅 run_sync() 内部使用

# hermes-agent/tools/delegate_tool.py L513 — delegate_tool 有独立的超时机制
DEFAULT_CHILD_TIMEOUT = 600  # seconds before a child agent is considered stuck

# hermes-agent/tools/delegate_tool.py L1491-1514 — 子 Agent 执行
child_timeout = _get_child_timeout()  # 可配置，默认 600s
_timeout_executor = ThreadPoolExecutor(max_workers=1, ...)
_child_future = _timeout_executor.submit(_run_with_thread_capture)
result = _child_future.result(timeout=child_timeout)  # 600s 超时

# hermes-agent/tools/delegate_tool.py L1918-1942 — batch 并行模式
def delegate_task(
    goal=None, context=None, toolsets=None,
    tasks=None,          # ← 传入 tasks 数组即为并行 batch 模式
    role=None,           # ← "orchestrator" 允许子 Agent 再委托
    parent_agent=None,
) -> str:
```

#### E.1.3 修正方案：OPCWorkerDispatcher

```python
class OPCWorkerDispatcher:
    """
    OPC-Hermes 的 Worker 派发层。
    不替代 delegate_tool，而是在其上层封装 OPC 的记忆注入和进度收集逻辑。
    
    取代原设计中的 AgentTaskDispatcher（已废弃）。
    """

    def __init__(self, agent_list: AgentList, memory: GatedMemoryLayer):
        self.agent_list = agent_list
        self.memory = memory

    def dispatch_workers(self, plan: ExecutionPlan, parent_agent) -> Dict[str, WorkerResult]:
        """
        将 DAG 计划转换为 delegate_task 调用序列。
        
        关键设计：
        - 串行阶段：单个 delegate_task(goal=..., context=..., toolsets=[...])
        - 并行阶段：单个 delegate_task(tasks=[{goal, context, toolsets}, ...])
        - 每个 Worker 的 context 参数包含：
            · 从 Summary Bridge 提取的上游摘要
            · Worker 专属 system prompt（角色定义）
            · 记忆工具的使用指引（prompt 级引导）
        """
        from tools.delegate_tool import delegate_task
        
        results = {}
        
        for stage in plan.topological_stages():
            if stage.is_parallel():
                # 利用 delegate_tool 原生 batch 模式
                batch_tasks = [
                    {
                        "goal": task.description,
                        "context": self._build_worker_context(task),
                        "toolsets": task.toolsets + ["opc_memory"],
                        "role": "leaf",
                    }
                    for task in stage.tasks
                ]
                batch_result = delegate_task(
                    tasks=batch_tasks,
                    parent_agent=parent_agent,
                )
                results.update(self._parse_batch_result(batch_result, stage))
            else:
                task = stage.tasks[0]
                result = delegate_task(
                    goal=task.description,
                    context=self._build_worker_context(task),
                    toolsets=task.toolsets + ["opc_memory"],
                    role="leaf",
                    parent_agent=parent_agent,
                )
                results[task.id] = self._parse_result(result)
            
            # 阶段完成后更新 Summary Bridge
            self._update_summary_bridge(stage, results)
        
        return results

    def _build_worker_context(self, task: SubTask) -> str:
        """
        构建注入给子 Agent 的 context 字符串。
        这是 OPC-Hermes 记忆门控的实际注入点——通过 delegate_tool 的 context 参数传递。
        """
        parts = []
        
        # 1. Worker 角色定义（system prompt）
        worker_config = self.agent_list.get(task.worker_id)
        parts.append(f"[角色定义]\n{worker_config.system_prompt}")
        
        # 2. 上游摘要（从 Summary Bridge 获取，实现记忆门控）
        if task.input_summaries:
            parts.append("[上游 Worker 信息]")
            for summary in task.input_summaries:
                parts.append(
                    f"- 来源: {summary.source_worker}\n"
                    f"  核心结论: {summary.summary}\n"
                    f"  关键指标: {summary.key_metrics}\n"
                    f"  注意事项: {', '.join(summary.caveats)}"
                )
        
        # 3. 记忆工具使用指引（prompt 引导 Worker 主动调用记忆工具）
        parts.append(
            "[记忆规则]\n"
            "完成任务后，你必须调用 opc_write_to_bridge 工具写入工作摘要，"
            "供下游 Worker 参考。摘要需包含：核心结论、关键数据、注意事项。"
        )
        
        return "\n\n".join(parts)
```

#### E.1.4 配置变更

```yaml
# config.yaml — delegation 配置段
delegation:
  child_timeout_seconds: 1800    # OPC Worker 最长 30 分钟（COMPLEX 任务需要）
  max_spawn_depth: 2             # Leader(depth=0) → Worker(depth=1)
  max_iterations: 100            # Worker 单次对话最多 100 轮工具调用
```

#### E.1.5 对比表

| 维度 | 原设计（AgentTaskDispatcher） | 修正方案（OPCWorkerDispatcher） |
|------|------|------|
| 进程模型 | multiprocessing.Process（跨进程） | ThreadPoolExecutor（同进程，delegate_tool 原生） |
| 超时机制 | 需自建（误解 300s 限制） | delegate_tool 已有 600s 可配置 + 心跳监控 |
| 进度通知 | 需自建 SQLite 轮询 | delegate_tool DelegateEvent 事件流 |
| 工具注册 | 需重复注册到子进程 | 继承父 Agent 的 ToolRegistry |
| Gateway 集成 | 需自建通知管道 | 已有 SSE/WebSocket 推送 |
| 新增代码量 | ~500 行 | ~150 行封装 |

---

### E.2 修正 2：Leader Agent 运行模型——Gateway Agent + Prompt 增强

#### E.2.1 原设计问题

原设计未明确 Leader 的运行模型：是独立进程、独立 event loop、还是寄生在 Hermes Agent 会话循环中？这导致以下不确定性：
- Leader 如何接收 Gateway 消息？
- Leader 如何在对话循环中保持 DAG 状态？
- Leader 进程崩溃时如何恢复？

#### E.2.2 修正方案：Leader = Gateway Agent 本身

**核心决策：不创建独立的 Leader 进程。Leader 就是当前 Gateway Agent 实例，通过 `pre_gateway_dispatch` hook 动态获得调度能力。**

```
                        用户消息
                            │
                            ▼
┌───────────────────────────────────────────────────────────────┐
│          Hermes Agent Gateway (不修改)                          │
│          · _handle_message() 接收消息                           │
│          · pre_gateway_dispatch hook 判断是否为 OPC 任务          │
└─────────────────────────┬─────────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │ hook 返回 "rewrite"                │ hook 返回 "allow"
        │ → 注入 OPC Leader Prompt           │ → 正常 Agent 处理
        ▼                                    ▼
┌─────────────────────────┐      ┌──────────────────────┐
│  同一个 Agent 实例       │      │  标准 Hermes Agent    │
│  system prompt 被动态增强 │      │  行为（简单任务）     │
│                         │      └──────────────────────┘
│  增强内容：              │
│  · Leader 调度指引       │
│  · OPC 工具使用规范      │
│  · Agent List 摘要       │
│                         │
│  可用工具增加：           │
│  · opc_plan_generate    │
│  · opc_complexity_rate  │
│  · delegate_task (原生) │
│  · opc_memory 工具集    │
│                         │
│  Agent LLM 推理后调用:   │
│  1. opc_complexity_rate │  → 评级
│  2. opc_plan_generate   │  → 生成计划 → 返回给用户确认
│  3. delegate_task(...)  │  → 派发 Worker → 等待完成
│  4. 汇总 + 交付         │  → 返回最终产物
└─────────────────────────┘
```

#### E.2.3 实现代码

```python
# opc_hermes/plugin.py — OPC Plugin 核心 hook

def _pre_gateway_dispatch_hook(event, gateway, session_store, **kwargs):
    """
    Gateway 级消息拦截器——OPC-Hermes 的入口。
    
    判断用户请求是否需要多 Agent 编配：
    - 简单任务（问答、单步操作）→ 放行给标准 Agent
    - 复杂任务（需要多角色协同）→ 注入 Leader prompt，让 Agent 以 Leader 身份思考
    
    源码确认：此 hook 在 gateway/run.py L6854-6893 中被调用，
    支持 "skip"/"rewrite"/"allow" 三种 action。
    """
    # 快速判断：短消息、问答类、slash 命令直接放行
    text = event.text or ""
    if len(text) < 20 or text.startswith("/"):
        return {"action": "allow"}
    
    # 检查是否为"确认执行"/"取消"等 OPC 交互指令
    opc_action = _check_opc_interactive_action(text, session_store)
    if opc_action:
        return opc_action
    
    # 复杂度预判（基于规则，不调用 LLM——避免 hook 中产生延迟）
    if not _likely_complex_task(text):
        return {"action": "allow"}
    
    # 注入 Leader 行为 prompt
    leader_prefix = _build_leader_injection(text)
    return {
        "action": "rewrite",
        "text": leader_prefix + text,
    }


def _build_leader_injection(user_text: str) -> str:
    """
    构建 Leader 行为指引前缀。
    注入后 LLM 将以 Leader 角色推理，主动调用 OPC 工具。
    """
    return (
        "[OPC-HERMES LEADER MODE]\n"
        "你现在是 OPC-Hermes Leader Agent——多 Agent 协同调度中枢。\n"
        "对于用户的请求，按以下步骤处理：\n"
        "1. 调用 opc_complexity_rate 评估任务复杂度\n"
        "2. 若为 MEDIUM/COMPLEX，调用 opc_plan_generate 生成执行计划\n"
        "3. 将计划展示给用户确认（含子任务清单、Worker 分配、记忆规则）\n"
        "4. 用户确认后，使用 delegate_task 的 batch 模式派发 Worker\n"
        "5. 收集所有 Worker 结果后汇总交付用户\n"
        "6. 若为 SIMPLE，直接执行无需编配\n\n"
        "[用户原始请求]\n"
    )


def _likely_complex_task(text: str) -> bool:
    """
    基于规则的复杂度预判（不调用 LLM，确保 hook 延迟 <1ms）。
    
    宁可误判（把简单任务当复杂）也不漏判（把复杂任务当简单）。
    误判的代价：多一次 opc_complexity_rate 调用（<300ms）。
    漏判的代价：复杂任务没有走编配流程，质量下降。
    """
    # 关键词匹配
    complex_keywords = [
        "帮我做", "帮我写", "帮我生成", "制作", "分析报告",
        "PPT", "白皮书", "文档", "方案", "调研",
        "完整的", "全面的", "多个", "包含", "以及",
    ]
    hit_count = sum(1 for kw in complex_keywords if kw in text)
    
    # 长度 + 关键词数量联合判断
    return len(text) > 50 and hit_count >= 2


# pre_llm_call hook — 每次 LLM 调用前动态注入 OPC 上下文
def _pre_llm_call_hook(messages, model, **kwargs):
    """
    在 LLM 调用前注入 OPC 上下文信息（Agent List 摘要、历史质量分等）。
    
    源码确认：此 hook 在 VALID_HOOKS 集合中（hermes_cli/plugins.py L136）。
    """
    session_id = kwargs.get("session_id")
    if not session_id:
        return None
    
    # 仅在 OPC 模式激活时注入
    opc_context = _get_opc_context_for_session(session_id)
    if not opc_context:
        return None
    
    # 注入到 system message 末尾
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] += f"\n\n[OPC Agent List 概览]\n{opc_context}"
    
    return None
```

#### E.2.4 为什么不用独立进程

| 方案 | 问题 |
|------|------|
| Leader 作为独立 subprocess | 需自建 IPC、重复 LLM 连接、无法使用 Gateway 消息推送、崩溃需额外守护 |
| Leader 作为独立 event loop | 与 Hermes Agent 的 `run_conversation()` 设计冲突，无法复用工具链 |
| **Leader = Gateway Agent + prompt 增强** | 零额外进程、复用全部基础设施、delegate_tool 原生支持、Gateway 故障恢复直接适用 |

#### E.2.5 状态保持

Leader 在同一个 `run_conversation()` 调用中完成所有操作：
1. LLM 推理 → 调用 opc_plan_generate → 返回计划文本（一个 tool call 周期）
2. 用户确认（通过 Gateway 消息，触发新一轮 `run_conversation()`）
3. LLM 推理 → 调用 delegate_task → 阻塞等待 Worker 完成 → 返回汇总结果

DAG 执行状态通过 OPC Memory Layer（SQLite）持久化，跨 `run_conversation()` 调用时从 DB 恢复。

---

### E.3 修正 3：Plugin Hook 可用性确认

#### E.3.1 源码验证结果

对 `hermes_cli/plugins.py` L127-167 的 `VALID_HOOKS` 集合逐项验证：

| Hook | 源码位置 | 验证状态 | OPC 用途 |
|------|---------|----------|---------|
| `pre_gateway_dispatch` | gateway/run.py L6854-6893 | **已确认**，支持 skip/rewrite/allow | 消息拦截，注入 Leader prompt |
| `pre_tool_call` | hermes_cli/plugins.py L128 | **已确认** | 可选：工具调用前的安全检查 |
| `post_tool_call` | hermes_cli/plugins.py L129 | **已确认** | 捕获 delegate_task 结果，更新 Summary Bridge |
| `pre_llm_call` | hermes_cli/plugins.py L136 | **已确认** | LLM 调用前注入 OPC 上下文（Agent List、记忆摘要） |
| `on_session_start` | hermes_cli/plugins.py L140 | **已确认** | 初始化 OPC 会话状态 |
| `on_session_end` | hermes_cli/plugins.py L141 | **已确认** | 触发 Evaluator 评分 |

#### E.3.2 pre_gateway_dispatch 完整行为（源码逐行确认）

```python
# gateway/run.py L6854-6893 完整行为：

# 触发条件：仅对用户消息触发（is_internal=False）
if not is_internal:
    _hook_results = invoke_hook(
        "pre_gateway_dispatch",
        event=event,               # MessageEvent 完整对象
        gateway=self,              # GatewayRunner 实例（可访问 session_store）
        session_store=self.session_store,  # 会话存储
    )

# 遍历 hook 返回值（支持多个 plugin 注册同一 hook）：
for _result in _hook_results:
    if _result.get("action") == "skip":
        return None                      # 丢弃消息，不回复
    if _result.get("action") == "rewrite":
        event = dataclasses.replace(event, text=_result["text"])  # 替换消息文本
        break
    if _result.get("action") == "allow":
        break                            # 正常分发

# 重要：hook 在 auth 之前运行（L6859 注释确认）
# 重要："rewrite" 后消息继续走正常的 auth → agent dispatch 流程
```

#### E.3.3 结论

设计文档 §2.2 第 6 条中对 `pre_gateway_dispatch` 的描述**完全准确**。无需修改 Hook 相关设计。OPC Plugin 可安全使用以下 hook 组合：

- `pre_gateway_dispatch` → 入口判断 + 消息重写
- `pre_llm_call` → 动态注入 OPC 上下文
- `post_tool_call` → 捕获 Worker 执行结果
- `on_session_start` / `on_session_end` → 会话生命周期管理

---

### E.4 修正 4：异步任务派发与进度通知方案

#### E.4.1 问题消解

基于 E.1 和 E.2 的修正，**原设计中 "Leader 轮询 SQLite ProgressReport" 的需求已经消失**：

- Leader = Gateway Agent 本身（无独立进程）
- Worker 通过 `delegate_task` 在 ThreadPoolExecutor 中执行（同进程）
- `delegate_tool` 内部已有完善的事件流机制（`DelegateEvent`）

#### E.4.2 delegate_tool 已有的进度事件

```python
# tools/delegate_tool.py L532-549 — 已定义的事件类型
class DelegateEvent(str, enum.Enum):
    TASK_SPAWNED = "delegate.task_spawned"        # Worker 启动
    TASK_PROGRESS = "delegate.task_progress"      # Worker 进度更新
    TASK_COMPLETED = "delegate.task_completed"    # Worker 完成
    TASK_FAILED = "delegate.task_failed"          # Worker 失败
    TASK_THINKING = "delegate.task_thinking"      # Worker 思考中
    TASK_TOOL_STARTED = "delegate.tool_started"   # Worker 调用工具
```

这些事件通过 Gateway 的 SSE/WebSocket 实时推送到用户前端——无需 OPC 自建通知管道。

#### E.4.3 两阶段执行模型

```
阶段 1：快速计划（同步，<15 秒）
─────────────────────────────────────
用户消息 → pre_gateway_dispatch hook 注入 Leader prompt
         → Agent run_conversation() 开始
         → LLM 推理 → 调用 opc_complexity_rate（<1s）
         → LLM 推理 → 调用 opc_plan_generate（~3s）
         → LLM 返回计划文本给用户
         → run_conversation() 结束
         
用户看到：计划卡片 + [确认执行] [修改] [取消] 按钮

阶段 2：后台执行（可能 1-30 分钟）
─────────────────────────────────────
用户发送 "确认" → 新一轮 run_conversation() 开始
         → LLM 推理 → 调用 delegate_task(tasks=[...])
         → delegate_tool 内部并行启动 Worker（ThreadPoolExecutor）
         → 实时发送 DelegateEvent → Gateway SSE 推送给用户
         → 所有 Worker 完成 → delegate_task 返回结果
         → LLM 推理 → 汇总结果
         → run_conversation() 结束
         
用户看到：实时进度流（"Worker A 完成..."） → 最终产物

关键：delegate_task 的阻塞不影响 Gateway 处理其他用户的消息
（Gateway 为每个 session 使用独立的 asyncio task/线程）
```

#### E.4.4 用户中断方案

```python
# 利用 Hermes Agent 已有的中断机制

# 1. 用户发 "取消" → 触发新的 pre_gateway_dispatch hook 调用
def _check_opc_interactive_action(text, session_store):
    """处理 OPC 交互指令（确认/取消/查询进度）。"""
    if _is_cancel_intent(text):
        # 利用 delegate_tool 的 pause_spawning() 机制
        from tools.delegate_tool import pause_spawning
        pause_spawning()
        return {
            "action": "rewrite",
            "text": "[系统指令] 用户请求取消当前 OPC 任务。"
                    "请终止子任务并汇报已完成的工作。"
        }
    
    if _is_progress_query(text):
        # 从 OPC Memory 读取当前进度
        progress = _get_current_task_progress(session_store)
        return {
            "action": "rewrite",
            "text": f"[系统指令] 用户查询进度。当前状态：\n{progress}\n请汇报给用户。"
        }
    
    return None

# 2. Hermes Agent 已有的 interrupt 机制（CLI: Ctrl+C, Gateway: 特殊消息）
#    delegate_tool 内部会调用 child.interrupt() 终止子 Agent
```

#### E.4.5 ProgressReport 的保留价值

虽然不再需要通过 SQLite 轮询 ProgressReport，但 `ProgressReport` 数据结构**仍然保留**——用于：
- Evaluator Agent 异步读取各 Worker 的执行元数据
- Optimizer 分析历史执行效率
- 中断恢复时重载 Worker 状态

写入时机改为：`post_tool_call` hook 在 `delegate_task` 完成后写入。

---

### E.5 修正 5：性能基准与 SQLite 并发分析

#### E.5.1 SQLite WAL 模式并发能力分析

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     SQLite WAL 并发模型（修正后场景）                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  修正后所有组件运行在同一进程（ThreadPoolExecutor），共享 SQLite 连接池：     │
│                                                                          │
│  Writer 场景：                                                            │
│  · Leader 线程（主线程）：写 TaskProtocol（任务开始时 1 次）                  │
│  · Worker 线程 A/B/C：各自写 Worker Context + Summary Bridge              │
│  · Evaluator 线程：写 Eval Memory（独立 DB 文件，无竞争）                   │
│                                                                          │
│  WAL 模式行为：                                                           │
│  · 读-写不阻塞：多个 reader 与 1 个 writer 可并发                           │
│  · 写-写串行化：同一时间只有 1 个 writer，其余 busy-wait                    │
│  · busy_timeout=5000ms：写锁等待 5 秒后报 SQLITE_BUSY                    │
│                                                                          │
│  最坏情况：5 个 Worker 同时完成，同时尝试 write_to_bridge()                 │
│  · 单条 INSERT 耗时：~0.5-2ms（含 fsync）                                 │
│  · 5 个 writer 串行化：0.5ms × 5 = 2.5ms（最后一个等待 ≤2ms）              │
│  · 远低于 busy_timeout=5000ms → 不会 SQLITE_BUSY                          │
│                                                                          │
│  Eval Memory 独立 DB → 与 Project Memory 零竞争                           │
│  Knowledge Base 独立 DB → 与 Project Memory 零竞争                        │
│                                                                          │
│  结论：SQLite WAL + ThreadPoolExecutor 在 OPC 场景下完全足够               │
│        瓶颈不在 DB 并发，而在 LLM API 调用延迟（占总耗时 85-95%）           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

#### E.5.2 性能基准（SLA 目标）

| 阶段 | 指标 | P50 | P95 | Max | 说明 |
|------|------|-----|-----|-----|------|
| 计划生成 | 用户感知延迟 | 3s | 8s | 15s | ComplexityRater + LLM 推理 |
| Worker SIMPLE | 子任务执行 | 15s | 45s | 120s | 小模型 + 简单工具 |
| Worker MEDIUM | 子任务执行 | 60s | 180s | 600s | 主力模型 + 多步工具 |
| Worker COMPLEX | 子任务执行 | 180s | 600s | 1800s | 大模型 + 复杂管道 |
| 记忆写入 | write_context | 2ms | 10ms | 50ms | 单条 SQLite INSERT |
| 记忆读取 | read_summaries | 5ms | 20ms | 100ms | FTS5 全文搜索 |
| 知识搜索 | vector_search | 50ms | 200ms | 1000ms | chromadb 语义检索 |

#### E.5.3 吞吐量目标

| 指标 | 目标值 | 受限因素 |
|------|--------|---------|
| 并发 Worker 数 | 8 | ThreadPoolExecutor max_workers |
| 同时处理用户任务数 | 3 | Gateway 并发 session 数 |
| SQLite 写入/秒 | 500+ | WAL 模式实测可达 1000+ INSERT/s |
| API 调用/分钟 (Anthropic) | 50 | Provider rate limit |
| API 调用/分钟 (OpenAI) | 60 | Provider rate limit |

#### E.5.4 瓶颈分析

```
性能瓶颈排序（从高到低影响）：

1. LLM API 延迟（占总延迟 85-95%）
   ┌──────────────────────────────────────────────────────────┐
   │ 模型              │ 首 token  │ 完整响应 (500 token)       │
   │ claude-sonnet-4   │ 1-3s      │ 8-15s                     │
   │ gpt-4o-mini       │ 0.3-0.8s  │ 2-5s                      │
   │ gemini-2.5-flash  │ 0.5-1.5s  │ 3-8s                      │
   │ minicpmv4.6 (本地)│ 0.1-0.3s  │ 1-3s                      │
   └──────────────────────────────────────────────────────────┘
   
   优化策略：
   · SIMPLE 任务强制用小模型 → 单任务延迟降低 60-80%
   · ComplexityRater 用最轻模型 minicpmv4.6 → 判定延迟 <300ms
   · delegate_task batch 并行 → 5 个 Worker 并行调用，总延迟 ≈ 最慢一个

2. 并行 Worker 间的 API 并发限制
   · 5 个 Worker 并行 → 5 个并发 API 请求
   · Anthropic 50 req/min → 5 并发完全无压力
   · 优化：不同 Worker 使用不同 Provider 可进一步分散负载

3. chromadb 向量搜索（知识库查询）
   · 首次加载 embedding 模型: ~2s（冷启动开销）
   · 后续查询: 50-200ms
   · 优化：Plugin on_session_start 中预热 + 降级到 FTS5 的 fallback 机制

4. SQLite 并发写入
   · 不是瓶颈：即使 8 个 Worker 同时写入，串行化延迟仅 ~8ms
```

#### E.5.5 Evaluator 评估采样策略

为控制评估成本，增加采样率配置：

```yaml
# 评估采样率（避免每个任务都触发 Evaluator）
evaluator:
  sampling:
    SIMPLE: 0.3        # SIMPLE 任务仅评估 30%
    MEDIUM: 0.7        # MEDIUM 任务评估 70%
    COMPLEX: 1.0       # COMPLEX 任务全部评估
    user_rated: 1.0    # 用户主动评分的任务 100% 入库
  
  # 大 Evaluator 触发条件不变（异常驱动，非周期性）
  cross_validation:
    trigger_on_score_drop: 0.15    # 连续 3 次评分骤降 >0.15
    trigger_on_low_decomp: 0.5    # leader_decomposition 维度持续 ≤0.5
```

预估日成本（100 个子任务/天）：
- SIMPLE 70 × 0.3 = 21 次评估 → ~$0.63
- MEDIUM 25 × 0.7 = 18 次评估 → ~$0.54
- COMPLEX 5 × 1.0 = 5 次评估 → ~$0.15
- **总计 ~$1.32/天**（对比全评估的 ~$5-10/天）

---

### E.6 修正后的新增文件清单（对比原设计）

原设计新增 28 个文件，修正后精简为：

```
opc_hermes/
├── __init__.py
├── plugin.py                     ← OPC Plugin 入口（hooks + 工具注册）
│   └── hooks: pre_gateway_dispatch, pre_llm_call, post_tool_call,
│              on_session_start, on_session_end
│
├── leader_prompt.py              ← Leader Prompt 构建（取代独立 leader_agent.py 的调度逻辑）
│   └── 功能: 复杂度预判 + Leader 行为指引 + Agent List 摘要注入
│
├── worker_dispatcher.py          ← OPCWorkerDispatcher（~150 行，delegate_tool 封装）
│   └── 取代原 AgentTaskDispatcher (multiprocessing) ← 已废弃
│
├── complexity_rater.py           ← 不变（注册为 Hermes Agent Tool）
├── agent_list/                   ← 不变（Worker + Skill 注册表）
│
├── memory_layer/
│   ├── gated_memory.py           ← 不变（门控记忆层）
│   ├── tools.py                  ← 不变（opc_memory 工具集）
│   ├── task_protocol.py          ← 简化：ProgressReport 改为 post_tool_call 写入
│   └── summary_bridge.py         ← 不变
│
├── evaluator.py                  ← 不变（独立 Agent 实例）+ 增加采样率配置
├── optimizer.py                  ← 不变（cron 定时优化）
├── knowledge_pipeline.py         ← 不变
├── revision_handler.py           ← 不变
├── model_prefs.py                ← 不变
│
├── workflow/
│   ├── dag_executor.py           ← 简化：调用 worker_dispatcher，不自建进程管理
│   ├── cycle_detector.py         ← 不变
│   └── artifact_manager.py       ← 不变
│   └── ✗ fault_handler.py        ← 删除：delegate_tool 已有超时/心跳/诊断
│   └── ✗ recovery.py             ← 简化：复用 delegate_tool 的诊断 + OPC Memory 恢复点
│
├── config/                       ← 不变
├── webui/                        ← 不变
└── requirements.txt              ← 移除 multiprocessing 相关依赖
```

**精简统计**：
- 删除 `workflow/fault_handler.py`（delegate_tool 已内置）
- 删除 `workflow/recovery.py` 大部分代码（仅保留 OPC Memory 恢复点逻辑）
- `leader_agent.py` 重构为 `leader_prompt.py`（不再是独立进程，而是 prompt 构建器）
- `dag_executor.py` 简化为调用 `worker_dispatcher.py`
- 总代码量估算：从 ~3000 行降至 ~1500 行

---

### E.7 修正后的关键设计决策记录（追加到附录 C）

| 决策 | 原选择 | 修正选择 | 修正理由 |
|------|--------|---------|---------|
| Worker 派发机制 | AgentTaskDispatcher (multiprocessing) | OPCWorkerDispatcher (复用 delegate_tool) | delegate_tool 已具备并行 batch、超时、心跳、事件流——无需重建 |
| Leader 运行模型 | 未明确（暗示独立进程） | Gateway Agent + pre_gateway_dispatch prompt 增强 | 零额外进程、复用所有基础设施、delegate_tool 原生支持 |
| 进度通知 | 自建 SQLite 轮询 ProgressReport | delegate_tool DelegateEvent + Gateway SSE | 已有机制，零新增代码 |
| 超时管理 | 需绕过 300s 限制 | 无需绕过（300s 仅影响 async 工具，delegate_tool 有独立 600s 超时） | 源码验证表明原分析有误 |
| 中断恢复 | 自建恢复点 + 幂等 | 复用 delegate_tool interrupt + OPC Memory 恢复点 | 减少重复实现 |
| Evaluator 成本 | 每个任务都评估 | 采样评估（SIMPLE 30% / MEDIUM 70% / COMPLEX 100%） | 日成本从 ~$8 降至 ~$1.3 |
