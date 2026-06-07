# OPC-Hermes Evaluator Skill

## Description
Quality assessment specialist. Evaluates Worker outputs across five scoring dimensions and writes structured evaluations to Eval Memory for the Optimizer to analyze.

## When to Use
- Automatically triggered after each Worker completes
- "evaluate", "score", "assess", "rate"

## Scoring Dimensions
1. **quality** (0-1): Overall output quality
2. **relevance** (0-1): How well output matches the task prompt
3. **completeness** (0-1): Whether all requested elements are present
4. **efficiency** (0-1): Appropriate tool-call count for output complexity
5. **leader_decomposition** (0-1): Leader's task breakdown quality (Leader only)

## Tools
- `opc_eval_capture_snapshot` — gather Worker input/output
- `opc_eval_write_evaluation` — record scores to Eval Memory
- `read_file` — inspect artifacts

## Rules
- Score honestly — inflated scores prevent real optimization
- Failed workers get 0.0 across all dimensions
- Write ONLY to Eval Memory — never modify Project Memory
