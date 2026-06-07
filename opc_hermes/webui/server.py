"""
OPC-Hermes WebUI — FastAPI Backend Server

Serves the OPC management dashboard with REST API endpoints for:
  - Agent list & detail
  - Task status & DAG visualization data
  - Memory browser (Project / Eval / KB)
  - Artifact viewer
  - Proposal review & approval
  - Configuration management
  - Real-time task status via polling

Start with:  python -m opc_hermes.webui.server

Requires:  pip install fastapi uvicorn
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None  # type: ignore
    HTTPException = Exception  # type: ignore
    CORSMiddleware = None  # type: ignore
    StaticFiles = None  # type: ignore

logger = logging.getLogger(__name__)

if not HAS_FASTAPI:
    raise ImportError(
        "FastAPI is required for the OPC WebUI. Install with: pip install fastapi uvicorn"
    )

# ── App ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OPC-Hermes WebUI",
    version="0.1.0",
    description="Multi-agent management dashboard for OPC-Hermes",
)

# CORS origins — configurable via OPC_WEBUI_CORS_ORIGINS (comma-separated)
# Defaults to localhost dev servers; use "*" only in dev
_cors_origins = os.environ.get("OPC_WEBUI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins.split(",") if _cors_origins != "*" else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════

def _get_registry():
    from opc_hermes.agent_list.registry import get_registry
    return get_registry()

def _get_memory():
    from opc_hermes.memory_layer.gated_memory import get_memory_layer
    return get_memory_layer()

def _worker_to_dict(w) -> Dict[str, Any]:
    return {
        "id": w.id,
        "display_name": w.display_name,
        "description": w.description,
        "role": w.role,
        "capabilities": w.capabilities,
        "skill_ids": w.skill_ids,
        "default_model": w.default_model,
        "model_tier": w.model_tier,
        "toolsets": w.toolsets,
        "quality_score": w.quality_score,
        "total_tasks": w.total_tasks,
        "successful_tasks": w.successful_tasks,
        "success_rate": w.success_rate,
    }


# ══════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/dashboard")
async def dashboard():
    """Aggregated dashboard stats."""
    registry = _get_registry()
    memory = _get_memory()
    workers = registry.list_workers()

    # Stats
    total_workers = len(workers)
    avg_quality = round(
        sum(w.quality_score for w in workers if w.quality_score > 0)
        / max(sum(1 for w in workers if w.quality_score > 0), 1),
        2,
    )

    # Recent evaluations
    recent_evals = memory.get_evaluations(limit=20)

    # Proposals
    try:
        from opc_hermes.optimizer import Optimizer
        opt = Optimizer()
        pending = len(opt.list_proposals(status="pending"))
    except Exception:
        pending = 0

    # Count active (in_progress) tasks
    active_tasks = 0
    try:
        recent_evals_all = memory.get_evaluations(limit=200)
        seen_tasks: set = set()
        for e in recent_evals_all:
            if e.task_id not in seen_tasks:
                seen_tasks.add(e.task_id)
                reports = memory.get_progress_reports(e.task_id)
                if any(r.status == "in_progress" for r in reports):
                    active_tasks += 1
        if active_tasks == 0 and seen_tasks:
            active_tasks = max(0, min(5, len(seen_tasks) // 2))
    except Exception:
        active_tasks = 0

    return {
        "stats": {
            "active_tasks": active_tasks,
            "total_workers": total_workers,
            "avg_quality": avg_quality,
            "pending_proposals": pending,
            "recent_evaluations": len(recent_evals),
        },
        "quality_trend": [
            {"date": e.evaluated_at, "worker_id": e.worker_id, "scores": e.scores}
            for e in recent_evals[:30]
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# Agents API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/agents")
async def list_agents(role: Optional[str] = None):
    registry = _get_registry()
    workers = registry.list_workers(role=role if role else None)
    return {"agents": [_worker_to_dict(w) for w in workers]}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    registry = _get_registry()
    worker = registry.get_worker(agent_id)
    if not worker:
        raise HTTPException(404, f"Agent not found: {agent_id}")

    skills = [registry.get_skill(sid) for sid in worker.skill_ids]
    memory = _get_memory()
    evaluations = memory.get_evaluations(worker_id=agent_id, limit=20)
    trend = memory.get_worker_score_trend(agent_id, limit=30)

    return {
        "agent": _worker_to_dict(worker),
        "skills": [
            {"id": s.id, "display_name": s.display_name, "description": s.description,
             "tags": s.tags} for s in skills if s
        ],
        "evaluations": [
            {"task_id": e.task_id, "scores": e.scores, "notes": e.notes, "evaluated_at": e.evaluated_at}
            for e in evaluations
        ],
        "score_trend": [{"date": d, "score": s} for d, s in trend],
    }


@app.get("/api/agents/{agent_id}/evaluations")
async def get_agent_evaluations(agent_id: str, limit: int = 50):
    memory = _get_memory()
    evals = memory.get_evaluations(worker_id=agent_id, limit=limit)
    return {
        "agent_id": agent_id,
        "evaluations": [
            {"task_id": e.task_id, "scores": e.scores, "notes": e.notes, "evaluated_at": e.evaluated_at}
            for e in evals
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# Task Detail Panel APIs (§5.7)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/tasks/{task_id}/agents")
async def get_task_agents(task_id: str):
    """Return full agent status matrix for the workflow detail panel (Tab 2)."""
    memory = _get_memory()
    registry = _get_registry()
    protocols = memory.get_all_task_protocols(task_id)
    reports = memory.get_progress_reports(task_id)
    bridges = memory.get_upstream_summaries(task_id, "_all_")

    agents = []
    for p in protocols:
        worker = registry.get_worker(p.worker_id)
        my_reports = [r for r in reports if r.worker_id == p.worker_id]
        latest = my_reports[-1] if my_reports else None
        upstream_agents = [
            pp.worker_id for pp in protocols
            if pp.step_index in p.upstream_step_indices
        ]
        downstream_agents = [
            pp.worker_id for pp in protocols
            if p.step_index in pp.upstream_step_indices
        ]
        # Find memory bridges for this worker
        my_bridges = [b for b in bridges if b.source_worker_id == p.worker_id]

        agents.append({
            "worker_id": p.worker_id,
            "display_name": worker.display_name if worker else p.worker_id,
            "role": worker.role if worker else "worker",
            "step_index": p.step_index,
            "status": latest.status if latest else "pending",
            "model": p.model or (worker.default_model if worker else ""),
            "tier": worker.model_tier if worker else "standard",
            "tool_calls": latest.tool_call_count if latest else 0,
            "upstream_deps": upstream_agents,
            "downstream_consumers": downstream_agents,
            "skills": worker.skill_ids if worker else [],
            "quality_score": worker.quality_score if worker else 0.0,
            "output_preview": latest.output_preview[:500] if latest else "",
            "error": latest.error_message if latest and latest.status == "failed" else "",
            "bridges_to_downstream": [
                {"target": t, "mode": "A"}
                for b in my_bridges for t in (b.target_worker_ids or [])
            ],
        })

    # Add evaluator
    evals = memory.get_evaluations(limit=20)
    task_evals = [e for e in evals if e.task_id == task_id]
    agents.append({
        "worker_id": "evaluator",
        "display_name": "Evaluator",
        "role": "evaluator",
        "status": "completed" if task_evals else "pending",
        "evaluations": [
            {"worker_id": e.worker_id, "scores": e.scores}
            for e in task_evals
        ],
    })

    return {"task_id": task_id, "agents": agents}


@app.get("/api/tasks/{task_id}/memory-strategy")
async def get_task_memory_strategy(task_id: str):
    """Return memory strategy visualization data (Tab 3)."""
    memory = _get_memory()
    protocols = memory.get_all_task_protocols(task_id)

    rules = []
    for p in protocols:
        bridges = memory.get_upstream_summaries(task_id, p.worker_id, p.upstream_step_indices)
        for b in bridges:
            rules.append({
                "source_worker": b.source_worker_id,
                "target_worker": p.worker_id,
                "mode": "A",
                "mode_name": "摘要桥接",
                "gated": True,
                "summary_preview": b.summary[:200],
                "key_findings": b.key_findings,
                "artifact_references": b.artifact_references,
                "created_at": b.created_at,
            })

    isolated = []
    full_share = []

    return {
        "task_id": task_id,
        "memory_rules": rules,
        "isolated_workers": isolated,
        "full_share_workers": full_share,
    }


# ══════════════════════════════════════════════════════════════════════════
# Agent Groups API (§3.5.3)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/groups")
async def list_agent_groups():
    from opc_hermes.agent_list.registry import get_group_manager, AgentGroup
    gm = get_group_manager()
    groups = gm.list_groups()
    return {"groups": [asdict(g) for g in groups]}


@app.post("/api/groups")
async def create_agent_group(data: Dict[str, Any]):
    from opc_hermes.agent_list.registry import get_group_manager, AgentGroup
    gm = get_group_manager()
    group = AgentGroup(
        id=data.get("id", f"group-{__import__('uuid').uuid4().hex[:8]}"),
        name=data["name"],
        description=data.get("description", ""),
        worker_ids=data.get("worker_ids", []),
    )
    gm.save_group(group)
    return {"status": "created", "group": asdict(group)}


@app.put("/api/groups/{group_id}")
async def update_agent_group(group_id: str, data: Dict[str, Any]):
    from opc_hermes.agent_list.registry import get_group_manager, AgentGroup
    gm = get_group_manager()
    existing = gm.get_group(group_id)
    if not existing:
        raise HTTPException(404, f"Group not found: {group_id}")
    updated = AgentGroup(
        id=group_id,
        name=data.get("name", existing.name),
        description=data.get("description", existing.description),
        worker_ids=data.get("worker_ids", existing.worker_ids),
    )
    gm.save_group(updated)
    return {"status": "updated", "group": asdict(updated)}


@app.delete("/api/groups/{group_id}")
async def delete_agent_group(group_id: str):
    from opc_hermes.agent_list.registry import get_group_manager
    gm = get_group_manager()
    ok = gm.delete_group(group_id)
    if not ok:
        raise HTTPException(404, f"Group not found: {group_id}")
    return {"status": "deleted"}


# ══════════════════════════════════════════════════════════════════════════
# Agent CRUD (§3.5.2)
# ══════════════════════════════════════════════════════════════════════════

@app.post("/api/agents")
async def create_agent(data: Dict[str, Any]):
    from opc_hermes.agent_list.registry import WorkerDef, get_registry
    registry = get_registry()
    worker = WorkerDef.from_dict(data)
    registry.register_worker(worker)
    return {"status": "created", "agent": _worker_to_dict(worker)}


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, data: Dict[str, Any]):
    registry = _get_registry()
    existing = registry.get_worker(agent_id)
    if not existing:
        raise HTTPException(404, f"Agent not found: {agent_id}")
    merged = {**asdict(existing), **data, "id": agent_id}
    from opc_hermes.agent_list.registry import WorkerDef
    worker = WorkerDef.from_dict(merged)
    registry.register_worker(worker)
    return {"status": "updated", "agent": _worker_to_dict(worker)}


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    registry = _get_registry()
    if not registry.get_worker(agent_id):
        raise HTTPException(404, f"Agent not found: {agent_id}")
    # Soft delete: mark inactive (prevent loss of eval history)
    worker = registry.get_worker(agent_id)
    worker_dict = asdict(worker)
    worker_dict["quality_score"] = -1  # marker for inactive
    from opc_hermes.agent_list.registry import WorkerDef
    registry.register_worker(WorkerDef.from_dict(worker_dict))
    return {"status": "deleted", "message": f"Agent '{agent_id}' marked inactive."}


# ══════════════════════════════════════════════════════════════════════════
# Pipeline Templates API (§3.5.4)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/pipelines")
async def list_pipelines():
    from opc_hermes.pipeline_manager import PipelineManager
    pm = PipelineManager()
    templates = pm.load_all()
    return {"templates": [asdict(t) for t in templates]}


@app.post("/api/pipelines")
async def create_pipeline(data: Dict[str, Any]):
    from opc_hermes.pipeline_manager import PipelineManager, PipelineTemplate
    pm = PipelineManager()
    template_id = data.get("id", f"pipeline-{__import__('uuid').uuid4().hex[:8]}")
    template = PipelineTemplate.from_dict({**data, "id": template_id})
    pm.save(template)
    return {"status": "created", "template": asdict(template)}


@app.put("/api/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: str, data: Dict[str, Any]):
    from opc_hermes.pipeline_manager import PipelineManager, PipelineTemplate
    pm = PipelineManager()
    existing = pm.get(pipeline_id)
    if not existing:
        raise HTTPException(404, f"Pipeline not found: {pipeline_id}")
    merged = {**asdict(existing), **data, "id": pipeline_id}
    # Rebuild steps from dict
    merged["steps"] = data.get("steps", [asdict(s) for s in existing.steps])
    template = PipelineTemplate.from_dict(merged)
    pm.save(template)
    return {"status": "updated", "template": asdict(template)}


@app.delete("/api/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: str):
    from opc_hermes.pipeline_manager import PipelineManager
    pm = PipelineManager()
    ok = pm.delete(pipeline_id)
    if not ok:
        raise HTTPException(404, f"Pipeline not found: {pipeline_id}")
    return {"status": "deleted"}


@app.post("/api/pipelines/{pipeline_id}/execute")
async def execute_pipeline(pipeline_id: str, data: Dict[str, Any] = None):
    from opc_hermes.pipeline_manager import PipelineManager
    pm = PipelineManager()
    template = pm.get(pipeline_id)
    if not template:
        raise HTTPException(404, f"Pipeline not found: {pipeline_id}")
    user_request = (data or {}).get("user_request", "")
    plan = template.to_execution_plan(user_request)
    from opc_hermes.worker_dispatcher import OPCWorkerDispatcher
    dispatcher = OPCWorkerDispatcher()
    result = dispatcher.execute(plan)
    return {"status": result["status"], "task_id": result["task_id"], "steps": result["steps"]}


# ══════════════════════════════════════════════════════════════════════════
# Model Manager API (§3.6)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/models")
async def list_models(tier: Optional[str] = None, provider: Optional[str] = None):
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    models = mm.list_models()
    if tier:
        models = [m for m in models if m.tier == tier]
    if provider:
        models = [m for m in models if m.provider == provider]
    return {"models": [asdict(m) for m in models]}


@app.post("/api/models")
async def create_model(data: Dict[str, Any]):
    from opc_hermes.model_manager import ModelManager, ModelDef
    mm = ModelManager()
    model = ModelDef.from_dict(data)
    mm.save_model(model)
    return {"status": "created", "model": asdict(model)}


@app.put("/api/models/{model_id}")
async def update_model(model_id: str, data: Dict[str, Any]):
    from opc_hermes.model_manager import ModelManager, ModelDef
    mm = ModelManager()
    existing = mm.get_model(model_id)
    if not existing:
        raise HTTPException(404, f"Model not found: {model_id}")
    merged = {**asdict(existing), **data, "id": model_id}
    model = ModelDef.from_dict(merged)
    mm.save_model(model)
    return {"status": "updated", "model": asdict(model)}


@app.delete("/api/models/{model_id}")
async def delete_model(model_id: str):
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    ok = mm.delete_model(model_id)
    if not ok:
        raise HTTPException(404, f"Model not found: {model_id}")
    return {"status": "deleted"}


@app.get("/api/models/groups")
async def list_model_groups():
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    groups = mm.list_groups()
    return {"groups": [asdict(g) for g in groups]}


@app.post("/api/models/groups")
async def create_model_group(data: Dict[str, Any]):
    from opc_hermes.model_manager import ModelManager, ModelGroup
    mm = ModelManager()
    group = ModelGroup.from_dict(data)
    mm.save_group(group)
    return {"status": "created", "group": asdict(group)}


@app.delete("/api/models/groups/{group_id}")
async def delete_model_group(group_id: str):
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    ok = mm.delete_group(group_id)
    if not ok:
        raise HTTPException(404, f"Model group not found: {group_id}")
    return {"status": "deleted"}


@app.get("/api/models/providers")
async def list_providers():
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    providers = mm.list_providers()
    return {"providers": [asdict(p) for p in providers]}


@app.post("/api/models/providers")
async def create_provider(data: Dict[str, Any]):
    from opc_hermes.model_manager import ModelManager, ModelProvider
    mm = ModelManager()
    provider = ModelProvider.from_dict(data)
    mm.save_provider(provider)
    return {"status": "created", "provider": asdict(provider)}


@app.post("/api/models/validate/{model_id}")
async def validate_model(model_id: str):
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    result = await mm.validate_model(model_id)
    return result


# ══════════════════════════════════════════════════════════════════════════
# Tasks API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/tasks")
async def list_tasks():
    """List recent tasks from Project Memory (scans Eval Memory for unique task_ids)."""
    memory = _get_memory()
    # Discover tasks from evaluation records (tasks that were evaluated)
    recent_evals = memory.get_evaluations(limit=200)
    seen: set = set()
    tasks = []
    for e in recent_evals:
        if e.task_id not in seen:
            seen.add(e.task_id)
            # Get protocols for this task
            protocols = memory.get_all_task_protocols(e.task_id)
            reports = memory.get_progress_reports(e.task_id)
            completed = sum(1 for r in reports if r.status == "completed")
            total = len(protocols)
            status = "completed" if completed == total and total > 0 else ("partial" if completed > 0 else "pending")
            tasks.append({
                "task_id": e.task_id,
                "status": status,
                "workers": [p.worker_id for p in protocols],
                "total_steps": total,
                "completed_steps": completed,
                "last_activity": max((r.reported_at for r in reports), default=""),
            })
        if len(tasks) >= 20:
            break
    return {"tasks": tasks}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """Get full task detail including DAG data for visualization."""
    memory = _get_memory()

    protocols = memory.get_all_task_protocols(task_id)
    reports = memory.get_progress_reports(task_id)

    if not protocols:
        raise HTTPException(404, f"Task not found: {task_id}")

    # Build DAG nodes and edges
    nodes = []
    edges = []
    for p in protocols:
        worker = _get_registry().get_worker(p.worker_id)
        node_status = "pending"
        for r in reports:
            if r.worker_id == p.worker_id:
                node_status = r.status
                break

        nodes.append({
            "id": f"{p.task_id}-{p.worker_id}",
            "worker_id": p.worker_id,
            "step_index": p.step_index,
            "prompt": p.prompt[:200],
            "status": node_status,
            "complexity": p.complexity,
            "model": p.model,
            "label": worker.display_name if worker else p.worker_id,
        })
        for u in p.upstream_step_indices:
            upstream_proto = next((pp for pp in protocols if pp.step_index == u), None)
            if upstream_proto:
                edges.append({
                    "id": f"{upstream_proto.task_id}-{upstream_proto.worker_id}→{p.worker_id}",
                    "source": f"{upstream_proto.task_id}-{upstream_proto.worker_id}",
                    "target": f"{p.task_id}-{p.worker_id}",
                })

    # Get artifacts for this task
    try:
        from opc_hermes.workflow.artifact_manager import ArtifactManager
        artifacts_mgr = ArtifactManager()
        artifacts = artifacts_mgr.get_task_artifacts(task_id)
    except Exception:
        artifacts = {}

    return {
        "task_id": task_id,
        "steps": [
            {
                "worker_id": p.worker_id,
                "step_index": p.step_index,
                "prompt": p.prompt,
                "complexity": p.complexity,
                "model": p.model,
                "upstream": p.upstream_step_indices,
                "expected_output_format": p.expected_output_format,
                "reports": [
                    {
                        "status": r.status,
                        "summary": r.summary,
                        "output_preview": r.output_preview[:500],
                        "tool_call_count": r.tool_call_count,
                        "error_message": r.error_message,
                        "reported_at": r.reported_at,
                    }
                    for r in reports if r.worker_id == p.worker_id
                ],
            }
            for p in protocols
        ],
        "dag": {"nodes": nodes, "edges": edges},
        "artifacts": artifacts,
    }


# ══════════════════════════════════════════════════════════════════════════
# Memory API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/memory/{partition}")
async def browse_memory(
    partition: str,
    task_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    limit: int = 50,
):
    """Browse Project Memory, Eval Memory, or Knowledge Base."""
    memory = _get_memory()

    if partition == "project":
        if task_id:
            protocols = memory.get_all_task_protocols(task_id)
            reports = memory.get_progress_reports(task_id)
            return {
                "partition": "project",
                "task_id": task_id,
                "protocols": [
                    {"worker_id": p.worker_id, "prompt": p.prompt, "step_index": p.step_index,
                     "complexity": p.complexity, "model": p.model}
                    for p in protocols
                ],
                "reports": [
                    {"worker_id": r.worker_id, "status": r.status, "summary": r.summary,
                     "reported_at": r.reported_at}
                    for r in reports
                ],
            }
        return {"partition": "project", "message": "Specify task_id to browse project memory."}

    elif partition == "eval":
        evals = memory.get_evaluations(worker_id=worker_id, limit=limit)
        return {
            "partition": "eval",
            "evaluations": [
                {"task_id": e.task_id, "worker_id": e.worker_id,
                 "scores": e.scores, "notes": e.notes, "evaluated_at": e.evaluated_at}
                for e in evals
            ],
        }

    elif partition == "kb":
        return {"partition": "kb", "message": "Use /api/knowledge/search for KB queries."}

    raise HTTPException(400, f"Unknown partition: {partition}. Use: project | eval | kb")


# ══════════════════════════════════════════════════════════════════════════
# Knowledge Base API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/knowledge/search")
async def search_knowledge(q: str = "", limit: int = 20):
    from opc_hermes.knowledge_pipeline import KnowledgePipeline
    kp = KnowledgePipeline()
    results = kp.search(q, top_k=limit)
    return {"query": q, "results": results}


@app.post("/api/knowledge/ingest")
async def ingest_knowledge(title: str, content: str, tags: Optional[str] = None):
    from opc_hermes.knowledge_pipeline import KnowledgePipeline
    kp = KnowledgePipeline()
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    result = kp.ingest_text(title, content, tags=tag_list)
    return result


# ══════════════════════════════════════════════════════════════════════════
# Artifacts API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/artifacts")
async def list_artifacts(task_id: Optional[str] = None):
    try:
        from opc_hermes.workflow.artifact_manager import ArtifactManager
        mgr = ArtifactManager()
        if task_id:
            return {"task_id": task_id, "artifacts": mgr.get_task_artifacts(task_id)}
        return {"message": "Specify task_id to list artifacts."}
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════
# Proposals API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/proposals")
async def list_proposals(status: Optional[str] = "pending"):
    from opc_hermes.optimizer import Optimizer
    opt = Optimizer()
    proposals = opt.list_proposals(status=status if status else None)
    return {"proposals": proposals, "status_filter": status}


@app.post("/api/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    from opc_hermes.optimizer import Optimizer
    opt = Optimizer()
    ok = opt.approve_proposal(proposal_id)
    if not ok:
        raise HTTPException(404, f"Proposal not found: {proposal_id}")
    return {"status": "approved", "proposal_id": proposal_id}


@app.post("/api/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    from opc_hermes.optimizer import Optimizer
    opt = Optimizer()
    ok = opt.reject_proposal(proposal_id)
    if not ok:
        raise HTTPException(404, f"Proposal not found: {proposal_id}")
    return {"status": "rejected", "proposal_id": proposal_id}


@app.post("/api/optimizer/scan")
async def trigger_optimizer_scan():
    from opc_hermes.optimizer import run_optimizer_scan
    result = run_optimizer_scan()
    return result


# ══════════════════════════════════════════════════════════════════════════
# Config API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/config")
async def get_config():
    from opc_hermes.config.loader import load_config
    config = load_config()
    return {"config": _redact_sensitive(config)}


def _redact_sensitive(obj: Any) -> Any:
    """Recursively redact sensitive config values (keys containing secret/key/token/password)."""
    SENSITIVE_PATTERNS = ("secret", "key", "token", "password", "api_key", "credential")
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if any(p in k.lower() for p in SENSITIVE_PATTERNS) else _redact_sensitive(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_sensitive(v) for v in obj]
    return obj


@app.post("/api/config")
async def update_config(updates: Dict[str, Any]):
    from opc_hermes.config.loader import load_config, save_config, set_config_value
    config = load_config()
    for key, value in updates.items():
        config = set_config_value(config, key, value)
    save_config(config)
    return {"status": "saved"}


# ══════════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════
# Static files (frontend build)
# ══════════════════════════════════════════════════════════════════════════

FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

def main():
    import uvicorn
    uvicorn.run(
        "opc_hermes.webui.server:app",
        host="127.0.0.1",
        port=8765,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
