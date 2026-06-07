"""
OPC-Hermes: Orchestrated Professional Colleagues

A multi-agent management layer built on top of Hermes Agent.
Does NOT modify Hermes Agent source code — operates entirely through
plugins, hooks, tool registration, and the cron API.

Core design principles:
  - Zero intrusion on Hermes Agent source
  - Memory isolation (Project / Eval / Knowledge Base)
  - Complexity-as-Skill
  - Evidence-backed evolution (proposal → human approval → manual switch)
"""

__version__ = "0.1.0"
__author__ = "OPC-Hermes Architecture Team"
