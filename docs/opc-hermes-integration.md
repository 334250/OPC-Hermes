# OPC-Hermes 全链路改动清单

> **版本**: v0.1.0 | **仓库**: <https://github.com/334250/OPC-Hermes.git>
> 对照 Hermes Agent v0.15.1 源码结构，逐组件说明 OPC-Hermes 需要新增、配置、注册的内容。
> 核心原则：**不修改 Hermes Agent 任何既有源码，若必须修改，则应该描述清楚限制，并且告诉用户自己已经走过的测试方案，但是没有走通的理由**。

---

## 一、Hermes Agent 源码结构速览

```
hermes-agent/                       ← 既有项目根目录
├── cli.py                          ← CLI 入口
├── hermes_cli/                     ← CLI UI 组件 (Rich/prompt_toolkit)
├── run_agent.py                    ← AIAgent 核心循环 (~12k LOC)
├── gateway/
│   ├── run.py                      ← Gateway 主进程 (~18k LOC)
│   ├── platforms/                  ← 22 个消息平台适配器
│   └── session.py                  ← Gateway 会话管理
├── tools/
│   ├── registry.py                 ← 工具自注册系统
│   └── *.py                        ← 70+ 个工具实现
├── toolsets.py                     ← 工具集分组定义
├── hermes_state.py                 ← SQLite + FTS5 会话存储
├── cron/
│   ├── scheduler.py                ← Cron 调度器
│   └── jobs.py                     ← Cron 任务定义
├── plugins/                        ← 插件系统 (3 种发现源)
├── providers/                      ← 20+ LLM 供应商适配
├── agent/                          ← 供应商 API 适配器
├── prompt_builder.py               ← System prompt 构建
├── batch_runner.py                 ← 批量轨迹生成
├── trajectory_compressor.py        ← 轨迹压缩
├── config.yaml                     ← 用户配置
├── .env                            ← API 密钥
└── pyproject.toml                  ← 包管理
```

---

## 二、新增文件清单（OPC-Hermes 包）

以下全部放在 `opc_hermes/` 目录下，与 `hermes-agent/` 同级或作为子包安装：

```
opc_hermes/
├── __init__.py
├── plugin.py                       ← OPC Plugin 入口（hooks 注册 + 工具注册）
│   └── hooks: pre_gateway_dispatch, pre_llm_call, post_tool_call,
│              on_session_start, on_session_end
│   └── 功能: 消息拦截/Leader prompt 注入/工具集注册/Cron 注册
│
├── leader_prompt.py                ← Leader Prompt 构建器
│   └── 功能: 复杂度预判(规则) → Leader 行为指引构建 → Agent List 摘要注入
│   └── 注: Leader 不是独立进程，而是 Gateway Agent 通过 prompt 增强获得调度能力
│
├── worker_dispatcher.py            ← OPCWorkerDispatcher（delegate_tool 封装）
│   └── 功能: DAG 拓扑排序 → delegate_task batch 调用 → 记忆注入 → 结果收集
│   └── 依赖: tools.delegate_tool, memory_layer, agent_list
│   └── 注: 不自建进程管理器，复用 delegate_tool 的 ThreadPoolExecutor
│
├── complexity_rater.py             ← 共享复杂度评级 Skill
│   └── 注册为 Hermes Agent Tool
│   └── 输入: task_text, agent_id, criteria
│   └── 输出: {level, confidence, reasoning}
│
├── agent_list/
│   ├── __init__.py
│   ├── registry.py                 ← Agent + Skill 全局注册表
│   │   └── 存储: agent_list/workers.yaml, agent_list/skills.yaml
│   │   └── API: search(query), match(capability), register(agent), update_score(id, score)
│   └── defaults.yaml               ← 系统默认 Worker/Skill 定义
│
├── memory_layer/
│   ├── __init__.py
│   ├── gated_memory.py             ← GatedMemoryLayer 主类
│   │   └── 内部分区: leader_partition, worker_partition, summary_bridge
│   │   └── 存储: memory/project.db, memory/eval.db, memory/kb.db + chromadb/
│   ├── tools.py                    ← 记忆工具 (注册到 Hermes Agent, opc_ 前缀)
│   │   └── opc_save_context(worker_id, task_id, data)
│   │   └── opc_get_upstream_summaries(worker_id, task_id)
│   │   └── opc_write_to_bridge(entry)
│   │   └── opc_save_progress_report(worker_id, task_id, report)
│   │   └── opc_get_worker_context(worker_id, task_id)   ← 恢复时重载上下文
│   ├── task_protocol.py            ← TaskProtocol, ProgressReport 数据结构
│   └── summary_bridge.py           ← SummaryBridgeEntry 数据结构
│
├── evaluator.py                    ← Evaluator Agent 配置
│   └── 独立 Hermes Agent 实例, system_prompt 含评分维度定义
│   └── 读写 Eval Memory (独立 SQLite), 只读 Project Memory
│   └── 注册 evaluator_tools: capture_snapshot(), score_output(), write_evaluation()
│
├── optimizer.py                    ← 自动优化引擎
│   └── 作为 cron job 运行: 扫描 Eval Memory → 发现模式 → 生成优化提案
│   └── 推送提案到 WebUI Dashboard → 用户人工审批后手动切换
│   └── 自动回滚: 切换后监控质量，显著下降时自动告警 + 一键回滚
│
├── knowledge_pipeline.py           ← 知识获取管道 (§8.2, §8.3)
│   └── 用户上传: 解析文档/视频/URL → 结构化提取 → 写入 Knowledge Base
│   └── 爬虫通道: 按 Agent 配置定时爬取 → 去重清洗 → 质量评分 → 写入 Knowledge Base
│
├── revision_handler.py             ← 修订/反馈处理 (§9.3)
│   └── 分析用户修改意见 → 拆解为修订子任务
│   └── 判断受影响 Worker 范围（局部/结构/全文修改）
│   └── 分发修订任务 (仅给受影响的 Worker)
│
├── model_prefs.py                  ← 模型控制三层优先级
│   └── 读取: config.yaml 中用户偏好
│   └── 查询: Leader 推荐的模型
│   └── 兜底: 复杂度路由表
│   └── 输出: 实际使用的模型 (含切换记录 → Eval Memory)
│
├── workflow/
│   ├── __init__.py
│   ├── dag_executor.py             ← DAG 编排器（调用 worker_dispatcher）
│   ├── cycle_detector.py           ← 循环依赖检测
│   └── artifact_manager.py         ← 产物存储、版本管理、目录结构
│   └── 注: fault_handler/recovery 已删除——delegate_tool 内置超时/心跳/诊断
│
├── cli_skin/
│   ├── __init__.py
│   ├── theme.py                    ← Rich 主题 (OPC 品牌色)
│   ├── panels.py                   ← 工作流状态面板、Agent List 浏览面板
│   └── commands.py                 ← opc 命令注册 (opc list, opc status, opc config)
│   └── 注: Plugin 系统可注册 CLI 子命令 (£Q5 已确认)，此处保留为 CLI 模式下的备选
│
├── webui/                          ← OPC-Hermes 独立 WebUI (React + FastAPI)
│   └── 详见 §八 OPC-Hermes WebUI 设计规范
│
├── config/
│   ├── leader_default.yaml         ← 默认 Leader Agent 配置
│   ├── worker_templates/           ← Worker 默认模板 (按领域)
│   └── skill_templates/            ← Skill 默认模板
│
├── toolsets.py                     ← OPC-Hermes 专属工具集定义
│
└── requirements.txt                ← OPC-Hermes 新增 Python 依赖
    └── chromadb (向量索引，知识库语义搜索)
    └── pyyaml (Agent List 配置文件解析)
    └── (其余复用 Hermes Agent 既有依赖: sqlite3, rich, prompt_toolkit)
    └── opc_memory_toolset:   [save_context, get_summary, write_to_bridge, ...]
    └── opc_evaluator_toolset: [capture_snapshot, score_output, ...]
    └── opc_leader_toolset:   [complexity_rater, worker_discover, plan_generate, ...]
```

---

## 二-B、关键参考表

> 以下两张表是 OPC-Hermes 所有默认 Skill 和 Model 的完整清单，供开发时快速查阅。
> 定义源文件：`opc_hermes/agent_list/defaults.yaml`（Skills）和 `opc_hermes/config/capability_matrix.yaml`（Models）。

### Skills 总表

