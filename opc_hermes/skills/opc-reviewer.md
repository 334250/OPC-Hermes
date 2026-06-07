# OPC-Hermes Reviewer Skill

## Description
Quality review and proofreading specialist. Checks grammar, spelling, terminology consistency, style compliance, and reference integrity.

## When to Use
- Task involves reviewing, proofreading, or quality checking
- "review", "check", "proofread", "audit", "validate", "verify"
- Upstream worker has produced a document needing review

## Tools
- `read_file` — read the document to review
- `patch` — suggest or apply fixes
- `write_file` — save review report

## Output Format
- Review report with:
  - Grammar/spelling errors (with suggestions)
  - Terminology inconsistencies
  - Style violations
  - Missing or broken references
  - Overall quality assessment

## Memory
- Call `opc_save_context` with review findings
- Call `opc_save_progress_report` at start and finish
