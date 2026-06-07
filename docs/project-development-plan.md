# OPC-Hermes 项目开发计划

> 版本：v0.1  
> 日期：2026-06-07  
> 范围：`opc_hermes/` 插件包、`docs/` 设计文档、与 `hermes-agent/` 的非侵入式集成  
> 原则：不修改 Hermes Agent 既有源码；通过插件、配置、工具注册、Cron 和外部存储完成扩展。

## 1. 项目目标

OPC-Hermes 的目标是在 Hermes Agent 运行时之上实现一个可编排、可评估、可演进的多智能体管理层。系统应支持 Leader Agent 接收用户需求，拆解任务，选择 Worker Agent，执行 DAG 工作流，隔离记忆，评估质量，并基于评估数据生成优化建议。

### 1.1 核心能力目标

1. Leader Agent 能够识别任务意图、评估复杂度、生成可确认的执行计划。
2. Worker Agent 能够按角色执行专业任务，并通过 Summary Bridge 向下游传递受控摘要。
3. Gated Memory 能够隔离 Project Memory、Eval Memory、Knowledge Base。
4. DAG Executor 能够支持串行、并行、Pipeline、Star Delegation 等协同模式。
5. Evaluator Agent 能够对 Worker 输入输出质量打分，并写入 Eval Memory。
6. Optimizer 能够扫描评估结果，提出模型、Prompt、Skill、Worker 调整建议。
7. CLI/WebUI 能够展示 Agent List、任务状态、产物、评估分数和优化提案。
8. 系统全程保持可测试、可回滚、可审计。

### 1.2 非目标

1. 不替换 Hermes Agent 的核心循环。
2. 不直接修改 `hermes-agent/` 既有源码。
3. 不让 Optimizer 自动改写生产配置；所有优化建议必须人工审批。
4. 不在第一阶段实现完整 WebUI，优先保证核心运行链路。
5. 不把所有任务都重流程化；简单任务应保持低成本、低延迟。

## 2. 当前状态评估

### 2.1 已具备的基础

| 模块 | 当前状态 | 说明 |
|------|----------|------|
| `plugin.py` | 框架存在 | 可注册复杂度工具、钩子、CLI、Cron，但多处仍是 stub |
| `agent_list/registry.py` | 可用 | 支持默认 Worker/Skill 加载、查询、注册、评分更新 |
| `agent_list/defaults.yaml` | 已扩展 | 已包含通用内容 Agent 和开发类 Agent |
| `leader_prompt.py` | 可用 | 可构建 Leader prompt，并注入 Agent List、复杂度规则、开发 workflow |
| `complexity_rater.py` | 基础可用 | 规则启发式已实现，LLM 评级待实现 |
| `memory_layer/gated_memory.py` | 基础可用 | SQLite 三分区 schema 和核心读写 API 已存在 |
| `memory_layer/tools.py` | 基础可用 | 已有 OPC 记忆工具注册逻辑 |
| `workflow/dag_executor.py` | 基础可用 | 拓扑排序和并行分组逻辑已存在 |
| `workflow/artifact_manager.py` | 基础可用 | 支持产物版本化存储 |
| `worker_dispatcher.py` | stub | 当前模拟执行，未真正调用 Hermes `delegate_task` |
| `evaluator.py` | 部分可用 | 工具 handler 已有，Evaluator 实例化/触发链路待实现 |
| `optimizer.py` | 部分可用 | 提案生成基础逻辑已有，Cron/WebUI 接入待实现 |
| `knowledge_pipeline.py` | stub 较多 | 上传、URL、爬虫、解析、向量索引待实现 |
| `revision_handler.py` | 基础启发式 | 反馈路由逻辑需接入真实任务上下文 |
| `cli_skin/commands.py` | 部分可用 | list/status/config 还需连接实际存储 |
| `webui/` | 空壳 | 需要后续设计和实现 |
| 测试 | 很少 | 已有默认注册表一致性测试，整体测试体系待建立 |

### 2.2 已发现的即时问题

| 问题 | 影响 | 处理策略 |
|------|------|----------|
| 多处 Phase stub | 无法完成真实多 Agent 执行 | Phase 1-3 分阶段补齐 |
| `worker_dispatcher.py` 未调用 `delegate_task` | Worker 不会真实执行 | Phase 2 核心任务 |
| 插件钩子未注入 Leader Prompt | Gateway 消息无法自动进入 OPC 流程 | Phase 1 核心任务 |
| Evaluator 未接入 Worker 完成事件 | 质量评估无法自动产生 | Phase 3 核心任务 |
| Cron 未注册 Optimizer | 优化提案无法周期生成 | Phase 4 任务 |
| WebUI 缺失 | 缺少可视化管理面 | Phase 5 任务 |
| 测试覆盖不足 | 重构和集成风险高 | 每阶段设置质量门禁 |

