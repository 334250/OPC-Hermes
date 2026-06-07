# OPC-Hermes 产品设计文档

> **版本**: v1.0  
> **日期**: 2026-06-07  
> **仓库**: <https://github.com/334250/OPC-Hermes.git>  
> **定位**: 构建在 Hermes Agent 之上的多 Agent 管理层  
> **原则**: 不修改 Hermes Agent 源码；通过插件、配置、工具注册、Cron 和外部存储完成扩展  

---

## 目录

1. [产品概述](#1-产品概述)
2. [系统架构](#2-系统架构)
3. [Agent 角色体系](#3-agent-角色体系)
4. [多工作流编排](#4-多工作流编排)
5. [工作流看板（Workflow Panel）](#5-工作流看板workflow-panel)
6. [门控共享记忆](#6-门控共享记忆)
7. [复杂度评级与模型路由](#7-复杂度评级与模型路由)
8. [质量评估系统](#8-质量评估系统)
9. [自进化引擎](#9-自进化引擎)
10. [知识管道](#10-知识管道)
11. [修订与反馈闭环](#11-修订与反馈闭环)
12. [WebUI 产品界面](#12-webui-产品界面)
13. [安全护栏](#13-安全护栏)
14. [实施路线图](#14-实施路线图)

---

## 1. 产品概述

### 1.1 OPC-Hermes 是什么

OPC-Hermes（Orchestrated Professional Colleagues）是一个**构建在 Hermes Agent 之上的多 Agent 管理层**。它不替换 Hermes Agent 的核心循环，而是通过注入角色定义、记忆隔离、复杂度路由、质量评估和自进化管道，将单个通用 Agent 升级为一支**可编排、可评估、可进化**的 AI 数字员工团队。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **多 Agent 角色** | 1 个 Leader + 21 个 Worker + 1 个 Evaluator，按专业分工 |
| **DAG 工作流** | 5 种协同模式（Pipeline / Scatter-Gather / Consensus / Hierarchy / Star） |
| **门控记忆** | 3 层物理隔离（Project / Eval / KB），Worker 只读上游 Summary Bridge |
| **复杂度路由** | SIMPLE / MEDIUM / COMPLEX 三级，3 层模型优先级 |
| **质量评估** | 5 维度评分，自动写入 Eval Memory |
| **自进化** | Optimizer 周期扫描 → 生成提案 → 人工审批 → 手动切换 |
| **WebUI** | React 仪表盘，9 个页面，taste-skill 驱动的暗色主题 |
| **零侵入** | 不修改 Hermes Agent 源码，全部通过 Plugin + Hook + Tool + Cron 集成 |

### 1.3 与传统 Agent 框架的差异

```
传统框架:  "帮我画个架构图" → 单一 Agent → 单一模型 → 输出
OPC-Hermes: "帮我画个架构图"
              → Leader Agent 解析意图
              → ComplexityRater 判定 MEDIUM
              → DAG 拆解: 调研Worker → 画图Worker → 审稿Worker
              → Worker 间通过 Summary Bridge 摘要传递（不共享原始上下文）
              → Evaluator 评分 → 写入 Eval Memory
              → Optimizer 周期扫描 → 优化提案 → 人工审批
```

---

## 2. 系统架构

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
│  Agent List     │  Proposal Engine  │  Revision Handler      │
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
└──────────────────────────────────────────────────────────────┘
```

### 2.2 请求生命周期

```
用户在 Telegram 发送: "/opc 帮我做一份 Q2 销售分析 PPT"

0. Gateway 路由:
   → 识别 /opc 前缀 → 路由到 Leader Agent

1. Leader Agent 意图解析:
   → 识别复合任务 → 调用 complexity_rater → MEDIUM
   → 查询 Agent List: 数据分析 ✓  画图 ✓  PPT制作 ✗
   → 自动生成 PPT Worker → 注册到 Agent List

2. Leader 输出计划 → 用户确认:
   ┌────────────────────────────────────────────┐
   │ 📋 任务计划: Q2 销售分析 PPT               │
   │                                            │
   │ 协同模式: Pipeline                          │
   │                                            │
   │ Step 1: 数据分析Worker (MEDIUM)             │
   │   模型: claude-sonnet-4                     │
   │   Skills: [pandas_analysis]                 │
   │   输出: 销售趋势数据 + 洞察                  │
   │                                            │
   │ Step 2: 画图Worker (SIMPLE)                 │
   │   模型: gemini-2.5-flash                    │
   │   Skills: [data_chart]                      │
   │   输出: 3张图表                              │
   │   依赖: Step 1 摘要                         │
   │                                            │
   │ Step 3: PPT制作Worker (MEDIUM) 🆕           │
   │   模型: claude-sonnet-4                     │
   │   Skills: [python_pptx]                     │
   │   输出: .pptx 文件                          │
   │   依赖: Step 1 摘要 + Step 2 产物            │
   │                                            │
   │ [确认执行] [修改计划] [取消]                  │
   └────────────────────────────────────────────┘

3. DAG 执行:
   Step 1 → [TaskProtocol] → 数据分析Worker → [输出 + ProgressReport]
   Step 2 → [SummaryBridge(Step1)] → 画图Worker → [输出 + 3图表]
   Step 3 → [SummaryBridge(Step1,2)] → PPT Worker → [输出 + .pptx]

4. Evaluator 评分（异步）:
   数据分析: quality=0.85, relevance=0.9, completeness=0.8
   画图:     quality=0.75, relevance=0.8, completeness=0.9
   PPT:      quality=0.9, relevance=0.85, completeness=0.88

5. Leader 汇总 → 交付用户

6. Optimizer 周期扫描 Eval Memory → 发现画图Worker质量偏低 → 生成提案
```

---

## 3. Agent 角色体系

### 3.1 三层模型

| 角色类型 | 职责 | 记忆关系 | 实例化 |
|---------|------|---------|--------|
| **Leader Agent** | 任务拆解、Worker 匹配、计划生成、DAG 调度、结果汇总 | 与 Worker 不共享记忆；通过 TaskProtocol + ProgressReport 通信 | Gateway Agent 通过 pre_gateway_dispatch hook 注入 Leader prompt |
| **Worker Agent** | 接收 TaskProtocol，调用 skills 完成子任务 | 与自己的 skills 共享记忆；与其他 Worker 通过 Summary Bridge 桥接 | delegate_tool 的 ThreadPoolExecutor 线程中运行 |
| **Evaluator Agent** | 对 Worker 输入/输出质量打分，写 Eval Memory | 只读 Project Memory，只写 Eval Memory | 独立的 Agent 实例或本地规则评分器 |

### 3.2 Worker 清单（21 个）

#### 通用内容 Worker

| Worker ID | 显示名称 | 模型层 | 核心 Skills |
|-----------|---------|--------|------------|
| `researcher` | 调研 Agent | standard | web_search, paper_fetch |
| `writer` | 撰写 Agent | standard | chapter_writing |
| `illustrator` | 画图 Agent | budget | flowchart_draw, data_chart, draw_io_advanced |
| `ppt_maker` | PPT 制作 | standard | python_pptx |
| `doc_maker` | 文档制作 | standard | python_docx, sphinx_doc, pandoc_convert |
| `formatter` | 排版 Agent | budget | markdown_format |
| `reviewer` | 审稿 Agent | standard | grammar_check, consistency_review |
| `data_analyst` | 数据分析 | standard | pandas_analysis |
| `translator` | 翻译 Agent | budget | translation_engine |
| `browser_agent` | 浏览器 Agent | budget | playwright_browser |
| `email_agent` | 邮件 Agent | budget | email_handler |

#### 软件开发 Worker

| Worker ID | 职责 | 主要输出 |
|-----------|------|----------|
| `product_engineer` | 需求澄清、验收标准、任务拆分 | 需求规格 |
| `software_architect` | 模块边界、接口契约、数据流设计 | 设计文档 |
| `backend_engineer` | API、业务逻辑、数据模型实现 | 代码变更 |
| `frontend_engineer` | UI、状态管理、浏览器验证 | 前端代码 |
| `qa_engineer` | 测试映射、回归验证 | 测试文件 + 结果 |
| `devops_engineer` | CI/CD、部署配置 | 配置变更 |
| `code_reviewer` | 正确性、回归风险、维护性审查 | 问题列表 |
| `security_engineer` | 权限、输入校验、密钥、依赖审查 | 风险列表 |

---

## 4. 多工作流编排

### 4.1 五种协同模式

#### 模式 1：Pipeline（顺序管道）
```
Agent A → Agent B → Agent C
适用: 有明确先后依赖的线性任务
```

#### 模式 2：Scatter-Gather（并行分发 → 汇总）
```
        ┌── Worker A ──┐
任务 ───┼── Worker B ──┼── Leader 汇总
        └── Worker C ──┘
适用: 多角度同时分析
```

#### 模式 3：Consensus（多 Agent 投票）
```
        ┌── 技术 Agent ──┐
任务 ───┼── 产品 Agent ──┼── 加权投票 → 决策
        └── 数据 Agent ──┘
适用: 高风险决策
```

#### 模式 4：Hierarchy（层级委托）
```
      Leader
    ┌────┼────┐
  W-A  W-B  W-C
   │
  Skill1
适用: 超大型任务分层拆解
```

#### 模式 5：Star Delegation（星形委托 + 摘要桥接）—— **核心模式**

```
                      用户
                       │
                  Leader Agent
               ┌───┬───┼───┬───┐
               ▼   ▼   ▼   ▼   ▼
            W-A W-B W-C W-D W-E
               │   │   │   │   │
               └───┴───┼───┴───┘
                       │
                Summary Bridge
            (Worker 间仅通过摘要桥接)
```

**关键特征**:
1. Leader 拥有全局视图，通过 ProgressReport 了解完成度
2. 每个 Worker 独立工作，与自己的 skills 深度耦合
3. Summary Bridge 保证信息传递效率 — Worker 只需知道上游做了什么
4. 修订流程由 Leader 统一管控 — 用户改一句话，Leader 判断需要通知哪些 Worker

### 4.2 DAG 编排器

DAG 编排器（`workflow/dag_executor.py`）负责：
- **拓扑排序**: Kahn 算法，确保依赖顺序
- **并行批次检测**: 将无依赖关系的步骤放入同一批次并发执行
- **循环检测**: DFS 着色检测，在计划生成阶段就阻止循环依赖

```
计划步骤:
  Step 0: researcher (无依赖)        ─┐
  Step 1: data_analyst (依赖 0)       ├─ Batch 0: 并行 [0]
  Step 2: illustrator (依赖 1)       ─┤
  Step 3: ppt_maker (依赖 1,2)    ─┐  ├─ Batch 1: [1]
                                       ├─ Batch 2: [2]
  DAG 调度:                            ├─ Batch 3: [3]
  Batch 0: [researcher]               ─┘
  Batch 1: [data_analyst]
  Batch 2: [illustrator]
  Batch 3: [ppt_maker]
```

### 4.3 故障处理策略

| 状态 | 策略 | 说明 |
|------|------|------|
| `failed` | RETRY（默认） | 重试最多 2 次，间隔 5s |
| `timeout` | RETRY → ABORT | 先重试，超时 3 次后中止 |
| `cancelled` | ABORT | 用户取消，立即中止 |

每个 Worker 执行前写入 `TaskProtocol`，完成后写入 `ProgressReport`。中断后可通过 `opc_get_worker_context` 恢复已完成的步骤。

---

## 5. 工作流看板（Workflow Panel）

### 5.1 设计目标

工作流看板是 OPC-Hermes WebUI 的核心页面，提供**多工作流并行状态的可视化总览**。用户可在单一视图中：
- 查看所有活跃工作流及其进度
- 监控每个 Worker 的实时状态
- 追踪 Summary Bridge 的信息流向
- 快速定位瓶颈和失败步骤
- 管理多个并发任务的优先级

### 5.2 看板布局

```
┌──────────────────────────────────────────────────────────────────────┐
│  工作流看板                                          [新建任务] [刷新] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─ 筛选栏 ──────────────────────────────────────────────────────┐   │
│  │ [全部] [进行中] [已完成] [失败]  │ 🔍 搜索任务...  │ 排序: 最近  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────┐  ┌──────────────────────────┐         │
│  │ 🔄 Q2销售分析PPT          │  │ ✅ API文档生成             │         │
│  │ Pipeline · MEDIUM         │  │ Pipeline · SIMPLE         │         │
│  │ ┌────┐  ┌────┐  ┌────┐   │  │ ┌────┐  ┌────┐           │         │
│  │ │ ✅ │→│ ✅ │→│ 🔄 │   │  │ │ ✅ │→│ ✅ │           │         │
│  │ │数据│  │画图│  │PPT │   │  │ │调研│  │文档│           │         │
│  │ └────┘  └────┘  └────┘   │  │ └────┘  └────┘           │         │
│  │ 2/3 完成 · 已运行 8分钟    │  │ 完成 · 2/2 · 评分 0.85   │         │
│  └──────────────────────────┘  └──────────────────────────┘         │
│                                                                      │
│  ┌──────────────────────────┐  ┌──────────────────────────┐         │
│  │ ❌ 竞品分析报告            │  │ ⏸️ 安全审计（等待审批）    │         │
│  │ Scatter · COMPLEX         │  │ Pipeline · MEDIUM         │         │
│  │ ┌────┐  ┌────┐           │  │ ┌────┐  ┌────┐           │         │
│  │ │ ❌ │  │ ⬜ │           │  │ │ ✅ │  │ ⏸️ │           │         │
│  │ │爬虫│  │汇总│           │  │ │架构│  │安全│           │         │
│  │ └────┘  └────┘           │  │ └────┘  └────┘           │         │
│  │ 1/2 失败 · 爬虫超时       │  │ 等待用户审批安全建议       │         │
│  └──────────────────────────┘  └──────────────────────────┘         │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.3 单任务详情展开

点击任意工作流卡片展开详情面板：

```
┌──────────────────────────────────────────────────────────────────────┐
│  🔄 Q2销售分析PPT · Pipeline · MEDIUM · 创建于 15:30                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─── DAG 可视化 ───────────────────────────────────────────────┐    │
│  │                                                               │    │
│  │   ┌──────────┐      ┌──────────┐      ┌──────────┐          │    │
│  │   │ ✅ 数据分析│ ────→│ ✅ 画图    │ ────→│ 🔄 PPT制作 │          │    │
│  │   │ researcher│ 摘要  │illustrator│ 产物  │ ppt_maker│          │    │
│  │   │ ⭐ 0.85  │      │ ⭐ 0.75  │      │ ─        │          │    │
│  │   │ 用时 3m  │      │ 用时 2m  │      │ 进行中... │          │    │
│  │   └──────────┘      └──────────┘      └──────────┘          │    │
│  │                                                               │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─── Summary Bridge 流向 ───────────────────────────────────────┐   │
│  │                                                               │   │
│  │  数据分析 → 画图: "Q2销售总额增长15%，AWS占32%..."             │   │
│  │  数据分析 → PPT:  "Q2销售总额增长15%，AWS占32%..." + data.json │   │
│  │  画图     → PPT:  "3张图表已生成: chart1.png, chart2.png..."   │   │
│  │                                                               │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─── 操作 ─────────────────────────────────────────────────────┐    │
│  │ [⏸️ 暂停] [⏹ 取消] [📋 查看产物] [📝 提交修订]              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.4 看板状态模型

每个工作流卡片展示以下信息：

| 元素 | 说明 |
|------|------|
| **状态指示器** | 彩色圆点 + 图标（🔄进行中 / ✅已完成 / ❌失败 / ⏸️暂停） |
| **任务标题** | 从 TaskProtocol 提取 |
| **协同模式** | Pipeline / Scatter-Gather / Consensus / Hierarchy / Star |
| **复杂度** | SIMPLE / MEDIUM / COMPLEX + 置信度 |
| **DAG 缩略图** | 简化的步骤节点链（✅/🔄/❌/⬜），每个节点 1-2 字标签 |
| **进度** | N/M 完成 + 已运行时间 |
| **关键指标** | 平均质量分（如果有 Evaluator 评分） |

### 5.5 数据来源

工作流看板的数据来自以下 OPC 模块：

```
工作流看板
    │
    ├─ TaskProtocols  ──→ 任务列表、步骤定义
    │   (Project Memory: task_protocols 表)
    │
    ├─ ProgressReports ──→ 步骤状态、执行时间
    │   (Project Memory: progress_reports 表)
    │
    ├─ SummaryBridge   ──→ Worker 间信息流向
    │   (Project Memory: summary_bridges 表)
    │
    ├─ Evaluations     ──→ 质量评分
    │   (Eval Memory: evaluations 表)
    │
    └─ Agent Registry  ──→ Worker 元数据（名称、图标、模型层）
        (agent_list/defaults.yaml + workers.yaml)
```

### 5.6 实时更新策略

| 策略 | 适用场景 | 实现 |
|------|---------|------|
| **轮询（Polling）** | WebUI 默认 | 每 5 秒 `GET /api/tasks` 获取最新状态 |
| **WebSocket 推送** | 需要实时反馈时 | Phase 6+，基于 Hermes PTY bridge 模式 |
| **手动刷新** | 用户主动触发 | 看板顶部 [刷新] 按钮 |

---

## 6. 门控共享记忆

### 6.1 设计原则

OPC-Hermes 的记忆管理核心思想是**门控（Gated Memory）**——不是所有 Agent 都能看到彼此的记忆。记忆共享规则不硬编码，由 Leader Agent 在每个工作流的计划阶段按需定义。

### 6.2 默认门控规则

```
┌────────────────────────┬──────────────────────────────────────┐
│ 关系                   │ 默认记忆共享模式                       │
├────────────────────────┼──────────────────────────────────────┤
│ Leader ↔ Worker        │ ❌ 不共享记忆                         │
│                        │ 仅通过 TaskProtocol + ProgressReport  │
├────────────────────────┼──────────────────────────────────────┤
│ Worker ↔ 其 Skills     │ ✅ 完全串联，共享同一记忆空间           │
├────────────────────────┼──────────────────────────────────────┤
│ Worker ↔ Worker        │ ⚠️ 按需配置                           │
│                        │ 选项 A: 摘要桥接（默认）— 只传精简摘要  │
│                        │ 选项 B: 全文共享 — 可读完整上下文       │
│                        │ 选项 C: 完全隔离 — 不交换任何信息       │
│                        │ 选项 D: 单向提示 — 单向发送记忆提示     │
├────────────────────────┼──────────────────────────────────────┤
│ 用户 → Leader          │ 修改意见通过 Leader 分发                │
│                        │ Leader 不公开用户原始消息给 Worker      │
└────────────────────────┴──────────────────────────────────────┘
```

### 6.3 三层物理存储

```
┌─────────────────────────────────────────────────────┐
│  Project Memory (project.db) — SQLite + WAL          │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────┐  │
│  │ Leader Task   │ │ Worker       │ │ Summary      │  │
│  │ Memory        │ │ Context      │ │ Bridge       │  │
│  │              │ │              │ │              │  │
│  │ 谁写: Leader  │ │ 谁写: Worker │ │ 谁写: Worker │  │
│  │ 谁读: Leader  │ │ 谁读: Worker │ │ 谁读: 所有人  │  │
│  └──────────────┘ └──────────────┘ └─────────────┘  │
├─────────────────────────────────────────────────────┤
│  Eval Memory (eval.db) — SQLite + WAL               │
│  谁写: Evaluator  谁读: Evaluator + Optimizer       │
│  存储: 评分结果、输入/输出快照、优化建议              │
├─────────────────────────────────────────────────────┤
│  Knowledge Base (kb.db) — SQLite + ChromaDB          │
│  谁写: Knowledge Pipeline  谁读: 所有 Agent（只读）   │
│  存储: 结构化知识、模板、方法论、工具评测              │
└─────────────────────────────────────────────────────┘
```

### 6.4 记忆数据流

以"技术白皮书"为例：

```
时间线 →

1. Leader → Worker A（调研）:
   TaskProtocol {子任务: "调研微服务最佳实践", 格式: Markdown}
   Worker A 写入: Worker Context A（与 skills 共享）

2. Worker A 完成 → 写入 Summary Bridge:
   {来源: Worker A, 摘要: "微服务3大趋势: Service Mesh, eBPF, WASM...",
    目标: [Worker B, Worker C]}

3. Worker B（撰写）读取 Summary Bridge:
   opc_get_upstream_summaries("task-001", "writer")
   → 返回 Worker A 的摘要（不包含 raw 数据）

4. Evaluator 读取 Worker B 的 TaskProtocol + 输出:
   opc_eval_capture_snapshot("task-001", "writer")
   → 评分 → write_evaluation() → Eval Memory（不写 Project Memory）
```

---

## 7. 复杂度评级与模型路由

### 7.1 复杂度评级

| 级别 | 特征 | 模型层 | 需要审批 | 示例 |
|------|------|--------|---------|------|
| **SIMPLE** | 单步、单工具、无需协调 | budget | 否 | 翻译、摘要、格式化 |
| **MEDIUM** | 2-4 步、多工具、中等协调 | standard | 是 | 项目周报、功能 PPT |
| **COMPLEX** | 5+ 步、并行 Worker、跨域 | premium | 是 | Q2 分析报告、技术白皮书 |

### 7.2 三层模型优先级

```
Layer 1: 用户配置覆盖           ← 最高优先级
    ↓ 未设置
Layer 2: Leader 推荐模型
    ↓ 未指定
Layer 3: 自动路由（复杂度 + 能力矩阵）
    ↓ 无匹配
Fallback: claude-sonnet-4
```

### 7.3 能力兼容性校验

| Model | Vision | Tool Calling | Context | 适用复杂度 |
|-------|--------|-------------|---------|-----------|
| claude-sonnet-4 | ✅ | ✅ | 200K | MEDIUM / COMPLEX |
| gpt-4o | ✅ | ✅ | 128K | COMPLEX |
| gpt-4o-mini | ✅ | ✅ | 128K | SIMPLE |
| gemini-2.5-flash | ✅ | ✅ | 1M | SIMPLE / MEDIUM |
| deepseek-v3 | ❌ | ✅ | 64K | MEDIUM |
| minicpmv4.6 | ✅ | ❌ | 8K | SIMPLE |

---

## 8. 质量评估系统

### 8.1 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| **quality** | 1.0 | 输出整体正确、清晰、结构良好 |
| **relevance** | 1.0 | 与任务目标匹配度 |
| **completeness** | 1.0 | 覆盖所有要求（文件、测试、产物） |
| **efficiency** | 1.0 | 工具调用和成本合理 |
| **leader_decomposition** | 0.5 | Leader 拆解质量（仅 Leader） |

### 8.2 评分方式

OPC-Hermes 提供两种评分方式：

| 方式 | 说明 | 适用场景 |
|------|------|---------|
| **LocalEvaluator（规则引擎）** | 基于启发式规则（输出长度、结构、关键词覆盖率、chars-per-call 比率） | Phase 3+ 默认，零成本 |
| **LLM Evaluator** | 通过 Hermes Agent 实例用 LLM 评分 | Phase 4+，精度更高 |

### 8.3 评估闭环

```
Worker 完成
    │
    ├─ status=completed → LocalEvaluator.evaluate_and_write()
    │   ├─ 5 维度评分
    │   ├─ write_evaluation() → Eval Memory
    │   └─ update_score() → Agent Registry
    │
    └─ status=failed → 全维度 0.0 + 错误记录
```

---

## 9. 自进化引擎

### 9.1 优化周期

```
Eval Memory
    │
    ▼ (每 1h Cron Job)
Optimizer.scan()
    │
    ├─ 遍历所有 Worker，读取最近 30 天评估数据
    ├─ 至少 5 条评估才分析
    ├─ 计算 avg_quality
    │
    ├─ 低于阈值 → 生成 model_switch 提案
    ├─ budget 层且 <0.5 → 生成 tier_upgrade 提案
    │
    ├─ 去重（30 天窗口）
    └─ 持久化 JSON → proposals/
        │
        ▼
    WebUI Proposals 页面展示
        │
        ├─ [Approve] → 状态: approved → 人工切换 → applied
        ├─ [Reject]  → 状态: rejected
        └─ [Later]   → 状态: pending，下次仍可见
```

### 9.2 回滚检测

```
check_for_regression(worker_id, applied_since)
    │
    ├─ 对比切换前后 10 次评估
    ├─ 质量下降 ≥ 0.2 → 生成回滚警告
    └─ 质量稳定 → 无操作
```

---

## 10. 知识管道

### 10.1 双通道

| 通道 | 输入 | 处理 | 输出 |
|------|------|------|------|
| **用户上传** | .md / .txt / .csv / .json / .yaml / .html | 文件解析 → 结构化提取 | KB SQLite |
| **爬虫** | 配置的 URL 列表 | web_extract → 去重 → 质量评分 | KB SQLite |

### 10.2 使用方式

```
Worker A: 完成任务前查询 KB
    → kb_search("微服务架构最佳实践")
    → 返回相关条目（标题 + 摘要）

Knowledge Pipeline: 用户上传参考文档
    → ingest_file("whitepaper.md", tags=["微服务", "架构"])
    → 写入 KB，所有 Worker 可读
```

---

## 11. 修订与反馈闭环

### 11.1 三级修订范围

| 范围 | 关键词 | 行为 |
|------|--------|------|
| **LOCAL** | fix/change/调整/修改 | 匹配受影响 Worker → 最小改动 |
| **STRUCTURAL** | reorganize/add/remove/重组/添加 | 结构变更 → 重排内容 |
| **GLOBAL** | rewrite/redo/completely/重写/完全 | 全部重做 |

### 11.2 修订流程

```
用户: "只把 PPT 第 4 页柱状图换成折线图"

Revision Handler:
    → scope: LOCAL
    → affected_workers: [illustrator, ppt_maker]
    → 不会重跑 researcher 和 data_analyst

受影响 Worker 收到修订 prompt:
    "## Original Task\n...\n## Revision Request\n只把柱状图换成折线图\n\nMake ONLY the requested change."
```

---

## 12. WebUI 产品界面

### 12.1 设计理念

OPC-Hermes WebUI 采用 **taste-skill 驱动的暗色仪表盘设计**，专为开发者和管理员打造：

```
设计 DIELS:
  VARIANCE: 5  (结构化，数据清晰)
  MOTION:   4  (微妙过渡，不喧宾夺主)
  DENSITY:  6  (仪表盘密度，留白舒适)

调色板:
  Background:  #0a0a0f (深空黑)
  Surface:     #14141f (卡片背景)
  Surface 2:   #1e1e2e (悬停/激活)
  Border:      #2a2a3a (细分隔线)
  Text:        #e4e4ec (主文本)
  Text 2:      #8888a0 (次要文本)
  Accent:      #7c3aed (OPC 紫)

技术栈:
  React 18 + TypeScript + Vite
  Tailwind CSS (自定义 OPC 调色板)
  FastAPI + Uvicorn (后端)
```

### 12.2 页面清单

| 页面 | 路由 | 功能 |
|------|------|------|
| **Dashboard** | `/` | 5 统计卡片 + 质量趋势图 |
| **Agent List** | `/agents` | 角色过滤 + 搜索 + 卡片网格 |
| **Agent Detail** | `/agents/:id` | 技能标签 + 评估历史 + 分数趋势 |
| **Workflow Panel** | `/workflows` | 多工作流看板（卡片 + DAG 缩略图） |
| **Task List** | `/tasks` | 任务发现 + 状态筛选 |
| **Task Detail** | `/tasks/:id` | DAG 可视化 + 步骤详情 + Summary Bridge 流向 |
| **Memory Browser** | `/memory` | 分区浏览 (Project/Eval/KB) |
| **Artifact Viewer** | `/artifacts` | 版本化产物浏览 |
| **Proposal Review** | `/proposals` | 优化提案审批流 |
| **Config** | `/config` | JSON 编辑器 + 保存 |

### 12.3 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard` | GET | 聚合统计 + 质量趋势 |
| `/api/agents` | GET | Worker 列表 |
| `/api/agents/:id` | GET | Worker 详情 + 技能 + 评估 |
| `/api/workflows` | GET | 活跃工作流列表（看板数据） |
| `/api/tasks` | GET | 任务列表 |
| `/api/tasks/:id` | GET | DAG 数据 + 步骤详情 |
| `/api/memory/:partition` | GET | 记忆分区浏览 |
| `/api/knowledge/search` | GET | KB 搜索 |
| `/api/artifacts` | GET | 产物浏览 |
| `/api/proposals` | GET | 提案列表 |
| `/api/proposals/:id/approve` | POST | 审批提案 |
| `/api/proposals/:id/reject` | POST | 拒绝提案 |
| `/api/config` | GET/POST | 配置读写 |

---

## 13. 安全护栏

### 13.1 权限边界

| 主体 | 可写 | 只读 | 不可访问 |
|------|------|------|---------|
| **Leader** | Project Memory (Leader Task) | Summary Bridge, KB, Eval | Worker Context |
| **Worker** | Project Memory (Worker Context), Summary Bridge | KB, 上游 Summary Bridge | Eval, 其他 Worker Context |
| **Evaluator** | Eval Memory | Project Memory, KB | — |
| **Optimizer** | Proposals | Eval Memory | Project Memory, KB |
| **Knowledge Pipeline** | KB | — | Project, Eval |

### 13.2 注入防护

```python
# Worker prompt 过滤
guard_worker_prompt(prompt)
  → 过滤: </?system>, </?assistant>, <|im_start|>, <|im_end|>, 角色标签

# Summary Bridge 来源标记
guard_summary_bridge(summary, source_worker_id)
  → 包装: "[UPSTREAM SUMMARY — source: researcher]\n\n...[/UPSTREAM SUMMARY]"
```

### 13.3 密钥保护

- Config API 返回前脱敏（`_redact_sensitive`）
- 日志不输出密钥（`redact_secrets` + `scan_for_secrets`）
- 提案中不包含配置密钥

---

## 14. 实施路线图

### 当前状态（v0.15.1 对应）

| Phase | 名称 | 状态 |
|-------|------|------|
| 0 | 工程基线 | ✅ 完成 |
| 1 | 插件接入与 Leader 路由 | ✅ 完成 |
| 2 | Worker Dispatch 与 DAG 执行 | ✅ 完成 |
| 3 | 记忆与评估闭环 | ✅ 完成 |
| 4 | 优化与知识库 | ✅ 完成 |
| 5 | WebUI | ✅ 完成 |
| 6 | 生产硬化 | ✅ 完成 |

### 下一步

| 任务 | 优先级 |
|------|--------|
| 工作流看板前端页面 (`WorkflowPanel.tsx`) | 高 |
| DAG 交互式可视化 (React Flow) | 高 |
| WebUI 身份认证 | 中 |
| ChromaDB 向量索引 | 中 |
| LLM Evaluator（替代规则评分） | 低 |
| 多工作流并发调度优化 | 低 |
| 完整 PDF/DOCX 解析 | 低 |

---

> **核心原则回顾**: OPC-Hermes 始终遵循"不修改 Hermes Agent 源码"的原则，所有功能通过 Plugin、Hook、Tool 注册、Cron API 和独立存储实现。这是一个**管理层**，不是替代品。
