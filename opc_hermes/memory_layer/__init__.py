"""Gated Memory Layer for OPC-Hermes.

Three physically-separated storage partitions:
  - Project Memory   (project.db)  — task execution context
  - Eval Memory      (eval.db)     — quality metrics, evaluator scores
  - Knowledge Base   (kb.db + chromadb/) — domain knowledge, user uploads

Internal gating: Workers only read upstream SummaryBridge entries,
never raw project context. Evaluator writes only to Eval Memory.
"""