## 3. 总体开发策略

开发按“先可运行，再可评估，再可优化，再可视化”的顺序推进。

1. Phase 0：稳定基线，确保包可导入、配置可加载、测试能跑。
2. Phase 1：插件与 Leader 路由接通，用户请求能进入 OPC 计划流程。
3. Phase 2：真实 Worker Dispatch 接通，DAG 能执行并产生产物和记忆。
4. Phase 3：Evaluator 接入，形成质量评分闭环。
5. Phase 4：Optimizer、Knowledge Pipeline、Revision Handler 完成数据闭环。
6. Phase 5：CLI/WebUI 管理面落地。
7. Phase 6：生产化、安全、性能、文档和发布。

建议周期：14 周完成 MVP 到可用 Beta。若单人开发，可按 18-22 周估算。

## 4. 里程碑计划

| 阶段 | 周期 | 目标 | 退出标准 |
|------|------|------|----------|
| Phase 0 | 第 1 周 | 工程基线稳定 | 包可导入，核心配置一致性测试通过 |
| Phase 1 | 第 2-3 周 | Leader 接入 Hermes 插件链路 | `/opc` 或配置触发可生成计划 |
| Phase 2 | 第 4-6 周 | Worker DAG 真实执行 | 至少 3 Worker Pipeline 可跑通 |
| Phase 3 | 第 7-8 周 | 记忆与评估闭环 | Worker 输出自动写 Project Memory，评分写 Eval Memory |
| Phase 3b | 第 8-9 周 | 管理面板后端 | 智能体组/流水线模板/模型管理器 CRUD + 29 API 端点 |
| Phase 4 | 第 9-10 周 | 优化与知识库基础版 | 可生成优化提案，可检索 KB |
| Phase 5 | 第 11-12 周 | CLI/WebUI 管理面 | 可查看 Agent、任务、产物、评分、提案 |
| Phase 6 | 第 13-14 周 | Beta 硬化 | 安全、性能、端到端测试、文档齐备 |

## 5. Phase 0：工程基线稳定

### 5.1 目标

建立可靠的开发和测试基线，清除会阻断导入、测试、打包的基础问题。

### 5.2 任务清单

| ID | 任务 | 涉及文件 | 验收标准 |
|----|------|----------|----------|
| P0-1 | 修复所有模块导入错误 | `opc_hermes/*.py` | `python3` 可导入核心模块 |
| P0-2 | 建立 pytest 配置 | `opc_hermes/pyproject.toml` 或根配置 | `python3 -m pytest opc_hermes/tests` 可运行 |
| P0-3 | 扩展注册表一致性测试 | `opc_hermes/tests/` | 校验 Worker/Skill/template/toolset/workflow 引用 |
| P0-4 | 增加配置 YAML 解析测试 | `config/*.yaml` | 所有 YAML 可解析且关键字段存在 |
| P0-5 | 增加包数据测试 | `pyproject.toml` | 默认 YAML、skills、templates 被打包 |
| P0-6 | 增加开发环境说明 | `README.md` 或 docs | 新开发者能安装依赖并跑测试 |
| P0-7 | 清理缓存和生成物策略 | `.gitignore` | `__pycache__`、DB、artifacts 不进入版本库 |

### 5.3 质量门禁

1. `python3 -m compileall -q opc_hermes` 通过。
2. 核心模块导入抽样通过：`plugin`、`evaluator`、`optimizer`、`worker_dispatcher`、`gated_memory`。
3. 默认注册表加载后至少包含 Leader、Evaluator 和开发类 Worker。
4. 不依赖真实 Hermes 环境的测试全部通过。

## 6. Phase 1：插件接入与 Leader 路由

### 6.1 目标

让 OPC-Hermes 能通过 Hermes 插件系统参与消息处理，并在合适时机注入 Leader prompt。

### 6.2 功能范围

1. 插件注册 OPC toolsets。
2. 插件注册 memory/evaluator 工具。
3. 支持 `/opc` 前缀触发 Leader 模式。
4. 支持配置项控制是否默认启用 Leader。
5. Leader 能读取 Agent List 摘要和开发 workflow hints。
6. Leader 能输出标准计划 JSON 和用户可读计划。

