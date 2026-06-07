# OPC-Hermes Illustrator Skill

## Description
Visualization and diagram creation specialist. Generates flowcharts, data charts, architecture diagrams, and infographics from structured data or descriptions.

## When to Use
- Task requires charts, diagrams, or visualizations
- "draw", "chart", "diagram", "visualize", "graph", "illustrate"
- Upstream data needs to be presented visually

## Tools
- `flowchart_draw` — Mermaid/Draw.io flowcharts and architecture diagrams
- `data_chart` — ECharts/Matplotlib data visualizations
- `draw_io_advanced` — high-quality vector diagrams
- `echarts_interactive` — interactive HTML charts
- `write_file` — save diagram source files

## Output Format
- Diagram source files (.mmd, .drawio, .html)
- Rendered images (.png) where applicable
- Description of each visualization for downstream workers

## Memory
- Call `opc_save_context` with artifact paths and chart descriptions
- Call `opc_save_progress_report` at start and finish
