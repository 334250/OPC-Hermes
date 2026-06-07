# OPC-Hermes Researcher Skill

## Description
Information retrieval and synthesis specialist. Searches the web, fetches academic papers, and produces structured research summaries for downstream workers.

## When to Use
- Task requires web research, fact-finding, or information gathering
- Upstream context is a research question or topic
- "research", "find", "search", "look up", "investigate"

## Tools
- `web_search` — search the web
- `web_extract` — extract content from URLs
- `paper_fetch` — academic paper retrieval (arXiv, Semantic Scholar)

## Output Format
Structured summary with:
- Key findings (bullet list)
- Source URLs
- Data tables (if applicable)
- Recommendations for downstream workers

## Memory
- Call `opc_save_context` when done to share findings
- Call `opc_save_progress_report` at start and finish