### 6.3 任务清单

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P1-1 | 设计 OPC 配置加载器 | 读取 `~/.hermes/opc/config.yaml`，提供默认值 | 缺配置时可运行，有配置时覆盖默认 |
| P1-2 | 完成 toolset 注册 | 将 `OPC_TOOLSETS` 正式注册到 Hermes registry | `hermes tools` 可见 OPC toolsets |
| P1-3 | 完成 `_register_evaluator_tools` | 调用 `evaluator.register_all(ctx)` | evaluator 工具可注册 |
| P1-4 | 实现 `pre_gateway_dispatch` | 检测 `/opc`、任务复杂度、用户配置 | 非 OPC 消息 passthrough |
| P1-5 | 实现 `pre_llm_call` prompt 注入 | 针对 Leader session 注入完整 prompt | 注入内容包含 Agent List |
| P1-6 | 定义计划 JSON schema | Leader 输出结构化 plan | schema 可校验 |
| P1-7 | 增加计划解析器 | 从 Leader 输出提取可执行 plan | 非法计划给出明确错误 |
| P1-8 | 增加计划确认状态 | MEDIUM/COMPLEX 任务等待用户确认 | 未确认不执行 Worker |
| P1-9 | 增加单元测试 | hook、prompt、plan schema | 测试覆盖正常/异常路径 |

### 6.4 Leader Plan Schema 草案

```json
{
  "task_id": "opc-20260607-001",
  "title": "开发某功能",
  "complexity": {"level": "MEDIUM", "confidence": 0.75},
  "mode": "pipeline",
  "requires_user_approval": true,
  "steps": [
    {
      "index": 0,
      "worker_id": "software_architect",
      "prompt": "设计模块边界和接口契约",
      "upstream": [],
      "expected_output_format": "Markdown design summary",
      "requires_vision": false,
      "requires_tool_calling": true,
      "model_override": null,
      "timeout_seconds": 600
    }
  ],
  "memory_rules": [
    {
      "source_step": 0,
      "target_steps": [1, 2],
      "summary_policy": "key_findings_and_artifacts_only"
    }
  ],
  "acceptance_criteria": ["测试通过", "输出产物路径"]
}
```

### 6.5 退出标准

1. 用户输入 `/opc 帮我做一个 Q2 销售分析 PPT` 能生成 Pipeline 计划。
2. 用户输入 `/opc 开发一个后端 API 并补测试` 能匹配 `software_architect -> backend_engineer -> qa_engineer -> code_reviewer`。
3. MEDIUM/COMPLEX 计划在确认前不会调用 `dispatch_workers`。
4. Leader prompt 中明确包含开发 workflow hints。

## 7. Phase 2：Worker Dispatch 与 DAG 执行

### 7.1 目标

将 `worker_dispatcher.py` 从 stub 变成真实执行器，复用 Hermes `delegate_task`，支持 DAG、并行批处理、记忆注入和结果聚合。

### 7.2 关键设计

1. Leader 产出 plan。
2. Dispatcher 校验 plan。
3. Dispatcher 为每个 step 写入 `TaskProtocol`。
4. Dispatcher 按 DAG parallel group 执行。
5. 每个 Worker 的 prompt 只注入其上游 SummaryBridge。
6. Worker 输出后写 progress report、summary bridge、artifact metadata。
7. Dispatcher 返回结构化执行结果。

### 7.3 任务清单

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P2-1 | 实现 plan validator | 校验 step index、worker_id、upstream、mode | 非法 plan 拒绝执行 |
| P2-2 | 接入 `find_parallel_groups` | 按阶段批量执行 | 同阶段无依赖任务可并行 |
| P2-3 | 实现 Worker prompt render | 从 `prompts.yaml` 渲染模板 | 上游摘要正确注入 |
| P2-4 | 写入 TaskProtocol | 每个 step 执行前保存协议 | Worker 可恢复上下文 |
| P2-5 | 接入 Hermes `delegate_task` | 复用已有 delegate 工具，不自建进程池 | Worker 真实执行 |
| P2-6 | 实现 batch delegate | 并行 group 调用 batch 模式 | 并行分支能一起调度 |
| P2-7 | 收集 Worker 结果 | 标准化 completed/failed/timeout | 结果结构稳定 |
| P2-8 | 写 SummaryBridge | 从 Worker 输出提取摘要、key findings、artifacts | 下游只读摘要 |
| P2-9 | 接入 ArtifactManager | 保存文件产物和 metadata | 产物可按 task/worker/version 查询 |
| P2-10 | 实现失败策略 | retry、skip、abort、ask_user | 失败不会导致状态丢失 |
| P2-11 | 添加恢复能力 | 根据 TaskProtocol/progress 跳过已完成 step | 中断后可恢复 |
| P2-12 | 增加集成测试 | fake delegate + memory tmpdir | 3-step pipeline 可跑通 |

### 7.4 Worker 执行状态模型

