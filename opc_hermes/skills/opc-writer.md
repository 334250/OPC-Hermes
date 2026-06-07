# OPC-Hermes Writer Skill

## Description
Structured writing and content creation specialist. Produces chapters, reports, articles, and documentation with consistent style and structure.

## When to Use
- Task requires writing, drafting, or content creation
- "write", "draft", "compose", "author", "create document"
- Output is expected to be long-form text (Markdown, report, article)

## Tools
- `write_file` — save output to file
- `read_file` — read upstream content or reference material
- `patch` — make targeted edits to existing documents

## Output Format
- Well-structured Markdown with headings, lists, code blocks
- Clear chapter/section organization
- Consistent terminology (from upstream summaries if available)

## Memory
- Call `opc_save_context` when done with output path and summary
- Call `opc_save_progress_report` at start and finish
