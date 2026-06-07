"""Workflow orchestration for OPC-Hermes.

Components:
  - dag_executor.py   — DAG topological sort + parallel execution
  - cycle_detector.py — circular dependency detection
  - artifact_manager.py — output storage, versioning, directory structure
"""
