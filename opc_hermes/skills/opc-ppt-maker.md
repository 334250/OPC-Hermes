# OPC-Hermes PPT Maker Skill

## Description
Presentation creation specialist. Generates .pptx files with structured slides, embedded charts, and consistent styling using python-pptx.

## When to Use
- Task requires a PowerPoint/PPTX presentation
- "PPT", "presentation", "slides", "slide deck", "powerpoint"
- Upstream workers have produced content, charts, and data to present

## Tools
- `python_pptx` — generate .pptx files programmatically
- `write_file` — save the output file
- `terminal` — run python-pptx scripts

## Output Format
- .pptx file with:
  - Title slide
  - Agenda/outline slide
  - Content slides (from upstream summaries)
  - Chart slides (from upstream artifacts)
  - Conclusion/next-steps slide

## Memory
- Call `opc_save_context` with .pptx file path and slide summary
- Call `opc_save_progress_report` at start and finish
