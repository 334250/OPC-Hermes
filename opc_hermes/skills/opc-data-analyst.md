# OPC-Hermes Data Analyst Skill

## Description
Data analysis and statistics specialist. Cleans, analyzes, and extracts insights from structured data using Pandas, Scipy, and DuckDB.

## When to Use
- Task involves data analysis, statistics, or data cleaning
- "analyze", "data", "statistics", "trends", "numbers", "report"
- Upstream context includes a data file path

## Tools
- `terminal` — run Python/Pandas/SQL scripts
- `write_file` — save analysis report
- `read_file` — read data files and upstream context
- `data_chart` — create visualizations of findings (optional)

## Output Format
- Structured analysis report (Markdown or JSON):
  - Data summary (rows, columns, types)
  - Key findings (statistical tests, trends, outliers)
  - Recommendations
  - Charts (if requested)

## Memory
- Call `opc_save_context` with analysis report and key numbers
- Call `opc_save_progress_report` at start and finish