| 状态 | 含义 | 后续动作 |
|------|------|----------|
| `pending` | 已生成计划，尚未执行 | 等待依赖或用户确认 |
| `running` | 正在执行 | 记录 heartbeat/progress |
| `completed` | 成功产出 | 写 SummaryBridge，触发 Evaluator |
| `failed` | 执行失败 | 按策略 retry/abort |
| `timeout` | 超时 | 可重试或转人工 |
| `skipped` | 因上游失败或计划修改跳过 | 记录原因 |
| `cancelled` | 用户取消 | 停止后续 step |

### 7.5 退出标准

1. `data_analyst -> illustrator -> ppt_maker` 示例可真实调用 Worker。
2. `backend_engineer -> qa_engineer -> code_reviewer` 示例可真实调用 Worker。
3. 每个 step 都能在 Project Memory 找到 TaskProtocol 和 ProgressReport。
4. 下游 Worker 看不到上游原始完整上下文，只能看到 SummaryBridge。
5. 失败 step 的错误被保存并可展示。

## 8. Phase 3：记忆、评估与质量闭环

### 8.1 目标

Worker 执行完成后自动触发 Evaluator，对 Worker 产出进行评分，写入 Eval Memory，并回写 Agent Registry 的质量统计。

### 8.2 任务清单

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P3-1 | 完成 memory tools 端到端测试 | `opc_save_context` 等工具真实写 SQLite | 工具 handler 可独立测试 |
| P3-2 | 定义 evaluator trigger | Worker completed 后触发 | 成功 Worker 自动排队评估 |
| P3-3 | 实现 Evaluator spawn | 作为普通 Hermes Agent 或本地评分器运行 | 可用真实/假模型测试 |
| P3-4 | 完善 snapshot 内容 | 包含 task protocol、progress、artifacts、upstream summaries | 评估输入完整 |
| P3-5 | 实现 score rubric v1 | 质量、相关性、完整性、效率、Leader 拆解 | 分数可解释 |
| P3-6 | 写 Eval Memory | 评分记录入库 | 可按 task/worker 查询 |
| P3-7 | 更新 Agent Registry score | 质量均值或加权分 | Agent List 展示质量 |
| P3-8 | 增加评估失败隔离 | Evaluator 失败不影响主任务交付 | 只记录 eval_failed |
| P3-9 | 增加测试 | fake evaluator + tmp memory | 完整评估闭环通过 |

### 8.3 评分标准 v1

| 维度 | 分数含义 | 低分信号 |
|------|----------|----------|
| `quality` | 输出整体正确、清晰、结构良好 | 输出混乱、明显错误、不可用 |
| `relevance` | 与任务目标匹配 | 答非所问、遗漏核心目标 |
| `completeness` | 覆盖所有要求 | 缺少文件、缺少测试、缺少产物 |
| `efficiency` | 工具调用和成本合理 | 过度调用、未调用必要工具 |
| `leader_decomposition` | Leader 拆解合理 | Worker 选择错误、依赖不合理 |

### 8.4 退出标准

1. Worker 完成后 1 个 Evaluator 任务自动产生。
2. Eval Memory 中可查到每个 Worker 的评分。
3. Agent Registry 中 worker quality_score 有更新。
4. Evaluator 无权写 Project Memory。

## 9. Phase 3b：管理面板后端 — 智能体组 + 流水线模板 + 模型管理器

### 9.1 目标

实现产品设计文档 §3.5（智能体管理面板）、§3.6（模型管理面板）、§5（工作流看板详情面板）要求的后端数据模型和 REST API。

### 9.2 任务清单

#### 智能体组与流水线模板

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P3b-1 | 实现 AgentGroup 数据模型 | `agent_list/` 新增 `groups.yaml` + `AgentGroup` dataclass + CRUD 方法 | 可通过 API 创建/编辑/删除分组 |
| P3b-2 | 实现 PipelineTemplate 数据模型 | 新建 `pipeline_manager.py` + `pipelines/templates.yaml` | 模板可保存、编辑、按计划执行 |
| P3b-3 | 实现 Agent CRUD API 端点 | POST/PUT/DELETE agents | 可通过 WebUI 增删改智能体 |
| P3b-4 | 实现 Agent Group API 端点 | GET/POST/PUT/DELETE groups | 分组 CRUD 可用 |
| P3b-5 | 实现 Pipeline API 端点 | GET/POST/PUT/DELETE pipelines | 模板管理可用 |

#### 模型管理器

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P3b-6 | 实现 ModelDef / ModelGroup / ModelProvider 数据模型 | 新建 `model_manager.py` + `models/` 目录 | 模型数据可持久化到 YAML |
| P3b-7 | 实现 Model CRUD API 端点 | GET/POST/PUT/DELETE models | 模型库可管理 |
| P3b-8 | 实现 Model Group API 端点 | GET/POST/PUT/DELETE model groups | 分组 CRUD 可用 |
| P3b-9 | 实现 Provider API 端点 | GET/POST providers | 供应商管理可用 |
| P3b-10 | 实现模型连接验证 | POST /models/validate/:id | 测试 API 调用验证端点 |