| Skill ID | 显示名称 | 功能描述 | 所属 Worker | 输入 | 输出 |
|----------|---------|---------|------------|------|------|
| `web_search` | 网页搜索 | 搜索引擎查询 + 结果提取 + 结构化摘要 | 调研、产品经理 | 搜索关键词/问题 | 结构化搜索结果列表 |
| `paper_fetch` | 论文检索 | arXiv/Semantic Scholar 学术文献检索 | 调研 | 论文标题/关键词/DOI | 论文摘要 + 引用信息 |
| `chapter_writing` | 章节撰写 | 结构化技术章节写作（含大纲→正文） | 书写、技术文档 | 章节大纲 + 上游摘要 | Markdown 章节正文 |
| `markdown_format` | Markdown 排版 | 格式化、目录生成、引用管理 | 排版、技术文档 | 原始 Markdown 文本 | 格式化后 Markdown |
| `grammar_check` | 语法检查 | 中英文语法/拼写/标点检查 | 审稿 | 待审文本 | 错误列表 + 修正建议 |
| `consistency_review` | 一致性审查 | 术语一致性、风格一致性、引用完整性 | 审稿 | 完整文档 | 不一致项列表 |
| `flowchart_draw` | 流程图绘制 | Mermaid/Draw.io 流程图、架构图生成 | 画图 | 图表需求描述 | `.mmd` / `.drawio` 文件 |
| `data_chart` | 数据图表 | ECharts/Matplotlib 数据可视化 | 画图、数据分析 | 结构化数据 + 图表类型 | `.png` / `.html` 图表 |
| `python_pptx` | PPT 生成 | python-pptx 演示文稿创建和编辑 | PPT制作 | Markdown 大纲 + 素材 | `.pptx` 文件 |
| `python_docx` | Word 生成 | python-docx 文档创建和编辑 | Word文档 | Markdown 正文 + 模板 | `.docx` 文件 |
| `pandas_analysis` | 数据分析 | Pandas/Scipy/DuckDB 数据清洗和分析 | 数据分析 | 数据文件路径 + 分析需求 | 分析报告 (JSON/Markdown) |
| `playwright_browser` | 浏览器自动化 | Playwright 浏览器操作（表单/抓取/截图） | 浏览器 | 操作指令 | 页面内容/截图 |
| `email_handler` | 邮件处理 | IMAP/SMTP 邮件收发、分类、附件处理 | 邮件 | 邮件操作指令 | 邮件列表/发送确认 |
| `translation_engine` | 翻译引擎 | 50+语言对翻译，支持领域术语表 | 翻译 | 源文本 + 目标语言 | 翻译后文本 |
| `draw.io_python` | Draw.io 图表 | 高质量矢量架构图生成 | 画图 | 图表规格描述 | `.drawio` 矢量图 |
| `echarts_python` | ECharts 图表 | 交互式数据图表生成 | 画图、数据分析 | 数据 + 图表配置 | `.html` 交互图表 |
| `sphinx_doc` | Sphinx 文档 | API 文档自动生成（Sphinx/rST） | 技术文档 | Python 源码路径 | HTML/PDF 文档 |
| `pandoc_convert` | Pandoc 转换 | 多格式文档互转（md↔docx↔pdf↔html） | Word文档、排版 | 源文件路径 + 目标格式 | 转换后文件 |

### Model 能力对照表

| Model | Provider | Vision | Tool Calling | Context Len | 适用复杂度 | 单用户推荐场景 |
|-------|----------|--------|-------------|-------------|-----------|---------------|
| `claude-sonnet-4` | Anthropic | ✅ | ✅ | 200K | MEDIUM / COMPLEX | 主力模型：复杂推理、长文档、代码生成 |
| `gpt-4o` | OpenAI | ✅ | ✅ | 128K | COMPLEX | 备选主力：多模态复杂任务 |
| `gpt-4o-mini` | OpenAI | ✅ | ✅ | 128K | SIMPLE | 轻量任务：翻译、摘要、简单问答 |
| `gemini-2.5-flash` | Google | ✅ | ✅ | 1M | SIMPLE / MEDIUM | 超长上下文：全量文档分析、知识库检索 |
| `deepseek-v3` | DeepSeek | ❌ | ✅ | 64K | MEDIUM | 纯文本推理：代码审查、逻辑分析 |
| `minicpmv4.6` | OpenBMB | ✅ | ❌ | 8K | SIMPLE | 本地免费：简单图表、短文本处理 |

> **能力声明校验**：模型选择流程的最后一步由 `CapabilityChecker`（§5.6）执行能力校验。若候选模型不满足任务所需能力（如 deepseek-v3 缺少 vision 但任务需要），系统自动在同 Provider 中寻找替代模型并通知用户。

---

## 三、Hermes Agent 既有文件——需要做的配置操作

以下操作通过 Hermes Agent 既有的插件系统、Cron API 和独立配置文件完成，不修改 Hermes Agent 源码：

### 3.1 配置文件 —— 独立 OPC 配置（不修改 Hermes config.yaml）

> **源码约束**：Hermes Agent 的 `hermes_cli/config.py` 中 `DEFAULT_CONFIG` 不含 `opc_hermes` 键，配置加载器会忽略未知顶层键。因此 OPC-Hermes 使用**独立配置文件**，由 `opc_hermes/` 包自行加载。

配置文件位置：`~/.hermes/opc/config.yaml`

```yaml
# ~/.hermes/opc/config.yaml
# OPC-Hermes 独立配置文件（不依赖 Hermes Agent 配置解析）
opc_hermes:
  enabled: true

  # Agent List 存储位置
  agent_list_path: "~/.hermes/opc/agent_list/"

  # 记忆层存储位置
  memory_path: "~/.hermes/opc/memory/"

  # 产物存储位置
  artifact_path: "~/.hermes/opc/artifacts/"

  # Leader Agent 默认模型（由用户在 hermes model 中选择）
  leader_model: "${HERMES_DEFAULT_MODEL}"

  # 模型偏好（三层优先级的第一层）
  model_preferences:
    global:
      preferred_provider: null       # 例: "anthropic"
      max_cost_per_call: null        # 例: 0.02
    agents: {}                       # 例: {code_agent: {model: "claude-sonnet-4"}}
    skills: {}                       # 例: {web_search: {model: "gpt-4o-mini"}}
    workflows: {}                    # 例: {document_creation: {global_model: "claude-sonnet-4"}}

  # Evaluator 配置
  evaluator:
    model: "claude-sonnet-4"
    scoring_thresholds:
      overall: 0.7
      accuracy: 0.8
      leader_decomposition: 0.6

  # Optimizer 配置
  optimizer:
    cron_interval: "1h"
    proposal:
      push_to_dashboard: true      # 推送提案到 WebUI Dashboard 等待人工审批
      min_evals_for_proposal: 30   # 最少需要多少条真实评分才能产出提案
    auto_rollback:
      quality_drop_threshold: 0.10
      error_rate_threshold: 0.05
      observation_days: 7          # 切换后观察天数

  # 工作流配置
  workflow:
    default_timeouts:
      SIMPLE: 120
      MEDIUM: 600
      COMPLEX: 1800
    max_delegation_depth: 5
    max_same_agent_calls: 2
    artifact_cleanup_days: 30      # 中间产物清理周期

  # WebUI 配置
  webui:
    port: 9120
    theme: "opc_dark"            # opc_dark | opc_light
    auto_open: true               # 启动时自动打开浏览器
```

**加载机制**（OPC 新增代码，不修改 Hermes Agent）：

```python
# opc_hermes/config.py
import yaml
from pathlib import Path
from hermes_constants import get_hermes_home

OPC_CONFIG_PATH = Path(get_hermes_home()) / "opc" / "config.yaml"

def load_opc_config() -> dict:
    """OPC 独立配置加载器，不依赖 Hermes config 解析。"""
    if OPC_CONFIG_PATH.exists():
        return yaml.safe_load(OPC_CONFIG_PATH.read_text())["opc_hermes"]
    return _default_config()
```

### 3.2 `.env` —— 无新增（复用 Hermes Agent 既有密钥）

OPC-Hermes 不引入新的 API 供应商，所有模型调用通过 Hermes Agent 的 Provider Resolution 完成。如果记忆层使用独立的向量索引（chromadb），chromadb 运行在本地无需密钥。

### 3.3 `toolsets.py` —— 通过 Plugin 注册 OPC 工具集（不修改源码）

> **源码约束**：Hermes Agent 的 `toolsets.py` 中 `TOOLSETS` 是模块级常量字典（`TOOLSETS = {...}`），`resolve_toolset(name)` 通过字典查找解析工具集。单纯 `from opc_hermes.toolsets import ...` 只是导入变量，不会将其注册到 TOOLSETS 字典。
>
> **解决方案**：利用 Hermes Plugin 系统的 `register_tool()` API 注册工具，并在插件初始化时运行时追加 TOOLSETS 字典条目。该方案利用 Python dict 可变性，不修改 `toolsets.py` 源文件。

OPC Plugin 初始化时完成工具注册（OPC 新增文件，不修改 Hermes Agent）：

```python
# opc_hermes/plugin.py
def initialize(ctx: PluginContext):
    """OPC Plugin 初始化——通过 Hermes 插件系统注册工具和工具集。"""
    
    # Step 1: 注册 OPC 工具到 ToolRegistry（通过 PluginContext.register_tool）
    from opc_hermes.memory_layer import tools as mem_tools
    from opc_hermes.evaluator import tools as eval_tools
    from opc_hermes.leader_agent import tools as leader_tools
    
    for tool_module in [mem_tools, eval_tools, leader_tools]:
        for tool_func in tool_module.get_tools():
            ctx.register_tool(tool_func)
    
    # Step 2: 运行时追加 TOOLSETS 字典条目（Python dict 可变——不修改源文件）
    from toolsets import TOOLSETS
    TOOLSETS.update({
        "opc_memory": {
            "name": "OPC Memory Tools",
            "description": "门控记忆层的读写工具",
            "tools": [
                "opc_save_context",
                "opc_get_upstream_summaries",
                "opc_write_to_bridge",
                "opc_save_progress_report",
                "opc_get_worker_context",
            ]
        },
        "opc_leader": {
            "name": "OPC Leader Tools",
            "description": "Leader Agent 的调度工具",
            "tools": [
                "opc_complexity_rate",
                "opc_worker_discover",
                "opc_plan_generate",
                "opc_task_dispatch",
            ]
        },
        "opc_evaluator": {
            "name": "OPC Evaluator Tools",
            "description": "Evaluator Agent 的评分工具",
            "tools": [
                "opc_capture_snapshot",
                "opc_score_output",
                "opc_write_evaluation",
            ]
        },
    })
```

**核心机制说明**：
- `PluginContext.register_tool()` 委托到 `tools.registry.register()`（源码 `hermes_cli/plugins.py` 文档确认）
- `TOOLSETS` 是 Python dict，运行时 `dict.update()` 即可追加新条目，`resolve_toolset()` 立即可解析
- 插件加载顺序：`on_session_start` hook 或插件 `initialize()` 均在第一次 tool call 之前执行

