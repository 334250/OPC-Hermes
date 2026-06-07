"""Cycle Detector for OPC-Hermes task plans.

Scans a task plan for circular dependencies BEFORE execution.
Runs as a pre-flight check in the Leader's plan generation step.

Design reference: §9.5 循环依赖检测 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

from typing import Any, Dict, List, Set


def detect_cycle(steps: List[Dict[str, Any]]) -> List[List[int]]:
    """Detect cycles in a task plan's dependency graph.

    Args:
        steps: List of step dicts, each optionally with:
            - index: int
            - upstream: List[int] (dependencies)

    Returns:
        List of cycles found, where each cycle is a list of step indices.
        Empty list means no cycles.
    """
    n = len(steps)
    if n == 0:
        return []

    # Build adjacency list
    graph: Dict[int, List[int]] = {}
    for i, step in enumerate(steps):
        idx = step.get("index", i)
        upstream = step.get("upstream", [])
        if isinstance(upstream, int):
            upstream = [upstream]
        graph[idx] = [u for u in upstream if 0 <= u < n]

    # DFS-based cycle detection with path tracking
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[int, int] = {i: WHITE for i in range(n)}
    cycles: List[List[int]] = []
    path: List[int] = []

    def dfs(node: int) -> None:
        color[node] = GRAY
        path.append(node)

        for neighbor in graph.get(node, []):
            if color[neighbor] == GRAY:
                # Found a cycle — extract it from the path
                cycle_start = path.index(neighbor)
                cycles.append(list(path[cycle_start:]))
            elif color[neighbor] == WHITE:
                dfs(neighbor)

        path.pop()
        color[node] = BLACK

    for i in range(n):
        if color[i] == WHITE:
            dfs(i)

    return cycles


def check_plan(plan: Dict[str, Any]) -> List[str]:
    """Validate a task plan for common issues.

    Returns a list of human-readable issue descriptions.
    Empty list means the plan is valid.
    """
    issues: List[str] = []
    steps = plan.get("steps", [])

    if not steps:
        issues.append("Plan has no steps.")
        return issues

    # Check for cycles
    cycles = detect_cycle(steps)
    if cycles:
        for cycle in cycles:
            cycle_str = " → ".join(f"Step {i}" for i in cycle) + f" → Step {cycle[0]}"
            issues.append(f"Circular dependency: {cycle_str}")

    # Check for missing worker IDs
    for step in steps:
        if not step.get("worker_id"):
            issues.append(f"Step {step.get('index', '?')} has no worker_id.")

    # Check for self-dependency
    for step in steps:
        idx = step.get("index", -1)
        upstream = step.get("upstream", [])
        if isinstance(upstream, int):
            upstream = [upstream]
        if idx in upstream:
            issues.append(f"Step {idx} depends on itself.")

    # Check for invalid upstream references
    n = len(steps)
    for step in steps:
        idx = step.get("index", -1)
        upstream = step.get("upstream", [])
        if isinstance(upstream, int):
            upstream = [upstream]
        for u in upstream:
            if u < 0 or u >= n:
                issues.append(f"Step {idx} references invalid upstream {u} (valid range: 0-{n-1}).")

    return issues