#### 工作流详情面板

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P3b-11 | 实现 `/api/tasks/{id}/agents` | 返回每个 Worker 完整状态 + 上下游 | 详情面板 Tab 2 数据可用 |
| P3b-12 | 实现 `/api/tasks/{id}/memory-strategy` | 返回 SummaryBridge + 门控规则 | 详情面板 Tab 3 数据可用 |

#### 测试

| ID | 任务 | 验收标准 |
|----|------|----------|
| P3b-13 | Agent Group 集成测试 | CRUD + 成员管理 |
| P3b-14 | Pipeline Template 集成测试 | 模板 CRUD + 执行 |
| P3b-15 | Model Manager 集成测试 | 模型 CRUD + 分组 + 供应商 + 验证 |

### 9.3 退出标准

1. 29 个设计文档要求的 API 端点全部实现。
2. 智能体组、流水线模板、模型管理器数据可 YAML 持久化。
3. 工作流详情面板 4 个 Tab 的后端数据全部就绪。
4. 所有新增端点有集成测试覆盖。

---

## 10. Phase 5：Optimizer、Knowledge Pipeline、Revision Handler

### 9.1 Optimizer

#### 任务清单

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P4-1 | 完善 proposal schema | 支持 model/prompt/skill/tool/worker 类型 | JSON schema 固定 |
| P4-2 | 实现重复提案去重 | 同一 worker 同一问题不重复刷屏 | 30 天窗口去重 |
| P4-3 | 增加趋势分析 | 最近 N 次 vs 历史均值 | 能识别质量下降 |
| P4-4 | 增加成本/延迟指标 | 结合 tool count、duration、model source | 支持成本优化 |
| P4-5 | 接入 Cron | 注册 `opc-optimizer-scan` | 周期运行 |
| P4-6 | 实现审批状态流 | pending/approved/rejected/applied/rolled_back | 状态可持久化 |
| P4-7 | 实现回滚建议 | 质量下降后生成 rollback proposal | 不自动改配置 |

### 9.2 Knowledge Pipeline

#### 任务清单

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P4-8 | 实现文档上传解析 | md/txt/csv/json 优先，pdf/docx 后续 | 能写 KB |
| P4-9 | 实现 URL ingestion | 复用 Hermes web_extract | URL 内容可入库 |
| P4-10 | 实现 KB 查询工具 | 按 Agent/Tag/关键词查询 | Worker 可读 KB 摘要 |
| P4-11 | 增加向量索引选项 | ChromaDB 可选依赖 | 未安装时降级 LIKE |
| P4-12 | 实现质量评分 | 来源、长度、重复、更新时间 | 低质内容不默认注入 |
| P4-13 | 实现 per-agent KB routing | 不同 Worker 看到相关知识 | 避免全量污染上下文 |

### 9.3 Revision Handler

#### 任务清单

| ID | 任务 | 说明 | 验收标准 |
|----|------|------|----------|
| P4-14 | 完善反馈分类 | 局部修改/结构修改/全文重做/新增需求 | 分类稳定 |
| P4-15 | 映射受影响 Worker | 根据 artifact、step、summary 找 Worker | 不重跑无关分支 |
| P4-16 | 生成 revision plan | 新 task 或原 task 新 version | 可追踪版本 |
| P4-17 | 更新 Artifact version | 修订产物生成 v002+ | latest 指向最新 |
| P4-18 | 增加用户确认 | 大范围重做需确认 | 避免误重跑 |

### 9.4 退出标准

1. Optimizer 能从 Eval Memory 生成至少一种提案。
2. Knowledge Base 能写入、查询、按 Agent 过滤。
3. 用户反馈“只改第 3 页图表”能路由到相关 Worker，而非重跑全流程。

## 11. Phase 6：CLI 与 WebUI

### 10.1 CLI

优先实现 CLI，因为它成本低、适合调试、能服务 WebUI 之前的开发。

| ID | 命令 | 功能 | 验收标准 |
|----|------|------|----------|
| P5-1 | `hermes opc list agents` | 查看 Worker 列表 | 显示 id、role、score、skills |
| P5-2 | `hermes opc list skills` | 查看 Skill 列表 | 显示 owner、tags |
| P5-3 | `hermes opc status` | 查看活跃任务 | 显示 task、step、status |
| P5-4 | `hermes opc status <task_id>` | 查看单任务详情 | 显示 DAG、进度、产物 |
| P5-5 | `hermes opc proposals` | 查看优化提案 | 可按状态过滤 |
| P5-6 | `hermes opc approve/reject` | 审批提案 | 状态持久化 |
| P5-7 | `hermes opc config` | 查看/修改 OPC 配置 | 写 `~/.hermes/opc/config.yaml` |