### 3.4 `cron/jobs.py` —— 通过 create_job() API 注册 Optimizer 定时任务

> **源码约束**：Hermes Agent 的 `cron/jobs.py` 无 `register()` 或 `cron_register()` 函数。Cron 系统采用声明式 JSON 存储（`~/.hermes/cron/jobs.json`），提供 CRUD API：`create_job()` / `update_job()` / `delete_job()` / `list_jobs()`。
>
> **解决方案**：OPC Plugin 在初始化时调用 `create_job()` API 注册定时任务，或预置配置到 `~/.hermes/cron/jobs.json`。

```python
# opc_hermes/plugin.py 中的 cron 注册逻辑（延续 initialize() 函数）

def _register_cron_jobs():
    """通过 Hermes Cron 的 create_job() API 注册 OPC 定时任务。"""
    from cron.jobs import create_job, list_jobs
    
    existing = {j["name"] for j in list_jobs()}
    
    if "opc_optimizer_scan" not in existing:
        create_job(
            name="opc_optimizer_scan",
            interval="1h",
            command="opc_hermes.optimizer:tick",
            description="扫描 Eval Memory，发现优化机会，生成提案推送到 Dashboard"
        )
    
    if "opc_knowledge_crawl" not in existing:
        create_job(
            name="opc_knowledge_crawl",
            interval="24h",
            command="opc_hermes.optimizer:run_knowledge_crawl",
            description="按 Agent 配置爬取外部知识源（知乎/GitHub/博客）"
        )
```

**替代方案（预置 JSON，不运行代码）**：直接在 `~/.hermes/cron/jobs.json` 中预写 OPC job 条目，Hermes Agent 启动时自动加载。适用于包管理器安装后自动配置的场景。

### 3.5 `hermes_state.py` —— 无需修改

OPC-Hermes 的记忆层使用**独立 SQLite 文件**（`~/.hermes/opc/memory/project.db`、`eval.db`、`kb.db`），与 Hermes Agent 的 `hermes_state.py` 管理的会话存储完全分离。两个系统各自管理自己的数据库，互不影响。

### 3.6 `prompt_builder.py` —— 无需修改

> **源码约束**：Hermes Agent 的 `prompt_builder.py` 是无状态的——它根据当前会话上下文动态构建 system prompt，不从 `config.yaml` 加载角色定义。

OPC-Hermes 的 Worker 角色 prompt 通过以下机制注入（均不修改 `prompt_builder.py` 源码）：

| 机制 | 说明 | 适用场景 |
|------|------|----------|
| `AGENTS.md` 文件 | 项目根目录下的 Agent 行为指南，Hermes Agent 已支持自动加载 | 固定角色定义（如“你是一个专业的技术写作者”） |
| `.hermes/context/` | 项目级 context 文件，自动注入到 system prompt | 项目背景、编码规范等共享上下文 |
| Leader 动态构建 | Leader Agent 在调用 Worker 时，通过 tool call 参数传入任务专属上下文 | 任务级动态指令（如“本次重点关注安全性”） |
| `pre_llm_call` hook | OPC Plugin 通过此 hook 在 LLM 调用前动态注入记忆层摘要 | 实时上下文注入（如上游 Worker 摘要） |

---

## 四、Hermes Agent 既有文件——完全不碰的部分

| 文件/目录 | 原因 |
|-----------|------|
| `run_agent.py` | AIAgent 核心循环——OPC 的角色 Agent 是标准 Hermes Agent 实例，复用此循环 |
| `cli.py` | CLI 入口——OPC 通过 `hermes_cli/plugins.py` 注册扩展命令 |
| `gateway/` | 消息平台接入——所有用户交互通过此层，OPC 不需要修改 |
| `tools/*.py` | 既有 70+ 工具——OPC 不修改，仅新增 `opc_hermes/` 下的工具并通过 Registry 注册 |
| `tools/registry.py` | 工具自注册——OPC 工具通过 Plugin 的 `register_tool()` 注册（见 §五），不修改此文件 |
| `plugins/` | 插件系统——OPC 可注册 CLI 子命令 (`register_cli_command`)，但皮肤/主题需通过独立 WebUI 实现 (见 §八) |
| `providers/` | LLM 供应商——OPC 不引入新供应商 |
| `agent/` | API 适配器——不修改 |
| `batch_runner.py` | 轨迹生成——可选用于批量评测和提案验证 |
| `trajectory_compressor.py` | 轨迹压缩——同上，可选 |

---

## 五、工具注册链（运行时启动流程）

OPC-Hermes 的工具如何进入 Hermes Agent 的 Tool Registry：

```
1. Hermes Agent 启动
   └─→ plugins/ 加载目录扫描（含 pip 包入口、~/.hermes/plugins/、项目级 .hermes/plugins/）
       └─→ 发现 opc_hermes 插件（通过 pip entry_points 或插件目录）
           └─→ 调用 opc_hermes/plugin.py: initialize(ctx)
               ├─→ ctx.register_tool(opc_save_context)
               ├─→ ctx.register_tool(opc_get_upstream_summaries)
               ├─→ ... 注册所有 OPC 工具
               └─→ TOOLSETS.update({"opc_memory": ..., "opc_leader": ..., "opc_evaluator": ...})
                   └─→ resolve_toolset("opc_memory") 即可解析 ✅

2. Worker Agent 获得工具:
   └─→ Leader 指定 worker 的 toolset = ["opc_memory", "web_search"]
   └─→ model_tools.py 调用 resolve_toolset("opc_memory") → 获取工具名列表
   └─→ 从 ToolRegistry 中查找已注册的 opc_* 工具实现
   └─→ 注入 Worker 可用工具列表 → LLM 推理时自动调用

3. Cron 任务注册:
   └─→ initialize(ctx) 中调用 _register_cron_jobs()
   └─→ create_job() 将 OPC 定时任务写入 ~/.hermes/cron/jobs.json
   └─→ Hermes Cron Scheduler 读取并执行
```

**核心约束**：
- Tool call 有硬编码 **300 秒超时**（`model_tools.py` L145: `future.result(timeout=300)`）
- 因此 Worker 执行必须拆分为多步 tool call（每步 < 300s），不允许单次长耗时操作

---

## 六、端到端数据流（一个文档制作任务的全链路）

```
用户在 Telegram 发送 "帮我写一份技术白皮书"
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ Hermes Agent Gateway (gateway/run.py) — 不修改               │
│ · 接收消息 → 解析用户 → 触发 pre_gateway_dispatch hook        │
│ · OPC Plugin 的 hook 回调判断是否需要多 Agent 编配：          │
│   - 复杂任务 → {"action": "rewrite", "text": "[OPC] ..."}   │
│     重写消息前缀，Agent 循环中 Leader 工具被触发              │
│   - 简单任务 → {"action": "allow"} 正常分发给标准 Agent      │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Leader Agent (opc_hermes/leader_agent.py) — OPC 新增         │
│                                                              │
│ 1. 意图解析 (LLM 推理, model=opc_config.leader_model)         │
│ 2. 查询 Agent List (opc_hermes/agent_list/registry.py)        │
│ 3. 生成计划 → 用户确认 (通过 Gateway 渲染交互卡片)              │
│ 4. 模型选择: 用户偏好 > Leader 推荐 > 复杂度路由                │
│    (opc_hermes/model_prefs.py)                                │
│ 5. DAG 执行 (opc_hermes/workflow/dag_executor.py)              │
│    └─→ Leader 以 tool call 方式调用 Worker                    │
│        └─→ Hermes Agent 标准 tool dispatch — 不修改           │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Worker(调研)     │ │ Worker(书写)     │ │ Worker(审稿)     │
│ Hermes Agent    │ │ Hermes Agent    │ │ Hermes Agent    │
│ 标准实例         │ │ 标准实例         │ │ 标准实例         │
│                 │ │                 │ │                 │
│ toolset:        │ │ toolset:        │ │ toolset:        │
│ + opc_memory    │ │ + opc_memory    │ │ + opc_memory    │
│ + web_search    │ │ + chapter_w     │ │ + grammar_ck    │
│                 │ │                 │ │                 │
│ 执行中调用:      │ │ 执行中调用:      │ │ 执行中调用:      │
│ save_context()  │ │ save_context()  │ │ save_context()  │
│ write_to_bridge │ │ get_summary()   │ │                 │
│                 │ │ write_to_bridge │ │                 │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│ Memory Layer (opc_hermes/memory_layer/) — OPC 新增            │
│                                                              │
│ project.db (SQLite + FTS5):                                  │
│   ├── leader_task_memory → TaskProtocol + ProgressReport     │
│   ├── worker_context → Worker A/B/C 完整执行链               │
│   └── summary_bridge → Worker 间摘要交换                     │
│                                                              │
│ eval.db (SQLite 独立文件):                                    │
│   └── Evaluator 评分记录                                     │
│                                                              │
│ kb.db + chromadb/:                                           │
│   └── 用户上传 + 爬虫知识                                     │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Evaluator Agent (opc_hermes/evaluator.py) — OPC 新增         │
│ · 旁系监听，异步评分                                           │
│ · 读写 eval.db，只读 project.db                               │
│ · 评分维度: worker_accuracy, worker_quality,                  │
│             leader_decomposition, memory_rule_quality         │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Optimizer (opc_hermes/optimizer.py) — OPC 新增               │
│ · cron 定时触发 (通过 Hermes Agent cron/ 注册)                 │
│ · 扫描 Eval Memory → 发现质量下降/成本优化机会                  │
│ · 生成优化提案 → 推送到 Dashboard → 人工审批 → 手动切换         │
└──────────────────────────────────────────────────────────────┘
```

---

## 七、已确认的集成边界（源码验证结果）

