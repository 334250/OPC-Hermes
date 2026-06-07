# OPC-Hermes 安装与运行指南

## 前置要求

- Python 3.11+
- Git
- (可选) Node.js 18+ 用于 WebUI 前端
- (可选) FastAPI + Uvicorn 用于 WebUI 后端

## 安装

### 方式 1: 从源码安装

```bash
git clone https://github.com/334250/OPC-Hermes.git
cd OPC-Hermes
pip install -e ".[all]"
```

### 方式 2: 作为 Hermes Agent 插件

```bash
# 复制到 Hermes 插件目录
cp -r opc_hermes/ ~/.hermes/plugins/opc-hermes/

# 重启 Hermes 后自动发现
hermes
```

## 配置

OPC-Hermes 使用独立配置文件 `~/.hermes/opc/config.yaml`：

```yaml
opc_hermes:
  enabled: true
  leader_model: claude-sonnet-4
  routing:
    trigger_prefixes: ["/opc"]
    auto_route_complex_tasks: false
  evaluator:
    enabled: true
    model: claude-sonnet-4
  optimizer:
    enabled: true
    cron_interval: "1h"
  knowledge_pipeline:
    enabled: false
    use_chromadb: false
  webui:
    enabled: true
    host: "127.0.0.1"
    port: 8765
```

## 使用

### 触发 OPC 模式

在 Hermes 对话中输入 `/opc` 前缀：

```
/opc 帮我做一个 Q2 销售分析 PPT
```

Leader Agent 将：
1. 调用 `complexity_rater` 评估任务复杂度
2. 查询 Agent List 匹配 Worker
3. 生成结构化计划
4. 等待用户确认后执行

### CLI 命令

```bash
hermes opc list agents     # 查看所有 Worker
hermes opc list skills     # 查看所有 Skill
hermes opc status <task>   # 查看任务状态
hermes opc config          # 管理 OPC 配置
hermes opc proposals       # 查看优化提案
hermes opc approve <id>    # 审批提案
```

### WebUI

```bash
# 启动后端
pip install fastapi uvicorn
python -m opc_hermes.webui.server

# 启动前端（开发模式）
cd opc_hermes/webui/frontend
npm install && npm run dev
# → http://localhost:5173
```

## 目录结构

```
~/.hermes/opc/
  config.yaml          # OPC 配置
  agent_list/          # Agent/Skill 注册表
    workers.yaml
    skills.yaml
  memory/              # 门控记忆
    project.db         # 项目记忆
    eval.db            # 评估记忆
    kb.db              # 知识库
  artifacts/           # Worker 产物
    <task_id>/<worker_id>/v001/
  proposals/           # 优化提案
    <proposal_id>.json
  logs/
    opc.log
```

## 故障排查

### Worker 不执行
1. 检查 `delegate_task` 是否可用（需在 Hermes Agent 环境中运行）
2. 查看 `~/.hermes/logs/agent.log` 中的 OPC 日志

### 评估不生成
1. 检查 `evaluator.enabled: true` 在配置中
2. 确认 Worker 已完成并有输出

### WebUI 无法连接
1. 确认 `python -m opc_hermes.webui.server` 已启动
2. 检查端口 8765 未被占用
3. 前端开发模式需同时运行 `npm run dev`
