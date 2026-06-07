"""DAG Executor for OPC-Hermes task plans.

Performs topological sort on task plan steps and dispatches
them in dependency order.  Parallel branches (steps with no
mutual dependencies) are dispatched concurrently via
delegate_task's batch mode.

Design reference: §9.6 DAG 编排器 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple


def topological_sort(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Topologically sort task plan steps by their upstream dependencies.

    Each step may have an ``upstream`` field: a list of step indices
    (0-based) that must complete before this step starts.

    Args:
        steps: List of step dicts, each optionally with:
            - index: int (0-based position in the plan)
            - upstream: List[int] (indices of steps this depends on)

    Returns:
        Steps sorted in dependency order (upstream before downstream).
        Steps with no mutual dependencies appear in their original order.

    Raises:
        ValueError: If a cycle is detected.
    """
    if not steps:
        return []

    # Build adjacency
    n = len(steps)
    # Ensure every step has an index
    indexed: List[Dict[str, Any]] = []
    for i, step in enumerate(steps):
        s = dict(step)
        if "index" not in s:
            s["index"] = i
        indexed.append(s)

    # Build graph: step_index → list of downstream step indices
    graph: Dict[int, List[int]] = {i: [] for i in range(n)}
    in_degree: Dict[int, int] = {i: 0 for i in range(n)}

    for step in indexed:
        idx = step["index"]
        upstream = step.get("upstream", [])
        if isinstance(upstream, int):
            upstream = [upstream]
        for u in upstream:
            if u < 0 or u >= n:
                raise ValueError(f"Step {idx} references invalid upstream index {u}")
            graph[u].append(idx)
            in_degree[idx] += 1

    # Kahn's algorithm
    queue: List[int] = [i for i in range(n) if in_degree[i] == 0]
    sorted_indices: List[int] = []

    while queue:
        node = queue.pop(0)
        sorted_indices.append(node)
        for downstream in graph[node]:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

    if len(sorted_indices) != n:
        # Cycle detected — find the cycle for a helpful error message
        remaining = set(range(n)) - set(sorted_indices)
        cycle_nodes = ", ".join(str(i) for i in remaining)
        raise ValueError(
            f"Circular dependency detected among steps: {cycle_nodes}. "
            f"Check the 'upstream' fields in your task plan."
        )

    # Return steps in topological order
    index_to_step = {s["index"]: s for s in indexed}
    return [index_to_step[i] for i in sorted_indices]


def find_parallel_groups(sorted_steps: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Group topologically-sorted steps into parallel-executable batches.

    Steps in the same batch have no dependencies on each other and can
    be dispatched concurrently via delegate_task's batch mode.

    Args:
        sorted_steps: Steps already sorted by topological_sort().

    Returns:
        List of batches, where each batch is a list of steps that can
        run in parallel. Batches are ordered: batch 0 must complete
        before batch 1 starts.
    """
    if not sorted_steps:
        return []

    batches: List[List[Dict[str, Any]]] = []
    completed: Set[int] = set()

    remaining = list(sorted_steps)
    while remaining:
        batch: List[Dict[str, Any]] = []
        next_remaining: List[Dict[str, Any]] = []

        for step in remaining:
            upstream = step.get("upstream", [])
            if isinstance(upstream, int):
                upstream = [upstream]
            if all(u in completed for u in upstream):
                batch.append(step)
                completed.add(step["index"])
            else:
                next_remaining.append(step)

        if not batch:
            # Should not happen if topological_sort passed, but guard anyway
            raise ValueError("Deadlock: no progress in parallel group detection")

        batches.append(batch)
        remaining = next_remaining

    return batches