以下是对 Hermes Agent v0.15.1 源码的逐项验证结论：

### Q1: Tool Registry 扫描范围

**结论：Hermes 不会自动扫描 `opc_hermes/` 路径。OPC 通过 Plugin 系统的 `register_tool()` API 注册工具。**

源码分析：
- [`tools/registry.py` L57-L74](file:///home/zqh/data/OPC-Hermes/hermes-agent/tools/registry.py#L57-L74) — `discover_builtin_tools()` 只扫描 `tools/*.py` 目录，没有 `tool_scan_paths` 配置项
- 工具注册的正确路径是 **Plugin 系统**：`PluginContext.register_tool()` 委托到 `tools.registry.register()`，插件定义的工具与内置工具等价
- §3.3 的方案通过 OPC Plugin 的 `initialize(ctx)` 函数注册所有工具，无需修改 `toolsets.py` 源文件

> 无需添加 `tool_scan_paths` 配置项。无需修改 `toolsets.py` 源文件。

### Q2: toolsets.py 工具集注册

✅ 已确定 (§3.3)：通过 OPC Plugin 的 `initialize()` 函数在运行时调用 `TOOLSETS.update(...)` 追加 3 个工具集条目。这利用 Python dict 可变性，不修改 `toolsets.py` 源文件。`resolve_toolset()` 在调用时从 TOOLSETS dict 查找，运行时追加的条目立即生效。

### Q3: Gateway 交互卡片能力

**结论：Hermes 已有交互确认按钮的基座（`send_slash_confirm`），可在此基础上扩展。**

源码分析：
- [`gateway/platforms/base.py` L2074-L2106](file:///home/zqh/data/OPC-Hermes/hermes-agent/gateway/platforms/base.py#L2074-L2106) — `send_slash_confirm()` 基类方法，发送三选项确认提示（Approve Once / Always Approve / Cancel），定义完整流程：平台重写渲染按钮 → 按钮回调 → 网关 `_resolve_slash_confirm()` 分流
- 支持内联按钮的平台：**Telegram**（`InlineKeyboardButton`/`InlineKeyboardMarkup`/`CallbackQueryHandler`）、Discord、Slack、Matrix、Feishu、QQBot
- 不支持按钮的平台：回退为纯文本 `/approve`/`/always`/`/cancel` 斜杠命令

当前限制与实现路径：

| 方案 | 复杂度 | 说明 |
|------|--------|------|
| 扩展 `send_slash_confirm` | 中 | 修改 Telegram/Discord adapter 重写方法，支持自定义按钮文本（确认/修改/取消） |
| 文本降级（兜底方案） | 低 | 不支持按钮的平台使用 "回复 1 确认 / 2 修改 / 3 取消" |
| 自定义 Gateway Plugin | 高 | 通过 `pre_gateway_dispatch` hook 拦截消息并注入自定义按钮，功能最灵活 |

> **推荐**：先实现文本降级方案（零成本），在 Telegram/Discord 上通过扩展 `send_slash_confirm` 实现按钮版。

### Q4: cron/jobs.py 外部注册

✅ 已确定 (§3.4)：Hermes Cron 系统无 `register()` 或 `cron_register()` 函数，采用声明式 CRUD API。OPC Plugin 在初始化时调用 `create_job()` 注册定时任务（含幂等性检查，不重复创建）。无需修改 `cron/jobs.py` 源文件。

### Q5: Plugin CLI 皮肤扩展能力

**结论：Plugin 系统可注册新 CLI 命令，但不支持修改现有 CLI 的外观/皮肤。OPC 需独立 WebUI。**

源码分析：
- [`hermes_cli/plugins.py` L386-L407](file:///home/zqh/data/OPC-Hermes/hermes-agent/hermes_cli/plugins.py#L386-L407) — `register_cli_command()` 可注册 `hermes xxx` 子命令，有自己的 argparse 子解析器和 handler
- [`hermes_cli/plugins.py` L411-L420](file:///home/zqh/data/OPC-Hermes/hermes-agent/hermes_cli/plugins.py#L411-L420) — `register_command()` 可注册 `/xxx` 斜杠命令
- [`hermes_cli/plugins.py` L127-L167](file:///home/zqh/data/OPC-Hermes/hermes-agent/hermes_cli/plugins.py#L127-L167) — `VALID_HOOKS` 包含生命周期钩子（`pre_tool_call`/`post_tool_call`/`pre_llm_call` 等），**没有 `theme`/`skin`/`ui_render` 类钩子**

三种实现路径：

| 方案 | 复杂度 | 说明 |
|------|--------|------|
| Plugin 注册 CLI 子命令 | 低 | 注册 `hermes opc start`/`opc status`/`opc list` 等，复用既有 CLI TUI 框架 |
| 独立 WebUI (`opc_hermes/webui/`) | 中 | 新建 React 前端 + FastAPI 后端，参考 Hermes WebUI 布局 |
| 独立 CLI 封装 | 低—中 | 独立 Python 脚本调用 Hermes API/Agent，OPC 风格输出格式化 |

> **推荐**：考虑到 OPC 的核心场景是 DAG 执行可视化、Agent List 浏览、评估报告展示，富 GUI 的 WebUI 是最佳体验。详见 [OPC-Hermes WebUI 设计规范](#八-opc-hermes-webui-设计规范)。

---

> **总结**：OPC-Hermes 以“新增一个 Python 包 + 一个 Hermes Plugin + 一份独立配置文件”的方式完成集成，不修改 Hermes Agent 任何源码文件：
> - **OPC Plugin**（安装到 `~/.hermes/plugins/opc_hermes/` 或通过 pip entry_points）：注册工具、追加 TOOLSETS 条目、注册 Cron 任务、绑定 `pre_gateway_dispatch` hook
> - **独立配置**：`~/.hermes/opc/config.yaml`（OPC 自行加载，不依赖 Hermes config 解析）
> - **Cron 任务**：通过 `create_job()` API 写入 `~/.hermes/cron/jobs.json`
> 
> 这是全部对 Hermes Agent 既有环境的操作。其余 28 个文件全部在 `opc_hermes/` 包中新增，通过 Hermes Agent 既有的 Plugin System、Tool Registry、Cron API 的扩展点工作。核心循环 `run_agent.py`、消息平台 `gateway/`、LLM 供应商 `providers/` 完全不触及。
>
> **关键约束**：Tool call 有 300 秒硬超时（`model_tools.py` L145），Worker 执行必须拆分为多步调用。

---

## 八、OPC-Hermes WebUI 设计规范

### 8.1 定位与原则

OPC-Hermes WebUI 是一个**独立的 Web 前端**，专门用于多 Agent 编配（Orchestration）的可视化管理。它与 Hermes Agent 的 Web Dashboard 是**两套独立的应用**：

| 维度 | Hermes Web Dashboard | OPC-Hermes WebUI |
|------|---------------------|------------------|
| 定位 | Agent 运行时的**管理员面板** | 多 Agent 编配的**操作控制台** |
| 用户 | 个人开发者配置 Agent | 任务型用户调度多个 Worker |
| 核心场景 | 配 API Key、调模型、看日志 | 创建任务→确认计划→监控 DAG 执行→审阅产物 |
| 端口 | 9119 (FastAPI) | 9120 (独立 FastAPI) |
| 部署 | `hermes dashboard` 启动 | `hermes opc ui` 启动 |

**核心原则**：
1. **不修改 Hermes Agent 源码** — WebUI 通过 Hermes Agent 既有的 API 与工具链通信
2. **布局参考 Hermes WebUI** — 侧边栏导航 + 主内容区的经典布局，降低用户学习成本
3. **OPC 品牌独立** — 使用独立的颜色主题和视觉标识，与 Hermes Dashboard 区分
4. **渐进式开发** — 先实现核心页面（Dashboard + Tasks），后续迭代补充

### 8.2 布局架构

参考 Hermes WebUI 的 [App.tsx](file:///home/zqh/data/OPC-Hermes/hermes-agent/web/src/App.tsx) 布局结构：

```
┌──────────────────────────────────────────────────────────────┐
│  [折叠] [OPC · Hermes]              [主题] [语言] [用户]       │  ← Header (移动端)
├──────────┬───────────────────────────────────────────────────┤
│          │                                                   │
│  ⚡ 仪表盘 │  ┌─────────────────────────────────────────────┐  │
│  🤖 Agents │  │                                             │  │
│  📋 任务    │  │          主内容区                            │  │
│  📦 产物    │  │     (当前页面内容)                           │  │
│  📊 评估    │  │                                             │  │
│  🔧 配置    │  └─────────────────────────────────────────────┘  │
│          │                                                   │
│  ──────── │                                                   │
│  状态条    │                                                   │
│          │                                                   │
└──────────┴───────────────────────────────────────────────────┘
  ◄─ 240px ─►  ◄─────────────── flex-1 ──────────────────────►
```

**与 Hermes WebUI 布局对比**：

| 元素 | Hermes WebUI | OPC-Hermes WebUI |
|------|-------------|------------------|
| 侧边栏宽度 | 256px (可折叠至 56px) | 240px (可折叠至 56px) |
| 品牌区 | "Hermes Agent" | "OPC · Hermes" + OPC 图标 |
| 导航分隔 | 核心项 + Plugin 项 | 全部核心项（OPC 专属） |
| 底部区 | Auth 控件 + StatusStrip | Worker 状态 + Leader 心跳 |
| 主题切换 | DropUp 菜单 | 保留 |
| 语言切换 | 保留 | 保留 |

### 8.3 页面详情

#### 8.3.1 Dashboard（仪表盘）— `/`

默认首页，总览当前 OPC 系统状态。

```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│   活跃任务 (3)        │   在线 Worker (8)     │   质量分 (0.87)       │
│   ────────────────   │   ────────────────   │   ────────────────   │
│   大型  │ 2 运行中    │   空闲  │ 6          │   ↑ 0.03 vs 上周      │
│   ───────────────────────┴──────────────────────┴──────────────────────┐
│                                                                        │
│  最近任务                                          [+ 新建任务]         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 技术白皮书 v2      • 3/5 Workers 完成    • 15 min ago     → 查看  │  │
│  │ API 文档生成        • 已完成              • 2 hours ago    → 查看  │  │
│  │ 用户手册翻译        • 执行失败             • 1 day ago     → 查看   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  Agent List 概览                                                       │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐            │
│  │ 研究员    │ 写手      │ 审稿人    │ 译员      │ 数据分析   │  ...      │
│  │ ⭐ 4.2   │ ⭐ 4.5   │ ⭐ 3.8   │ ⭐ 4.1   │ ⭐ 4.0   │            │
│  │ 空闲      │ 忙碌      │ 空闲      │ 空闲      │ 离线      │            │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘            │
│                                                                        │
│  质量趋势 (近 7 天)                                                     │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  ▁▂▃▄▃▅▆  overall: 0.87  accuracy: 0.91  decomposition: 0.78     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

**数据来源**：
- 活跃任务 → Leader Agent 当前 DAG 状态
- 在线 Worker → Agent Registry 心跳
- 质量分 → Evaluator 7 日滚动平均
- 质量趋势 → Eval Memory 时间序列

#### 8.3.2 Agents（Agent 管理）— `/agents`

浏览、搜索、管理 Agent List 中的 Worker 和 Skill。

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Agents                                                    [+ 新建 Agent] │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ 🔍 搜索 Agent...          [全部 ▼] [Worker] [Skill] [⭐ 4.0+]       │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ ┌─ Agent 卡片 ─────────────────────┐ ┌─ Agent 卡片 ────────────────────┐ │
│ │                                  │ │                                  │ │
│ │  📝 技术写手 (writer)             │ │  🔍 研究员 (researcher)          │ │
│ │  ─────────────────────────────── │ │  ─────────────────────────────── │ │
│ │  Worker · 3 个 Skill · ⭐ 4.5   │ │  Worker · 2 个 Skill  · ⭐ 4.2  │ │
│ │  ─────────────────────────────── │ │  ─────────────────────────────── │ │
│ │  Capability: 技术文档写作，       │ │  Capability: 网络调研，          │ │
│ │  白皮书结构设计，Markdown 排版    │ │  信息检索，数据汇总              │ │
│ │  ─────────────────────────────── │ │  ─────────────────────────────── │ │
│ │  Model: claude-sonnet-4          │ │  Model: gpt-4o                   │ │
│ │  Status: ● 空闲                  │ │  Status: ● 忙碌 (1 task)        │ │
│ │  ─────────────────────────────── │ │  ─────────────────────────────── │ │
│ │  [查看详情] [编辑] [禁用]         │ │  [查看详情] [编辑] [禁用]        │ │
│ └──────────────────────────────────┘ └──────────────────────────────────┘ │
│                                                                          │
│ ┌─ Agent 详情面板 (点击卡片展开) ──────────────────────────────────────┐  │
│ │                                                                      │  │
│ │  技术写手 (writer)                                    [编辑] [禁用]   │  │
│ │  ═══════════════════════════════════════════════════════════════════  │  │
│ │                                                                      │  │
│ │  基础信息          │  所属 Skill          │  近期评分                  │  │
│ │  Type: Worker      │  • chapter_writing   │  ┌────────────────────┐   │  │
│ │  Model: ...        │  • markdown_format   │  │ ▁▂▃▄▃▅▆  0.87       │   │  │
│ │  Timeout: 600s     │  • proofreading      │  │ accuracy: 0.91     │   │  │
│ │  Max calls: 2      │                      │  └────────────────────┘   │  │
│ │                    │                      │                           │  │
│ │  System Prompt     │                      │  最近任务                  │  │
│ │  ┌──────────────┐  │                      │  • 白皮书章节撰写 ✅       │  │
│ │  │ ...prompt... │  │                      │  • API 文档格式化 ✅       │  │
│ │  └──────────────┘  │                      │  • 用户手册书写 ❌         │  │
│ └────────────────────┴──────────────────────┴───────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

**数据来源**：`agent_list/registry.py` — 从 `workers.yaml` / `skills.yaml` 读取，实时状态从 Agent Registry 查询。

#### 8.3.3 Tasks（任务管理）— `/tasks`

**核心页面**。创建新任务、确认计划、监控 DAG 执行。

**a) 任务列表视图**：

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Tasks                                                     [+ 新建任务]   │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ [全部 ▼] [运行中] [已完成] [失败]          🔍 搜索任务...             │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ ┌─ 任务行 ─────────────────────────────────────────────────────────────┐ │
│ │ 📋 技术白皮书 v2           MEDIUM · 3/5 Workers    ● 运行中  15min    │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐ │ │
│ │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░ 60%                            │ │ │
│ │ │ 研究员 ✅ → 写手 🔄 → 审稿 ⏳ → 排版 ⏳ → 发布 ⏳                │ │ │
│ │ └──────────────────────────────────────────────────────────────────┘ │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ ┌─ 任务行 ─────────────────────────────────────────────────────────────┐ │
│ │ 📋 API 文档生成           SIMPLE · 已完成    ● 完成  2 hours ago      │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐ │ │
│ │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 100%                           │ │ │
│ │ │ 分析 ✅ → 生成 ✅ → 格式化 ✅ → 校验 ✅                         │ │ │
│ │ └──────────────────────────────────────────────────────────────────┘ │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

**b) 新建任务向导**（多步骤表单）：

```
步骤 1/4 — 任务描述                              [取消] [下一步 →]
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  任务标题                                                                │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ 帮我写一份面向开发者的 OPC-Hermes 部署指南                          │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  详细描述 (可选)                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ 需要包含：系统架构概述、安装步骤、Worker 配置方法、                  │  │
│  │ 常见问题排查。目标读者：有 Python 基础的开发者。                     │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  附件 (可选)                                              [上传文件 📎]  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ opc-hermes-design-v3.0.md (45 KB)                        [✕ 移除]  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

步骤 2/4 — 复杂度评估 (自动)                     [上一步] [确认并继续 →]
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  ⏳ 正在评估任务复杂度...                                                 │
│                                                                          │
│  ┌─ 评估结果 ──────────────────────────────────────────────────────────┐ │
│  │                                                                      │ │
│  │  复杂度等级: MEDIUM (0.62)                                            │ │
│  │  置信度: 0.85                                                         │ │
│  │  理由: 多章节技术文档，需要调研 + 写作 + 审稿，涉及 4 个 Worker       │ │
│  │                                                                      │ │
│  │  模型路由: leader → claude-sonnet-4                                   │ │
│  │           worker → gpt-4o (default)                                   │ │
│  │                                                                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

步骤 3/4 — 计划预览 (交互确认)                  [上一步] [确认执行 →]
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  Leader 执行计划                            预计耗时: ~8 min              │
│                                                                          │
│  ┌─ DAG 可视化 ────────────────────────────────────────────────────────┐ │
│  │                                                                      │ │
│  │                ┌──────────┐                                          │ │
│  │                │ 研究员    │ ← 网络调研 + 竞品分析                     │ │
│  │                │ model:   │                                          │ │
│  │                │ gpt-4o   │                                          │ │
│  │                └────┬─────┘                                          │ │
│  │                     │ summary → bridge                               │ │
│  │           ┌─────────┼─────────┐                                      │ │
│  │           ▼         ▼         ▼                                      │ │
│  │     ┌──────────┐ ┌──────────┐ ┌──────────┐                          │ │
│  │     │ 写手(A)   │ │ 写手(B)   │ │ 写手(C)   │  ← 并行章节撰写          │ │
│  │     │ ch.1-2   │ │ ch.3-4   │ │ ch.5-6   │                          │ │
│  │     └────┬─────┘ └────┬─────┘ └────┬─────┘                          │ │
│  │          └──────────┬──┴───────────┘                                 │ │
│  │                     ▼                                                │ │
│  │                ┌──────────┐                                          │ │
│  │                │ 审稿人    │ ← 统稿 + 术语一致性检查                   │ │
│  │                └──────────┘                                          │ │
│  │                                                                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  操作:  [确认执行]  [修改计划 (反馈给 Leader)]  [取消任务]                │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

步骤 4/4 — 执行监控                              [返回任务列表]
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  执行中 — 技术白皮书 v2                                                  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░  55%                    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ Worker 状态 ───────────────────────────────────────────────────────┐ │
│  │                                                                      │ │
│  │  研究员 (researcher)                          ✅ 完成 · 2m 34s       │ │
│  │  ├─ web_search "OPC deployment"               ✅                     │ │
│  │  ├─ web_extract 3 sources                     ✅                     │ │
│  │  └─ opc_write_to_bridge                       ✅                     │ │
│  │                                                                      │ │
│  │  写手.A (writer) — 章节 1-2                    🔄 运行中 · 1m 12s    │ │
│  │  ├─ opc_get_upstream_summaries                ✅                     │ │
│  │  └─ write_chapter "安装步骤"                   🔄 ...writing...      │ │
│  │                                                                      │ │
│  │  写手.B (writer) — 章节 3-4                    ⏳ 等待上游            │ │
│  │  写手.C (writer) — 章节 5-6                    ⏳ 等待上游            │ │
│  │  审稿人 (reviewer)                              ⏳ 等待上游            │ │
│  │                                                                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌─ 实时日志 ──────────────────────────────────────────────────────────┐ │
│  │ [13:02:34] Worker researcher completed. Output: 3 sources extracted. │ │
│  │ [13:03:01] Worker writer.A started. Received upstream summary.       │ │
│  │ [13:04:15] Worker writer.A progress: Chapter 1 draft ready.          │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  操作: [暂停] [取消]                                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

**关键技术点**：
- DAG 可视化使用 **React Flow** 或 **Mermaid.js** 渲染（参考 Hermes WebUI 的 `@observablehq/plot` 图表方案）
- Worker 状态通过 WebSocket 实时推送（`/api/opc/tasks/{task_id}/ws`）
- 计划修改反馈通过 Leader Agent 的 tool call 实现

#### 8.3.4 Artifacts（产物管理）— `/artifacts`

浏览和管理任务产出的文件。

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Artifacts                                                   [清理过期]    │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │    按任务筛选: [全部 ▼]                               🔍 搜索文件...  │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ ┌─ 目录树 ────────┐ ┌─ 文件预览 ───────────────────────────────────────┐ │
│ │                 │ │                                                   │ │
│ │ 📁 技术白皮书v2  │ │  📄 01_架构概述.md                  12 KB        │ │
│ │  ├─ 📄 01_架构  │ │  ─────────────────────────────────────────────── │ │
│ │  ├─ 📄 02_安装  │ │  # OPC-Hermes 系统架构概述                       │ │
│ │  ├─ 📄 03_配置  │ │                                                   │ │
│ │  ├─ 📄 04_FAQ   │ │  OPC-Hermes 是一个基于 Hermes Agent 构建的...    │ │
│ │  └─ 📄 最终版    │ │                                                   │ │
│ │ 📁 API文档       │ │  ...更多内容...                                  │ │
│ │ 📁 翻译项目      │ │                                                   │ │
│ │                 │ │  ─────────────────────────────────────────────── │ │
│ │                 │ │  Worker: 写手.A · 生成时间: 2026-05-29 14:23     │ │
│ │                 │ │  [下载] [在新建标签页打开]                         │ │
│ └─────────────────┘ └───────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

**数据来源**：`opc_hermes/workflow/artifact_manager.py` — 产物目录结构和版本历史。

#### 8.3.5 Evaluations（评估中心）— `/evaluations`

查看 Evaluator 的评分历史和趋势。

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Evaluations                                                              │
│                                                                          │
│  总体质量趋势                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                                                                      │ │
│  │  1.0 ┤                                          ╭─ overall: 0.87     │ │
│  │  0.8 ┤    ╭──╮  ╭──╮    ╭────╮  ╭──╮  ╭────╮                         │ │
│  │  0.6 ┤  ╭╯  ╰──╯  ╰╮  ╭╯    ╰──╯  ╰──╯    ╰──                        │ │
│  │      ├────┼────┼────┼────┼────┼────┼────┼────                        │ │
│  │     5/22 5/23 5/24 5/25 5/26 5/27 5/28 5/29                         │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  按维度评分分布                                                           │
│  ┌──────────────┬──────────────┬──────────────┬──────────────────────┐  │
│  │ accuracy      │ quality       │ decomposition │ memory_rule_quality  │  │
│  │ ┌──────────┐  │ ┌──────────┐  │ ┌──────────┐  │ ┌────────────────┐  │  │
│  │ │ ████████ │  │ │ ██████   │  │ │ ████     │  │ │ ██████████    │  │  │
│  │ │ ████████ │  │ │ ████████ │  │ │ ████████ │  │ │ ██████████    │  │  │
│  │ │ 0.91     │  │ │ 0.85     │  │ │ 0.78     │  │ │ 0.92          │  │  │
│  │ └──────────┘  │ └──────────┘  │ └──────────┘  │ └────────────────┘  │  │
│  └──────────────┴──────────────┴──────────────┴──────────────────────┘  │
│                                                                          │
│  最近评估记录                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 任务                  │ overall │ accuracy │ quality  │ 时间         │ │
│  │───────────────────────│─────────│──────────│──────────│──────────────│ │
│  │ 技术白皮书 ✅          │ 0.88    │ 0.92     │ 0.85     │ 2 hours ago  │ │
│  │ API 文档 ✅            │ 0.91    │ 0.95     │ 0.88     │ 1 day ago    │ │
│  │ 翻译项目 ❌            │ 0.62    │ 0.70     │ 0.55     │ 2 days ago   │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

#### 8.3.6 Settings（配置）— `/settings`

OPC-Hermes 专用配置编辑器，结构与 Hermes WebUI 的 [ConfigPage](file:///home/zqh/data/OPC-Hermes/hermes-agent/web/src/pages/ConfigPage.tsx) 类似：

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Settings                                                                 │
│                                                                          │
│ ┌─ 配置分类 Tab ───────────────────────────────────────────────────────┐ │
│ │ [通用] [模型偏好] [Evaluator] [Optimizer] [工作流] [Agent List]     │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ ┌─ 通用配置 ───────────────────────────────────────────────────────────┐ │
│ │                                                                       │ │
│ │  Agent List 路径                                                      │ │
│ │  ┌──────────────────────────────────────────────────────────────┐    │ │
│ │  │ ~/.hermes/opc/agent_list/                      [浏览...]     │    │ │
│ │  └──────────────────────────────────────────────────────────────┘    │ │
│ │                                                                       │ │
│ │  记忆层路径                                                           │ │
│ │  ┌──────────────────────────────────────────────────────────────┐    │ │
│ │  │ ~/.hermes/opc/memory/                            [浏览...]     │    │ │
│ │  └──────────────────────────────────────────────────────────────┘    │ │
│ │                                                                       │ │
│ │  Leader 默认模型                                                      │ │
│ │  ┌──────────────────────────┐                                        │ │
│ │  │ claude-sonnet-4      [▼] │                                        │ │
│ │  └──────────────────────────┘                                        │ │
│ │                                                                       │ │
│ │  [保存配置]  [恢复默认]                                                │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 8.4 技术栈

与 Hermes WebUI 对齐的技术选型：

| 层 | 技术 | 说明 |
|----|------|------|
| 框架 | **React 18** + **TypeScript** | 与 Hermes WebUI 一致 |
| 构建 | **Vite 6** | 最新稳定版本，与 Hermes WebUI 共享 HMR + 代理配置模式 |
| 样式 | **Tailwind CSS v4** | 与 Hermes WebUI 一致 |
| 组件库 | **shadcn/ui 风格**（手写） | 可部分复用 Hermes WebUI 的 `components/ui/` |
| 图表 | **@observablehq/plot** | 用于评估趋势图（Hermes WebUI 已使用） |
| DAG 图 | **React Flow** (`@xyflow/react`) | 用于 DAG 执行可视化 |
| 终端 | **xterm.js** | 可选的调试终端（参考 ChatPage） |
| 图标 | **lucide-react** | 与 Hermes WebUI 一致 |
| 路由 | **react-router-dom v7** | 与 Hermes WebUI 一致 |
| 动效 | **motion** (framer-motion) | 与 Hermes WebUI 一致 |
| 后端 | **FastAPI** (Python) | 独立运行于端口 9120 |
| WebSocket | **FastAPI WebSocket** | 实时推送 DAG 进度、Worker 状态 |

### 8.5 后端 API 设计

OPC WebUI 的后端是一个**独立 FastAPI 应用**，运行在端口 9120，不修改 Hermes Agent 的 `tui_gateway/server.py`（端口 9119）。

```
opc_hermes/webui/
├── server.py           ← FastAPI 应用入口
├── routes/
│   ├── dashboard.py    ← GET /api/opc/dashboard  (聚合状态)
│   ├── agents.py       ← CRUD /api/opc/agents
│   ├── tasks.py        ← CRUD /api/opc/tasks + WebSocket
│   ├── artifacts.py    ← GET  /api/opc/artifacts
│   ├── evaluations.py  ← GET  /api/opc/evaluations
│   └── settings.py     ← GET/PUT /api/opc/settings
└── ws/
    └── task_progress.py ← WebSocket /api/opc/tasks/{task_id}/ws
```

**核心 API 端点**：

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/opc/dashboard` | 仪表盘聚合数据（活跃任务、在线 Worker、质量分） |
| `GET` | `/api/opc/agents` | Agent List（支持 search/capability/score 过滤） |
| `GET` | `/api/opc/agents/{id}` | Agent 详情（含评分历史、最近任务） |
| `POST` | `/api/opc/tasks` | 创建新任务（提交 task_text → 触发 Leader 规划） |
| `GET` | `/api/opc/tasks` | 任务列表（支持状态过滤） |
| `GET` | `/api/opc/tasks/{id}` | 任务详情（含 DAG 结构、Worker 状态） |
| `POST` | `/api/opc/tasks/{id}/confirm` | 确认计划（body: `{action: "confirm"|"modify"|"cancel"}`） |
| `POST` | `/api/opc/tasks/{id}/cancel` | 取消执行中的任务 |
| `WS` | `/api/opc/tasks/{id}/ws` | WebSocket 实时推送 Worker 状态变更 |
| `GET` | `/api/opc/artifacts` | 产物列表（按任务筛选） |
| `GET` | `/api/opc/artifacts/{id}/download` | 产物文件下载 |
| `GET` | `/api/opc/evaluations` | 评估记录列表 + 趋势数据 |
| `GET` | `/api/opc/settings` | 读取 OPC 配置 |
| `PUT` | `/api/opc/settings` | 更新 OPC 配置 |

### 8.5.1 数据访问路径（不修改 Hermes Agent 源码）

OPC WebUI 后端的核心挑战是：它运行在独立进程（端口 9120），但需要访问 Hermes Agent 进程内管理的数据。解决方案分两条路径：

```
┌──────────────────────────────────────────────────────────────────┐
│                    OPC WebUI 数据访问架构                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  路径 A: 直接读 SQLite 文件（静态数据）                             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ OPC WebUI FastAPI                                          │  │
│  │   │                                                        │  │
│  │   ├── /api/opc/agents ──────────► agent_list/*.yaml        │  │
│  │   ├── /api/opc/evaluations ─────► eval.db (只读)           │  │
│  │   ├── /api/opc/artifacts ───────► artifact_store/ 目录     │  │
│  │   └── /api/opc/settings ────────► config.yaml              │  │
│  │                                                            │  │
│  │  特点: 零延迟，无需与 Hermes Agent 进程通信                   │  │
│  │  前提: SQLite 开启 WAL 模式，读写不互斥                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  路径 B: SQLite 命令队列（实时数据与写操作，不修改源码）         │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ OPC WebUI (9120) 完全自包含——不依赖 Hermes 9119 端口        │  │
│  │                                                            │  │
│  │ 读操作（实时数据）:                                          │  │
│  │   GET /api/opc/tasks/{id} ──────► task_protocol 表 (SQLite)│  │
│  │   GET /api/opc/tasks/active ────► task_protocol 表 (SQLite)│  │
│  │   GET /api/opc/tasks/{id}/ws ───► progress_report 表轮询    │  │
│  │     OPC WebUI 的 WebSocket 端点每秒查询 SQLite 中最新        │  │
│  │     ProgressReport，有变化时推送客户端                      │  │
│  │                                                            │  │
│  │ 写操作（通过命令队列）:                                       │  │
│  │   POST /api/opc/tasks ───► command_queue 表 INSERT          │  │
│  │   POST /api/opc/tasks/{id}/confirm ──► 同上                │  │
│  │   Leader Agent 定期轮询 command_queue 表获取新指令          │  │
│  │                                                            │  │
│  │ 实现方式:                                                   │  │
│  │  1. opc_hermes/webui/server.py 为独立 FastAPI 进程 (9120)  │  │
│  │  2. 直接使用 sqlite3 模块读 GatedMemoryLayer 的 SQLite 文件 │  │
│  │     (WAL 模式下 Leader/Worker 写、WebUI 读互不阻塞)         │  │
│  │  3. 写操作写入 command_queue 表，Leader 在 Scheduler 循环中 │  │
│  │     调用 check_command_queue() 获取并执行新命令              │  │
│  │  4. WebSocket 端点使用 asyncio + aiosqlite 轮询实现         │  │
│  │                                                            │  │
│  │  不依赖 post_server_startup hook（该 hook 在 Hermes Agent   │  │
│  │  的 VALID_HOOKS 中未确认存在），完全独立运行                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  两条路径统一原则:                                                │
│  · 所有数据（静态 + 实时）→ 通过 SQLite WAL 模式并发访问         │
│  · 读操作 → 直读 SQLite/YAML 文件                               │
│  · 写操作 → INSERT command_queue → Leader 轮询执行              │
│  · WebUI 完全不依赖 Hermes 9119 端口，零耦合                     │
└──────────────────────────────────────────────────────────────────┘
```

> **关键约束**：OPC WebUI 通过 SQLite WAL 模式与 Hermes Agent 进程共享数据文件，不依赖 Hermes 任何内部 API 或未验证 hook。`command_queue` 表是 OPC 主动写入、Leader 被动轮询的单向通道，不修改 Hermes Agent 源码。

### 8.6 主题与品牌

OPC-Hermes WebUI 使用独立的品牌色方案，与 Hermes Dashboard 的 "Hermes Teal" 主题区分：

```css
/* OPC-Hermes 品牌色 */
:root {
  --opc-foreground: color-mix(in srgb, #e8e0d5 100%, transparent);  /* 暖纸色 */
  --opc-midground: color-mix(in srgb, #c9a96e 100%, transparent);   /* 金色 */
  --opc-background: color-mix(in srgb, #0d1117 100%, transparent);  /* 深蓝黑 */

  /* 语义色 */
  --opc-accent: #d4a853;         /* OPC 金 */
  --opc-success: #3fb950;
  --opc-warning: #d29922;
  --opc-danger: #f85149;

  /* 组件色 */
  --opc-card: color-mix(in srgb, var(--opc-midground) 6%, var(--opc-background));
  --opc-border: color-mix(in srgb, var(--opc-midground) 15%, transparent);
}
```

**与 Hermes WebUI 主题系统的关系**：Hermes WebUI 的 `themes/` 目录和 `ThemeProvider` 机制可以**复用代码**，但使用独立的 CSS 变量命名空间（`--opc-*` 而非 `--color-*`），确保两个 UI 在视觉上独立。

### 8.7 项目文件结构

```
opc_hermes/
├── webui/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── main.tsx              ← React 入口
│   │   ├── App.tsx               ← 布局 + 路由
│   │   ├── index.css             ← Tailwind + OPC 主题变量
│   │   ├── components/
│   │   │   ├── ui/               ← 可复用 UI 原语
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── Header.tsx
│   │   │   │   └── StatusStrip.tsx
│   │   │   ├── dag/
│   │   │   │   ├── DagCanvas.tsx       ← React Flow 画布
│   │   │   │   ├── WorkerNode.tsx      ← Worker 节点渲染
│   │   │   │   └── DagControls.tsx     ← 缩放/布局控件
│   │   │   └── task/
│   │   │       ├── TaskWizard.tsx       ← 新建任务多步表单
│   │   │       ├── PlanPreview.tsx      ← 计划预览 + 确认按钮
│   │   │       └── ProgressMonitor.tsx  ← 执行进度监控
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── AgentsPage.tsx
│   │   │   ├── TasksPage.tsx
│   │   │   ├── ArtifactsPage.tsx
│   │   │   ├── EvaluationsPage.tsx
│   │   │   └── SettingsPage.tsx
│   │   ├── lib/
│   │   │   ├── api.ts            ← 类型化 API 客户端
│   │   │   ├── ws.ts             ← WebSocket 客户端
│   │   │   └── utils.ts          ← cn() helper
│   │   └── hooks/
│   │       ├── useTaskProgress.ts
│   │       ├── useAgents.ts
│   │       └── useDashboard.ts
│   └── public/
│       └── favicon.svg
│
├── server.py                      ← FastAPI 后端入口
└── routes/                        ← API 路由
```

### 8.8 实施路径

分四个阶段渐进式交付：

**Phase 1: 基础框架**（Week 1-2）
- Vite + React + Tailwind 项目初始化
- 侧边栏导航 + 路由框架 (参考 Hermes App.tsx 布局)
- FastAPI 后端骨架 + 前 3 个 Stub API
- OPC 品牌色主题

**Phase 2: 核心页面**（Week 3-4）
- Dashboard 页面（聚合状态 + 最近任务列表）
- Agents 页面（Agent List 浏览/搜索/详情）
- Tasks 页面（任务列表 + 创建向导 Step 1-2）

**Phase 3: DAG 可视化**（Week 5-6）
- Tasks 页面 DAG 计划预览（React Flow）
- WebSocket 实时进度推送
- 执行监控面板（Worker 状态 + 实时日志）
- Artifacts 页面

**Phase 4: 评估与优化**（Week 7-8）
- Evaluations 页面（评分趋势 + 维度分布）
- Settings 配置编辑器
- 响应式适配（移动端）
- i18n 国际化

### 8.9 与 Hermes WebUI 的代码复用

| 复用项 | 方式 |
|--------|------|
| `cn()` helper | 直接复制，依赖 `clsx` + `tailwind-merge` |
| `api.ts` fetch 封装 (fetchJSON, SESSION_HEADER) | 参考实现，写入 `opc_hermes/webui/src/lib/api.ts` |
| `vite.config.ts` dev-proxy + `hermesDevToken` 模式 | 参考实现，适配 OPC 后端端口 9120 |
| `index.css` 的 `@font-face` + `@theme inline` 模式 | 参考结构，使用 OPC 颜色 token |
| `components/ui/` (Button, Card, Badge, Input...) | 参考结构，不直接引入 Hermes 的 `@nous-research/ui`，避免品牌串扰 |
| `Sidebar.tsx` 布局结构 (展开/折叠/移动端) | 参考实现逻辑，独立重写 |
| 主题切换器 | 参考 `ThemeSwitcher.tsx`，简化为 OPC 单一主题 |
| i18n 结构 | 参考 `i18n/` 目录，使用相同的 Context 模式 |

> **关键决策**：不引入 `@nous-research/ui` 作为依赖——OPC WebUI 需要独立的品牌视觉，引用 Hermes 的 UI Kit 会导致颜色 token 冲突和品牌串扰。组件从零手写，但参考其 API 设计。

---

## 九、测试策略

### 9.1 测试层次

```
┌─────────────────────────────────────────┐
│          OPC-Hermes 测试金字塔            │
├─────────────────────────────────────────┤
│                                         │
│   E2E (端到端)                           │
│  ┌─────────────────────────────────┐    │
│  │ · 完整任务链路: 输入 → Leader   │    │
│  │   → Worker → 总结 → 产物        │    │
│  │ · 3 种任务类型，各 10 次重复    │    │
│  │ · 框架: pytest + subprocess     │    │
│  └─────────────────────────────────┘    │
│                                         │
│   Integration (集成测试)                 │
│  ┌─────────────────────────────────┐    │
│  │ · GatedMemoryLayer SQLite 读写  │    │
│  │ · AgentTaskDispatcher 并行调度  │    │
│  │ · ChromaDB 语义搜索一致性       │    │
│  │ · 模型路由降级链验证            │    │
│  └─────────────────────────────────┘    │
│                                         │
│   Unit (单元测试)                        │
│  ┌─────────────────────────────────┐    │
│  │ · Schema Migration 迁移验证     │    │
│  │ · SummaryBridge 摘要校验        │    │
│  │ · ComplexityRater 判定逻辑      │    │
│  │ · DedupPipeline 去重准确性      │    │
│  │ · TaskProtocol 序列化/反序列化  │    │
│  └─────────────────────────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

### 9.2 测试组织

```
opc_hermes/tests/
├── conftest.py              ← pytest fixtures (temp SQLite / agent_list)
├── unit/
│   ├── test_schema_migration.py
│   ├── test_summary_bridge.py
│   ├── test_complexity_rater.py
│   ├── test_dedup.py
│   └── test_task_protocol.py
├── integration/
│   ├── test_memory_layer.py
│   ├── test_dispatcher.py
│   ├── test_chromadb_search.py
│   └── test_model_routing.py
└── e2e/
    ├── test_white_paper.py    ← 白皮书协作任务
    ├── test_code_review.py    ← 代码审查任务
    └── test_research.py       ← 调研分析任务
```

### 9.3 运行命令

```bash
# 单元测试
pytest opc_hermes/tests/unit/ -v

# 集成测试（需要 SQLite + chromadb）
pytest opc_hermes/tests/integration/ -v --db-path /tmp/test_hermes.db

# 端到端测试（需要 LLM API key）
pytest opc_hermes/tests/e2e/ -v --api-key $OPENAI_API_KEY --runs 10
```

---

## 十、部署流程

### 10.1 安装

```bash
# 1. 克隆仓库
git clone https://github.com/334250/OPC-Hermes.git
cd OPC-Hermes

# 2. 安装依赖
pip install -e .
# 或者 pip install opc-hermes

# 3. 初始化配置
hermes opc init
# 创建 ~/.hermes/opc/ 目录结构 + 默认配置文件

# 4. 验证安装
hermes opc status
```

### 10.2 目录结构（安装后）

```
~/.hermes/opc/
├── config.yaml                ← OPC 主配置（可覆盖 defaults.yaml）
├── agent_list/
│   ├── defaults.yaml          ← 系统默认 Agent/Skill 注册表
│   └── workers.yaml           ← 用户自定义 Worker
├── memory/
│   ├── project.db             ← Project Memory (SQLite WAL)
│   ├── eval.db                ← Eval Memory
│   ├── knowledge.db           ← Knowledge Base 元数据
│   ├── opc_cost.db            ← LLM 成本追踪
│   └── migrations/            ← Schema 迁移脚本 + 回滚
├── gitops/
│   └── agents/                ← Agent 配置 Git 版本仓库
├── artifact_store/
│   └── {task_id}/             ← 产物存储
└── models/
    └── capability_matrix.yaml ← 模型能力矩阵
```

### 10.3 启动

```bash
# 启动 OPC WebUI（独立进程，端口 9120）
hermes opc ui

# 启动 OPC CLI（复用 Hermes TUI）
hermes opc start
```

### 10.4 依赖清单

```
# requirements.txt (核心)
fastapi>=0.110
uvicorn>=0.29
sqlite-utils>=3.36
chromadb>=0.5
gitpython>=3.1
pyyaml>=6.0

# requirements-dev.txt (测试)
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27
```

---

## 十一、故障排查

### 11.1 常见问题

| 症状 | 可能原因 | 排查步骤 |
|------|---------|---------|
| `hermes opc ui` 启动失败 | 端口 9120 被占用 | `lsof -i:9120` 查看占用进程 |
| Worker 卡在 PENDING 状态 | Leader 进程未启动或崩溃 | 检查 `~/.hermes/opc/memory/project.db` 中 task_protocol 表 status 字段 |
| 语义搜索返回空 | chromadb 不可用 | 检查 chromadb 服务是否运行；查看日志是否触发 FTS5 降级 |
| 配置修改不生效 | 缓存未刷新 | 删除 `~/.hermes/opc/*.cache` 后重启 |
| SQLite 锁等待超时 | WAL 模式未开启 | 执行 `PRAGMA journal_mode=WAL;` 确认 WAL 模式已启用 |

### 11.2 日志位置

```
~/.hermes/opc/logs/
├── opc_webui.log     ← WebUI 后端日志
├── opc_leader.log    ← Leader Agent 调度日志
├── opc_workers.log   ← Worker 子进程日志 (按 worker_id 分文件)
└── opc_cron.log      ← Optimizer 定时任务日志
```

### 11.3 紧急回滚

```bash
# GitOps 回滚 - 回退指定 Agent 到上一版本
hermes opc rollback --agent {agent_id}

# Schema 回滚 - 手动执行回滚脚本
sqlite3 ~/.hermes/opc/memory/project.db < ~/.hermes/opc/memory/migrations/v1.rollback.sql

# 完全重置 - 删除所有 OPC 数据
hermes opc reset --confirm
# 将清空 ~/.hermes/opc/memory/、gitops/、artifact_store/ 目录
# Agent List 配置保留在 agent_list/ 中不受影响
```

---

## 十二、架构修正（基于源码验证 2026-06-06）

> 以下修正基于对 Hermes Agent v0.15.1 源码的逐行验证，对本文档第二节（新增文件清单）和第五节（工具注册链）产生影响。
> 完整修正方案见 [opc-hermes-design-v3.0.md 附录 E](./opc-hermes-design-v3.0.md#附录-e架构修正基于-hermes-agent-v0151-源码验证)。

### 12.1 关键发现：delegate_tool 已具备子 Agent 编排能力

Hermes Agent 的 `tools/delegate_tool.py` 是一个成熟的子 Agent 编排器：

```python
# 已有能力（无需 OPC 重建）：
- 并行 batch 模式：delegate_task(tasks=[{goal, context, toolsets}, ...])
- 可配置超时：delegation.child_timeout_seconds（默认 600s）
- 心跳监控：每 30s 检测子 Agent 活跃度
- 超时诊断：0-API-call 时自动 dump 堆栈
- 嵌套委托：role="orchestrator" 允许子 Agent 再委托
- 深度限制：delegation.max_spawn_depth（默认 2）
- 进度事件：DelegateEvent（SPAWNED/PROGRESS/COMPLETED/FAILED）
- 工具隔离：DELEGATE_BLOCKED_TOOLS 自动剥离危险工具
```

### 12.2 修正：Worker 派发机制

| 维度 | 原方案 | 修正方案 |
|------|--------|---------|
| 核心组件 | AgentTaskDispatcher (新建) | OPCWorkerDispatcher (delegate_tool 封装) |
| 进程模型 | multiprocessing.Process | ThreadPoolExecutor（delegate_tool 原生） |
| 超时 | 需绕过 300s 限制 | 无需绕过（300s 仅影响 async 工具） |
| 进度通知 | SQLite 轮询 ProgressReport | DelegateEvent + Gateway SSE |
| 代码量 | ~500 行 | ~150 行 |

**原因**：`model_tools.py` L145 的 `future.result(timeout=300)` 是 `run_sync()` 内部实现——仅将 async 协程桥接到同步。`delegate_task` 是同步函数，不经过此路径，有独立的 600s 超时。

### 12.3 修正：Leader 运行模型

| 维度 | 原方案 | 修正方案 |
|------|--------|---------|
| 运行形态 | 独立进程（未明确） | Gateway Agent + prompt 增强 |
| 消息接入 | 需自建 IPC | 复用 Gateway 消息路由 |
| 状态保持 | 未定义 | OPC Memory Layer 持久化 |
| 故障恢复 | 需自建守护进程 | Gateway 原生故障恢复 |

**实现方式**：`pre_gateway_dispatch` hook 判断任务复杂度，对复杂任务 `"rewrite"` 注入 Leader 行为指引。Agent 在获得 Leader prompt 后，通过 OPC 工具（`opc_plan_generate` + `delegate_task`）完成编排。

### 12.4 修正后的新增文件清单变更

```diff
opc_hermes/
- ├── leader_agent.py              ← 删除：不再需要独立调度进程
+ ├── leader_prompt.py             ← 新增：Leader Prompt 构建器

- ├── workflow/
- │   ├── fault_handler.py         ← 删除：delegate_tool 已内置
- │   ├── recovery.py              ← 简化：仅保留 OPC Memory 恢复点
+ ├── worker_dispatcher.py         ← 新增：delegate_tool 封装层（~150 行）
```

### 12.5 修正后的 delegation 配置

```yaml
# config.yaml — 新增 delegation 配置段
delegation:
  child_timeout_seconds: 1800    # Worker 超时（秒），覆盖默认 600s
  max_spawn_depth: 2             # Leader(0) → Worker(1)，Worker 不能再委托
  max_iterations: 100            # Worker 单次对话最多 100 轮 tool call
  # 注意：delegation 是 Hermes Agent 既有配置段，非 OPC 新增
```

### 12.6 Plugin Hook 验证确认

以下 hook 已在源码中确认可用（`hermes_cli/plugins.py` L127-167 `VALID_HOOKS` 集合）：

| Hook | 验证位置 | OPC 用途 |
|------|---------|---------|
| `pre_gateway_dispatch` | gateway/run.py L6854 | 消息拦截 + Leader prompt 注入 |
| `pre_llm_call` | plugins.py L136 | 动态注入 Agent List / 记忆摘要 |
| `post_tool_call` | plugins.py L129 | 捕获 delegate_task 结果，写入 ProgressReport |
| `on_session_start` | plugins.py L140 | 初始化 OPC 会话状态 |
| `on_session_end` | plugins.py L141 | 触发 Evaluator 评分 |

`pre_gateway_dispatch` 的详细行为：在 auth 之前运行、支持 `skip`/`rewrite`/`allow`、`rewrite` 使用 `dataclasses.replace(event, text=...)` 替换消息后继续正常 dispatch。
