# OPC-Hermes 开发智能体优化说明

本文档描述默认开发智能体的职责边界、推荐协同流程和扩展规则。定义源文件：

- `opc_hermes/agent_list/defaults.yaml`
- `opc_hermes/config/leader_default.yaml`
- `opc_hermes/config/worker_templates/prompts.yaml`

## 设计目标

开发类任务不应只交给一个“万能代码 Agent”。OPC-Hermes 默认将软件开发拆成需求、设计、实现、验证、审查和交付几个可独立评估的环节，方便 Leader 生成 DAG，也方便 Evaluator 精确定位质量问题。

## 默认开发 Worker

| Worker ID | 职责 | 主要输出 |
|-----------|------|----------|
| `product_engineer` | 澄清目标、约束、非目标、验收标准和任务切片 | 需求规格、验收标准、任务拆分 |
| `software_architect` | 设计模块边界、接口契约、数据流和实施计划 | 设计文档、实施计划、风险点 |
| `backend_engineer` | 实现 API、业务逻辑、数据模型和后端集成 | 代码变更、后端测试、实现说明 |
| `frontend_engineer` | 实现 UI、状态管理、交互和浏览器验证 | 前端代码变更、截图/验证结果 |
| `qa_engineer` | 将验收标准映射到测试并执行回归验证 | 测试文件、命令、通过/失败结果 |
| `devops_engineer` | 处理构建、CI/CD、部署配置和运行手册 | 配置变更、运行命令、回滚说明 |
| `code_reviewer` | 审查正确性、回归风险、维护性和测试缺口 | 严重程度排序的问题列表 |
| `security_engineer` | 审查权限、输入校验、密钥、依赖和高风险操作 | 风险列表、缓解措施、验证步骤 |

## 推荐协同流程

### 完整功能开发

`product_engineer -> software_architect -> backend_engineer/frontend_engineer -> qa_engineer -> code_reviewer`

适用于涉及前后端或多模块变更的功能开发。只有当任务涉及认证、权限、密钥、外部网络、文件系统或部署面时，才加入 `security_engineer` 或 `devops_engineer`。

### 后端变更

`software_architect -> backend_engineer -> qa_engineer -> code_reviewer`

适用于 API、数据模型、业务规则、任务队列、集成接口等后端变更。

### 前端变更

`software_architect -> frontend_engineer -> qa_engineer -> code_reviewer`

适用于页面、组件、状态流、可访问性、浏览器交互等前端变更。

### 发布/部署

`devops_engineer -> qa_engineer -> security_engineer`

适用于构建脚本、CI/CD、Docker、环境变量、部署配置和运行手册。

### 安全敏感任务

`security_engineer + code_reviewer + qa_engineer`

建议用 Star Delegation 并行审查，最后由 Leader 聚合风险与修复建议。

## Leader 路由规则

1. 开发任务默认先判断是否需要需求/设计阶段；简单 bugfix 可跳过 `product_engineer`。
2. 实现 Agent 不能在计划缺少验收标准、影响文件/模块和验证命令时直接开工。
3. Review Agent 不负责实现大段代码；它输出问题、风险、缺失测试和必要修复建议。
4. Security Agent 只在安全面明确存在时加入，避免每个任务都变成重流程。
5. DevOps Agent 只在构建、部署、环境、CI/CD 或可观测性受影响时加入。

## 扩展规则

新增开发智能体时，应同时补齐：

1. `defaults.yaml` 中的 skill 定义。
2. `defaults.yaml` 中的 worker 定义。
3. `prompts.yaml` 中同名 `system_prompt_template`。
4. `leader_default.yaml` 中需要自动触发的 workflow hint。
5. 注册表一致性测试，确保 skill、owner、template 不缺失。
