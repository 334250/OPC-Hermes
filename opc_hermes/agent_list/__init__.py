"""Agent + Skill global registry for OPC-Hermes.

The registry stores:
  - Worker agents (role definitions, capabilities, model preferences)
  - Skills (reusable capabilities with input/output contracts)
  - Default workers and skills shipped with the system

Storage:
  - agent_list/workers.yaml  — user-registered workers
  - agent_list/skills.yaml   — user-registered skills
  - agent_list/defaults.yaml — system defaults (shipped with package)
"""
