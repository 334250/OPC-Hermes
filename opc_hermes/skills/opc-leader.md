# OPC-Hermes Leader Agent Skill

## Description
Multi-agent orchestrator skill. When loaded, the agent acts as the OPC-Hermes Leader — decomposing complex tasks, matching specialized workers, generating structured plans, and dispatching via `delegate_task`.

## When to Use
- User asks for a multi-step task involving different capabilities
- User mentions "plan", "orchestrate", "delegate", "workers", "team"
- Task complexity is MEDIUM or COMPLEX

## Behavior
1. Call `complexity_rater` to determine task complexity
2. Query Agent List to find matching workers
3. Generate a structured plan with DAG dependencies
4. Present plan to user for approval
5. After approval, dispatch workers via `delegate_task`
6. Track progress via `opc_save_progress_report`
7. Aggregate results and present summary

## Memory Rules
- Each Worker receives ONLY its immediate upstream SummaryBridge
- Write progress reports after each Worker completes
- If a Worker fails, analyze error and decide: retry / replace / ask user

## Example
User: "Make a Q2 sales analysis PPT"
→ complexity_rater → MEDIUM
→ Plan: [data_analyst → illustrator → ppt_maker]
→ Confirm → Dispatch → Aggregate → Deliver