### 10.2 WebUI

WebUI 用于可视化管理，不应阻塞核心执行链路。

#### 页面清单

| 页面 | 功能 |
|------|------|
| Dashboard | 活跃任务、质量趋势、最近产物、待审批提案 |
| Agent List | Worker/Skill 浏览、评分、启停、模型偏好 |
| Task Detail | DAG 图、步骤状态、上下游摘要、产物版本 |
| Memory Browser | Project/Eval/KB 分区查看，带权限提示 |
| Artifact Viewer | 文件预览、版本切换、下载路径 |
| Proposal Review | 优化提案详情、证据、审批/拒绝 |
| Config | OPC 配置、路径、模型偏好、阈值 |

#### 技术建议

1. 后端：FastAPI，直接读取 OPC SQLite 和 proposals JSON。
2. 前端：React + Vite，轻量组件，不做复杂营销页。
3. DAG：优先使用 React Flow。
4. 图表：ECharts。
5. 鉴权：复用 Hermes Dashboard 鉴权机制；若不可用，第一版限制本地访问。

### 10.3 退出标准

1. CLI 能完成主要运维动作。
2. WebUI 能查看任务 DAG、Worker 状态、评分和提案。
3. WebUI 不能绕过人工审批直接自动应用优化。

## 12. Phase 7：生产化与 Beta 发布

### 11.1 安全

| ID | 任务 | 验收标准 |
|----|------|----------|
| P6-1 | 路径安全审计 | artifacts/memory/proposals 不允许路径穿越 |
| P6-2 | 工具权限审计 | Evaluator 只读 Project Memory，只写 Eval Memory |
| P6-3 | Prompt 注入防护 | SummaryBridge 标记来源和不可信内容 |
| P6-4 | 配置密钥审计 | 不在日志、DB、proposal 中泄露 secret |
| P6-5 | WebUI 鉴权 | 非授权用户不可访问任务和产物 |

### 11.2 性能

| ID | 任务 | 指标 |
|----|------|------|
| P6-6 | Leader 计划生成性能 | SIMPLE P95 < 5s，MEDIUM P95 < 15s |
| P6-7 | Memory 查询优化 | 常用 task 查询 P95 < 100ms |
| P6-8 | DAG 并行调度 | 并行 group 不串行阻塞 |
| P6-9 | Prompt 长度控制 | Agent List summary 和 KB 注入有 token budget |
| P6-10 | SQLite 并发测试 | 多 Worker 写入无锁死 |

### 11.3 文档

| ID | 文档 | 内容 |
|----|------|------|
| P6-11 | 安装文档 | pip/插件安装、配置路径、依赖 |
| P6-12 | 使用手册 | `/opc` 使用、计划确认、修订反馈 |
| P6-13 | Worker 扩展指南 | 新增 Worker/Skill/template/workflow/test |
| P6-14 | 运行手册 | 日志、DB、产物、备份、恢复 |
| P6-15 | 故障排查 | 常见错误和诊断命令 |

### 11.4 发布标准

1. 核心端到端场景全部通过。
2. 关键安全审查无高危未修复问题。
3. 文档覆盖安装、使用、扩展、故障排查。
4. 版本号、变更日志、迁移说明完整。

## 12. 端到端验收场景

### 12.1 文档/PPT 场景

用户请求：`/opc 帮我做一份 Q2 销售分析 PPT，包含趋势分析和图表`

期望流程：

1. Leader 评估为 COMPLEX 或 MEDIUM。
2. 生成 `data_analyst -> illustrator -> ppt_maker -> reviewer` 计划。
3. 用户确认后执行。
4. 数据分析报告写入 Project Memory。
5. 图表产物写入 Artifact Store。
6. PPT 文件写入 Artifact Store。
7. Reviewer 输出质量报告。
8. Evaluator 为每个 Worker 打分。
9. 用户获得 PPT 路径、摘要和后续建议。

### 12.2 软件开发场景

用户请求：`/opc 为 OPC-Hermes 增加一个任务状态 CLI，并补测试`

期望流程：

1. Leader 匹配 `backend_change` 或开发 pipeline。
2. 计划：`software_architect -> backend_engineer -> qa_engineer -> code_reviewer`。
3. Architect 输出影响文件和接口设计。
4. Backend 实现 CLI 状态读取。
5. QA 增加测试并执行。
6. Code Reviewer 输出 findings 或确认无严重问题。
7. Evaluator 写评分。
8. Leader 汇总变更、测试命令、剩余风险。

### 12.3 修订场景

用户反馈：`只把 PPT 第 4 页的柱状图换成折线图，其他内容不要动`

期望流程：

1. Revision Handler 识别为局部可视化修改。
2. 只路由到 `illustrator` 和 `ppt_maker`。
3. 产物生成新版本。
4. 原始版本可回溯。

### 12.4 优化场景

系统发现 `formatter` 最近 10 次完整性分数低于 0.5。

期望流程：

1. Optimizer 生成 prompt/模型优化提案。
2. Dashboard 显示证据和风险。
3. 用户审批或拒绝。
4. 若应用后质量下降，生成回滚提案。

## 13. 测试策略

### 13.1 测试层级

| 层级 | 覆盖内容 | 工具 |
|------|----------|------|
| Unit | registry、complexity、model_prefs、DAG、memory API | pytest |
| Contract | tool schema、plan schema、proposal schema | jsonschema/pytest |
| Integration | fake Hermes context、fake delegate、tmp SQLite | pytest |
| E2E | `/opc` 请求到 Worker 执行到评估 | pytest + fake provider |
| UI | WebUI 页面和 DAG 渲染 | Playwright |
| Security | path traversal、权限边界、secret 泄露 | pytest + 静态检查 |

### 13.2 必须新增的测试文件

| 文件 | 目的 |
|------|------|
| `tests/test_plugin_registration.py` | fake ctx 校验工具、hooks、toolsets 注册 |
| `tests/test_leader_prompt.py` | prompt 注入内容和配置覆盖 |
| `tests/test_plan_schema.py` | Leader plan 校验 |
| `tests/test_worker_dispatcher.py` | fake delegate 跑 DAG |
| `tests/test_memory_tools.py` | 记忆工具读写 |
| `tests/test_evaluator_flow.py` | snapshot 和 Eval Memory 写入 |
| `tests/test_optimizer.py` | 质量趋势生成提案 |
| `tests/test_artifact_manager.py` | 版本化和 latest |
| `tests/test_revision_handler.py` | 修订反馈路由 |
| `tests/test_security_boundaries.py` | 路径和记忆权限 |

### 13.3 测试数据策略

1. 所有 SQLite 测试使用 `tmp_path`。
2. 所有模型调用使用 fake provider 或 monkeypatch。
3. 所有 delegate 调用使用 fake delegate adapter。
4. artifact 测试使用临时文件，不写用户真实 home。
5. WebUI 测试使用固定 fixture API。

## 14. 数据与配置设计

### 14.1 配置文件

路径：`~/.hermes/opc/config.yaml`

必须支持：

1. `enabled`
2. `leader_model`
3. `agent_list_path`
4. `memory_path`
5. `artifact_path`
6. `model_preferences`
7. `evaluator`
8. `optimizer`
9. `knowledge_pipeline`
10. `webui`

### 14.2 存储目录

```text
~/.hermes/opc/
  config.yaml
  agent_list/
    workers.yaml
    skills.yaml
  memory/
    project.db
    eval.db
    kb.db
    chromadb/
  artifacts/
    <task_id>/<worker_id>/v001/
  proposals/
    <proposal_id>.json
  logs/
    opc.log
```

### 14.3 迁移策略

1. 每个 SQLite DB 增加 `schema_version` 表。
2. 启动时检查版本并执行幂等 migration。
3. migration 只前进，不自动删除用户数据。
4. 破坏性迁移必须生成备份。

## 15. 风险清单

| 风险 | 严重性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| Hermes 插件 API 与假设不一致 | 高 | 插件无法加载 | Phase 1 做 fake + real source 对照，保留 direct embedding API |
| `delegate_task` 参数不兼容 | 高 | Worker 无法执行 | 封装 adapter，写 contract test |
| 多 Worker 并发写 SQLite 锁冲突 | 中 | 任务失败或卡住 | WAL、短事务、重试、每 DB 独立锁 |
| SummaryBridge 摘要丢失关键信息 | 中 | 下游质量差 | 摘要 schema、artifact refs、必要字段校验 |
| Evaluator 打分不稳定 | 中 | Optimizer 误判 | 多维 rubric、低置信度标记、样本阈值 |
| Optimizer 提案过多 | 中 | 用户疲劳 | 去重、阈值、批量摘要、优先级 |
| WebUI 越权读取文件 | 高 | 数据泄露 | 路径白名单、鉴权、只读 API |
| 自动生成 Worker 质量不可控 | 中 | 路由错误 | 草案需用户确认，注册后先低权重 |
| 模型能力声明过时 | 中 | 任务失败 | capability checker + 配置覆盖 |
| 开发范围膨胀 | 高 | 延期 | 按阶段 gate，WebUI 不阻塞核心链路 |

## 16. 人员与智能体分工建议

本项目可以直接使用当前默认开发智能体协作：

| 工作类型 | 推荐 Worker |
|----------|-------------|
| 需求拆解、验收标准 | `product_engineer` |
| 架构和接口设计 | `software_architect` |
| 插件、memory、dispatcher、optimizer | `backend_engineer` |
| WebUI | `frontend_engineer` |
| 测试体系和回归 | `qa_engineer` |
| 打包、Cron、部署、日志 | `devops_engineer` |
| 安全边界、路径、权限 | `security_engineer` |
| 每阶段合并前审查 | `code_reviewer` |

### 16.1 推荐开发流水线

每个较大功能按以下流程走：

1. `product_engineer` 输出需求和验收标准。
2. `software_architect` 输出设计和影响范围。
3. `backend_engineer` 或 `frontend_engineer` 实现。
4. `qa_engineer` 补测试并验证。
5. `security_engineer` 只审查安全敏感变更。
6. `code_reviewer` 最后审查。
7. Leader 汇总结果。

## 17. 每周交付节奏

### Week 1

1. 修复导入、测试、打包基线。
2. 完成配置加载器。
3. 完成默认注册表和 toolset 校验。

### Week 2

1. 完成插件 tool/hook 注册。
2. 完成 Leader prompt 注入。
3. 完成 plan schema 和 parser。

### Week 3

1. 完成 `/opc` 计划生成和确认状态。
2. 完成 Leader 开发 workflow 路由。
3. 完成 Phase 1 集成测试。

### Week 4

1. 完成 dispatcher plan validator。
2. 完成 Worker prompt render。
3. 完成 TaskProtocol 写入。

### Week 5

1. 接入真实 `delegate_task`。
2. 完成串行和 Pipeline 执行。
3. 完成 SummaryBridge 写入。

### Week 6

1. 完成并行 group/batch dispatch。
2. 完成失败策略和恢复。
3. 完成 artifact 存储接入。

### Week 7

1. 完成 memory tools 端到端。
2. 完成 Evaluator trigger。
3. 完成 snapshot 和评分写入。

### Week 8

1. 完成 Agent 质量分更新。
2. 完成评估隔离和失败处理。
3. 完成评估相关测试。

### Week 9

1. 完成 Optimizer schema、趋势分析、去重。
2. 完成 proposal 持久化和审批状态。
3. 完成 Cron 接入。

### Week 10

1. 完成 KB 基础 ingestion/query。
2. 完成 Revision Handler 接入。
3. 完成修订产物版本化。

### Week 11

1. 完成 CLI list/status/proposals。
2. 完成 CLI config。
3. 完成 CLI 测试。

### Week 12

1. 完成 WebUI Dashboard、Task Detail、Agent List。
2. 完成 Proposal Review。
3. 完成基本 Playwright 验证。

### Week 13

1. 安全审计。
2. 性能测试。
3. E2E 场景补齐。

### Week 14

1. 文档补齐。
2. Beta 发布清单。
3. 版本号、CHANGELOG、迁移说明。

## 18. Definition of Done

每个功能完成必须满足：

1. 有明确验收标准。
2. 有单元测试或集成测试。
3. 涉及用户行为时有文档更新。
4. 涉及数据结构时有 schema 或 migration 说明。
5. 涉及安全边界时有安全测试。
6. 涉及 Worker 输出时写入 Project Memory。
7. 涉及质量评估时写入 Eval Memory。
8. 失败路径有可观察状态和错误信息。
9. 不修改 Hermes Agent 既有源码。
10. 可回滚或有恢复说明。

## 19. MVP 范围

如果需要压缩到最小可用版本，MVP 只保留：

1. `/opc` 触发 Leader。
2. Leader 生成并确认计划。
3. Agent Registry 匹配 Worker。
4. Dispatcher 串行/Pipeline 执行。
5. Project Memory + SummaryBridge。
6. Artifact Store。
7. 基础 Evaluator 写评分。
8. CLI 查看任务状态。

MVP 暂缓：

1. WebUI。
2. Knowledge crawler。
3. ChromaDB 向量索引。
4. 自动 Worker 生成。
5. Optimizer 回滚。
6. 复杂并行恢复。

## 20. 下一步行动

建议立即启动 Phase 0 和 Phase 1：

1. 补齐 `pytest` 开发依赖安装方式。
2. 完成配置加载器。
3. 完成插件 fake context 测试。
4. 完成 plan schema 和 parser。
5. 将 `worker_dispatcher.py` 的 stub 替换为 delegate adapter 设计草案。

完成这五项后，OPC-Hermes 就能从“架构原型”进入“可运行 MVP”阶段。
