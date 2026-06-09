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
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from fastapi import Body, FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException as StarletteHTTPException
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    Body = None  # type: ignore
    FastAPI = None  # type: ignore
    HTTPException = Exception  # type: ignore
    Request = None  # type: ignore
    CORSMiddleware = None  # type: ignore
    Response = None  # type: ignore
    StreamingResponse = None  # type: ignore
    StaticFiles = None  # type: ignore
    StarletteHTTPException = Exception  # type: ignore

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

_HERMES_WEB_SERVER: Any = None


def _mount_hermes_api() -> None:
    """Mount Hermes Agent's native dashboard API in this FastAPI process.

    OPC-Hermes serves its own React app, but the dashboard should reuse Hermes
    Agent's native operational capabilities without starting a second frontend.
    Mounting the API under an internal prefix keeps OPC's /api routes stable.
    """
    project_root = Path(__file__).resolve().parents[2]
    hermes_root = project_root / "hermes-agent"
    if not hermes_root.exists():
        logger.warning("Hermes Agent source not found at %s; native API not mounted", hermes_root)
        return
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    try:
        from hermes_cli import web_server as hermes_web_server  # type: ignore
    except Exception:
        logger.exception("Failed to import Hermes Agent Web API")
        return

    global _HERMES_WEB_SERVER
    _HERMES_WEB_SERVER = hermes_web_server
    hermes_web_server._DASHBOARD_EMBEDDED_CHAT_ENABLED = True
    hermes_app = hermes_web_server.app
    hermes_app.state.auth_required = False
    hermes_app.state.bound_host = os.environ.get("OPC_WEBUI_HOST", "127.0.0.1")
    hermes_app.state.bound_port = int(os.environ.get("OPC_WEBUI_PORT", "8765"))
    app.mount("/hermes-api", hermes_app)


_mount_hermes_api()


@app.get("/api/hermes/chat-config")
async def hermes_chat_config():
    """Return the local WebSocket config needed for native Hermes Chat."""
    if _HERMES_WEB_SERVER is None:
        raise HTTPException(503, "Hermes Agent Web API is not mounted")
    return {
        "enabled": bool(getattr(_HERMES_WEB_SERVER, "_DASHBOARD_EMBEDDED_CHAT_ENABLED", False)),
        "token": getattr(_HERMES_WEB_SERVER, "_SESSION_TOKEN", ""),
        "pty_path": "/hermes-api/api/pty",
        "events_path": "/hermes-api/api/events",
    }


def _load_hermes_env() -> Dict[str, str]:
    try:
        from hermes_cli.config import load_env

        return load_env()
    except Exception:
        return {}


def _resolve_secret_ref(value: str) -> str:
    env_name = _env_ref_name(value)
    if not env_name:
        return ""
    return os.environ.get(env_name, "") or _load_hermes_env().get(env_name, "")


def _chat_completions_url(api_base: str) -> str:
    base = (api_base or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _gateway_chat_target(model_id: str) -> Optional[Dict[str, Any]]:
    explicit_url = os.environ.get("OPC_HERMES_API_SERVER_URL", "").strip()
    if not explicit_url and model_id not in {"hermes-agent", "hermes"}:
        return None

    if explicit_url:
        url = explicit_url
    else:
        port = os.environ.get("API_SERVER_PORT", "8642")
        url = f"http://127.0.0.1:{port}/v1/chat/completions"

    api_key = (
        os.environ.get("OPC_HERMES_API_KEY", "")
        or os.environ.get("API_SERVER_KEY", "")
        or _load_hermes_env().get("API_SERVER_KEY", "")
    )
    return {"url": url, "api_key": api_key}


def _model_disables_chat_stream(model: Any) -> bool:
    capabilities = getattr(model, "capabilities", {}) or {}
    return bool(capabilities.get("image_gen"))


def _is_sse_unsupported_error(body: bytes) -> bool:
    text = body.decode("utf-8", errors="ignore").lower()
    return "sse" in text and ("not support" in text or "unsupported" in text)


def _model_chat_target(payload: Dict[str, Any]) -> Dict[str, Any]:
    model_id = str(payload.get("model", "") or "").strip()
    if not model_id:
        raise HTTPException(400, "model is required")

    gateway_target = _gateway_chat_target(model_id)
    if gateway_target is not None:
        return gateway_target

    from opc_hermes.model_manager import ModelManager

    mm = ModelManager()
    model = mm.get_model(model_id)
    if not model:
        raise HTTPException(404, f"Model not found: {model_id}")

    provider = next((p for p in mm.list_providers() if p.id == model.provider), None)
    api_base = (model.api_base or (provider.api_base if provider else "") or "").strip()
    if not api_base:
        raise HTTPException(400, f"Model '{model_id}' has no API base configured")

    api_key_ref = model.api_key_ref or (provider.api_key_ref if provider else "") or ""
    api_key = _resolve_secret_ref(api_key_ref)
    if not api_key and not _is_local_provider(model.provider, api_base):
        env_name = _env_ref_name(api_key_ref) or _default_api_key_env(model.provider)
        raise HTTPException(400, f"API key is not configured for model '{model_id}' ({env_name})")

    return {
        "url": _chat_completions_url(api_base),
        "api_key": api_key,
        "disable_stream": _model_disables_chat_stream(model),
    }


@app.post("/api/chat/completions")
async def chat_completions(request: Request):
    """Proxy chat completion requests to the selected OpenAI-compatible model."""
    import httpx

    body = await request.body()
    try:
        payload = json.loads(body.decode("utf-8") if body else "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid JSON in request body")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Request body must be a JSON object")

    target = _model_chat_target(payload)
    upstream_body = body
    stream_disabled = bool(target.get("disable_stream") and payload.get("stream"))
    if stream_disabled:
        upstream_payload = dict(payload)
        upstream_payload["stream"] = False
        upstream_body = json.dumps(upstream_payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }
    if request.headers.get("Accept") and not stream_disabled:
        headers["Accept"] = request.headers["Accept"]
    if target.get("api_key"):
        headers["Authorization"] = f"Bearer {target['api_key']}"
    elif request.headers.get("Authorization"):
        headers["Authorization"] = request.headers["Authorization"]

    client: Optional[httpx.AsyncClient] = None
    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0), proxy=None)
        proxy_req = client.build_request(
            "POST",
            target["url"],
            content=upstream_body,
            headers=headers,
        )
        proxy_resp = await client.send(proxy_req, stream=True)

        content_type = proxy_resp.headers.get("content-type", "")
        if content_type.lower().startswith("text/event-stream"):
            async def iter_proxy_stream():
                try:
                    async for chunk in proxy_resp.aiter_bytes():
                        yield chunk
                finally:
                    await proxy_resp.aclose()
                    await client.aclose()

            return StreamingResponse(
                iter_proxy_stream(),
                status_code=proxy_resp.status_code,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            )

        try:
            body_bytes = await proxy_resp.aread()
            status_code = proxy_resp.status_code
            response_content_type = content_type
            if (
                status_code in {400, 422}
                and payload.get("stream")
                and not stream_disabled
                and _is_sse_unsupported_error(body_bytes)
            ):
                await proxy_resp.aclose()
                retry_payload = dict(payload)
                retry_payload["stream"] = False
                retry_req = client.build_request(
                    "POST",
                    target["url"],
                    content=json.dumps(retry_payload, ensure_ascii=False).encode("utf-8"),
                    headers={key: value for key, value in headers.items() if key.lower() != "accept"},
                )
                proxy_resp = await client.send(retry_req, stream=True)
                response_content_type = proxy_resp.headers.get("content-type", "")
                body_bytes = await proxy_resp.aread()
                status_code = proxy_resp.status_code
            return Response(
                content=body_bytes,
                status_code=status_code,
                headers={"Content-Type": response_content_type or "application/json"},
            )
        finally:
            await proxy_resp.aclose()
            await client.aclose()
    except httpx.ConnectError:
        if client is not None:
            await client.aclose()
        raise HTTPException(503, f"Upstream chat API is not reachable: {target['url']}")
    except httpx.TimeoutException:
        if client is not None:
            await client.aclose()
        raise HTTPException(504, "Upstream chat API timed out")
    except httpx.RequestError as exc:
        if client is not None:
            await client.aclose()
        raise HTTPException(502, f"Upstream chat API request failed: {exc}")


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
        "default_provider": getattr(w, "default_provider", ""),
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
# Analytics
# ══════════════════════════════════════════════════════════════════════════

def _analytics_days(days: int) -> int:
    try:
        parsed = int(days)
    except (TypeError, ValueError):
        parsed = 30
    return max(1, min(parsed, 365))


def _ensure_hermes_import_path() -> bool:
    hermes_root = Path(__file__).resolve().parents[2] / "hermes-agent"
    if not hermes_root.exists():
        return False
    hermes_root_str = str(hermes_root)
    if hermes_root_str not in sys.path:
        sys.path.insert(0, hermes_root_str)
    return True


def _sqlite_rows(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        numeric = float(raw)
        if numeric > 1000000000:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_or_empty(value: Optional[datetime]) -> str:
    return value.astimezone(timezone.utc).isoformat() if value else ""


def _day_key(value: Any) -> str:
    parsed = _parse_timestamp(value)
    return parsed.date().isoformat() if parsed else ""


def _load_scores(value: Any) -> Dict[str, float]:
    if isinstance(value, dict):
        raw = value
    else:
        try:
            raw = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            raw = {}
    return {str(k): _to_float(v) for k, v in raw.items() if isinstance(v, (int, float))}


def _overall_score(scores: Dict[str, float]) -> Optional[float]:
    if "quality" in scores:
        return scores["quality"]
    if "overall" in scores:
        return scores["overall"]
    values = [v for v in scores.values() if isinstance(v, (int, float))]
    if not values:
        return None
    return sum(values) / len(values)


def _empty_usage(days: int, source: str = "empty") -> Dict[str, Any]:
    return {
        "daily": [],
        "by_model": [],
        "totals": {
            "total_input": 0,
            "total_output": 0,
            "total_cache_read": 0,
            "total_reasoning": 0,
            "total_estimated_cost": 0.0,
            "total_actual_cost": 0.0,
            "total_sessions": 0,
            "total_api_calls": 0,
        },
        "period_days": days,
        "skills": {
            "summary": {
                "total_skill_loads": 0,
                "total_skill_edits": 0,
                "total_skill_actions": 0,
                "distinct_skills_used": 0,
            },
            "top_skills": [],
        },
        "source": source,
    }


def _empty_model_analytics(days: int, source: str = "empty") -> Dict[str, Any]:
    return {
        "models": [],
        "totals": {
            "distinct_models": 0,
            "total_input": 0,
            "total_output": 0,
            "total_cache_read": 0,
            "total_reasoning": 0,
            "total_estimated_cost": 0.0,
            "total_actual_cost": 0.0,
            "total_sessions": 0,
            "total_api_calls": 0,
        },
        "period_days": days,
        "source": source,
    }


def _hermes_usage_analytics(days: int) -> tuple[Dict[str, Any], Optional[str]]:
    if not _ensure_hermes_import_path():
        return _empty_usage(days, "opc-fallback"), "Hermes Agent source is not available"

    try:
        from hermes_state import SessionDB
    except Exception as exc:
        return _empty_usage(days, "opc-fallback"), f"Hermes SessionDB is not available: {exc}"

    db = None
    try:
        db = SessionDB()
        cutoff = time.time() - (days * 86400)
        daily = []
        for raw in db._conn.execute(
            """
            SELECT date(started_at, 'unixepoch') as day,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(cache_read_tokens) as cache_read_tokens,
                   SUM(reasoning_tokens) as reasoning_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0) as estimated_cost,
                   COALESCE(SUM(actual_cost_usd), 0) as actual_cost,
                   COUNT(*) as sessions,
                   SUM(COALESCE(api_call_count, 0)) as api_calls
            FROM sessions WHERE started_at > ?
            GROUP BY day ORDER BY day
            """,
            (cutoff,),
        ).fetchall():
            row = dict(raw)
            daily.append({
                "day": row.get("day") or "",
                "input_tokens": _to_int(row.get("input_tokens")),
                "output_tokens": _to_int(row.get("output_tokens")),
                "cache_read_tokens": _to_int(row.get("cache_read_tokens")),
                "reasoning_tokens": _to_int(row.get("reasoning_tokens")),
                "estimated_cost": _to_float(row.get("estimated_cost")),
                "actual_cost": _to_float(row.get("actual_cost")),
                "sessions": _to_int(row.get("sessions")),
                "api_calls": _to_int(row.get("api_calls")),
            })
        by_model = []
        for raw in db._conn.execute(
            """
            SELECT model,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0) as estimated_cost,
                   COUNT(*) as sessions,
                   SUM(COALESCE(api_call_count, 0)) as api_calls
            FROM sessions WHERE started_at > ? AND model IS NOT NULL AND model != ''
            GROUP BY model ORDER BY SUM(input_tokens) + SUM(output_tokens) DESC
            """,
            (cutoff,),
        ).fetchall():
            row = dict(raw)
            by_model.append({
                "model": row.get("model") or "unknown",
                "input_tokens": _to_int(row.get("input_tokens")),
                "output_tokens": _to_int(row.get("output_tokens")),
                "estimated_cost": _to_float(row.get("estimated_cost")),
                "sessions": _to_int(row.get("sessions")),
                "api_calls": _to_int(row.get("api_calls")),
            })
        totals_row = db._conn.execute(
            """
            SELECT SUM(input_tokens) as total_input,
                   SUM(output_tokens) as total_output,
                   SUM(cache_read_tokens) as total_cache_read,
                   SUM(reasoning_tokens) as total_reasoning,
                   COALESCE(SUM(estimated_cost_usd), 0) as total_estimated_cost,
                   COALESCE(SUM(actual_cost_usd), 0) as total_actual_cost,
                   COUNT(*) as total_sessions,
                   SUM(COALESCE(api_call_count, 0)) as total_api_calls
            FROM sessions WHERE started_at > ?
            """,
            (cutoff,),
        ).fetchone()
        totals = {
            "total_input": _to_int(totals_row["total_input"] if totals_row else 0),
            "total_output": _to_int(totals_row["total_output"] if totals_row else 0),
            "total_cache_read": _to_int(totals_row["total_cache_read"] if totals_row else 0),
            "total_reasoning": _to_int(totals_row["total_reasoning"] if totals_row else 0),
            "total_estimated_cost": _to_float(totals_row["total_estimated_cost"] if totals_row else 0),
            "total_actual_cost": _to_float(totals_row["total_actual_cost"] if totals_row else 0),
            "total_sessions": _to_int(totals_row["total_sessions"] if totals_row else 0),
            "total_api_calls": _to_int(totals_row["total_api_calls"] if totals_row else 0),
        }
        skills = _empty_usage(days)["skills"]
        try:
            from agent.insights import InsightsEngine

            insights = InsightsEngine(db).generate(days=days)
            skills = insights.get("skills") or skills
        except Exception:
            pass
        return {
            "daily": daily,
            "by_model": by_model,
            "totals": totals,
            "period_days": days,
            "skills": skills,
            "source": "hermes-state",
        }, None
    except Exception as exc:
        logger.exception("Failed to load Hermes usage analytics")
        return _empty_usage(days, "opc-fallback"), f"Hermes usage analytics failed: {exc}"
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _model_capabilities(provider: str, model: str) -> Dict[str, Any]:
    if not _ensure_hermes_import_path():
        return {}
    try:
        from agent.models_dev import get_model_capabilities

        caps = get_model_capabilities(provider=provider or "", model=model)
        if caps is None:
            return {}
        return {
            "supports_tools": caps.supports_tools,
            "supports_vision": caps.supports_vision,
            "supports_reasoning": caps.supports_reasoning,
            "context_window": caps.context_window,
            "max_output_tokens": caps.max_output_tokens,
            "model_family": caps.model_family,
        }
    except Exception:
        return {}


def _hermes_model_analytics(days: int) -> tuple[Dict[str, Any], Optional[str]]:
    if not _ensure_hermes_import_path():
        return _empty_model_analytics(days, "opc-fallback"), "Hermes Agent source is not available"

    try:
        from hermes_state import SessionDB
    except Exception as exc:
        return _empty_model_analytics(days, "opc-fallback"), f"Hermes SessionDB is not available: {exc}"

    db = None
    try:
        db = SessionDB()
        cutoff = time.time() - (days * 86400)
        rows = db._conn.execute(
            """
            SELECT model,
                   billing_provider,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(cache_read_tokens) as cache_read_tokens,
                   SUM(reasoning_tokens) as reasoning_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0) as estimated_cost,
                   COALESCE(SUM(actual_cost_usd), 0) as actual_cost,
                   COUNT(*) as sessions,
                   SUM(COALESCE(api_call_count, 0)) as api_calls,
                   SUM(tool_call_count) as tool_calls,
                   MAX(started_at) as last_used_at,
                   AVG(input_tokens + output_tokens) as avg_tokens_per_session
            FROM sessions WHERE started_at > ? AND model IS NOT NULL AND model != ''
            GROUP BY model, billing_provider
            ORDER BY SUM(input_tokens) + SUM(output_tokens) DESC
            """,
            (cutoff,),
        ).fetchall()
        models = []
        for row in rows:
            provider = row["billing_provider"] or ""
            model = row["model"] or "unknown"
            models.append({
                "model": model,
                "provider": provider,
                "input_tokens": _to_int(row["input_tokens"]),
                "output_tokens": _to_int(row["output_tokens"]),
                "cache_read_tokens": _to_int(row["cache_read_tokens"]),
                "reasoning_tokens": _to_int(row["reasoning_tokens"]),
                "estimated_cost": _to_float(row["estimated_cost"]),
                "actual_cost": _to_float(row["actual_cost"]),
                "sessions": _to_int(row["sessions"]),
                "api_calls": _to_int(row["api_calls"]),
                "tool_calls": _to_int(row["tool_calls"]),
                "last_used_at": row["last_used_at"],
                "avg_tokens_per_session": _to_float(row["avg_tokens_per_session"]),
                "capabilities": _model_capabilities(provider, model),
            })
        totals_row = db._conn.execute(
            """
            SELECT COUNT(DISTINCT model) as distinct_models,
                   SUM(input_tokens) as total_input,
                   SUM(output_tokens) as total_output,
                   SUM(cache_read_tokens) as total_cache_read,
                   SUM(reasoning_tokens) as total_reasoning,
                   COALESCE(SUM(estimated_cost_usd), 0) as total_estimated_cost,
                   COALESCE(SUM(actual_cost_usd), 0) as total_actual_cost,
                   COUNT(*) as total_sessions,
                   SUM(COALESCE(api_call_count, 0)) as total_api_calls
            FROM sessions WHERE started_at > ? AND model IS NOT NULL AND model != ''
            """,
            (cutoff,),
        ).fetchone()
        totals = {
            "distinct_models": _to_int(totals_row["distinct_models"] if totals_row else 0),
            "total_input": _to_int(totals_row["total_input"] if totals_row else 0),
            "total_output": _to_int(totals_row["total_output"] if totals_row else 0),
            "total_cache_read": _to_int(totals_row["total_cache_read"] if totals_row else 0),
            "total_reasoning": _to_int(totals_row["total_reasoning"] if totals_row else 0),
            "total_estimated_cost": _to_float(totals_row["total_estimated_cost"] if totals_row else 0),
            "total_actual_cost": _to_float(totals_row["total_actual_cost"] if totals_row else 0),
            "total_sessions": _to_int(totals_row["total_sessions"] if totals_row else 0),
            "total_api_calls": _to_int(totals_row["total_api_calls"] if totals_row else 0),
        }
        return {"models": models, "totals": totals, "period_days": days, "source": "hermes-state"}, None
    except Exception as exc:
        logger.exception("Failed to load Hermes model analytics")
        return _empty_model_analytics(days, "opc-fallback"), f"Hermes model analytics failed: {exc}"
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _opc_analytics(days: int) -> Dict[str, Any]:
    memory = _get_memory()
    registry = _get_registry()
    workers = registry.list_workers()
    worker_lookup = {w.id: w for w in workers}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    protocols = _sqlite_rows(
        memory.project_db,
        "SELECT * FROM task_protocols ORDER BY created_at DESC",
    )
    reports = _sqlite_rows(
        memory.project_db,
        "SELECT * FROM progress_reports ORDER BY reported_at DESC",
    )
    evaluations = _sqlite_rows(
        memory.eval_db,
        "SELECT * FROM evaluations ORDER BY evaluated_at DESC",
    )

    activity_by_task: Dict[str, Optional[datetime]] = {}

    def mark_task(task_id: str, timestamp: Any) -> None:
        if not task_id:
            return
        parsed = _parse_timestamp(timestamp)
        current = activity_by_task.get(task_id)
        if current is None or (parsed is not None and parsed > current):
            activity_by_task[task_id] = parsed

    for row in protocols:
        mark_task(str(row.get("task_id") or ""), row.get("created_at"))
    for row in reports:
        mark_task(str(row.get("task_id") or ""), row.get("reported_at"))
    for row in evaluations:
        mark_task(str(row.get("task_id") or ""), row.get("evaluated_at"))

    period_task_ids = {
        task_id
        for task_id, timestamp in activity_by_task.items()
        if timestamp is None or timestamp >= cutoff
    }

    protocols_by_task: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    reports_by_task: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    evals_by_task: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in protocols:
        task_id = str(row.get("task_id") or "")
        if task_id in period_task_ids:
            protocols_by_task[task_id].append(row)
    for row in reports:
        task_id = str(row.get("task_id") or "")
        if task_id in period_task_ids:
            reports_by_task[task_id].append(row)
    for row in evaluations:
        task_id = str(row.get("task_id") or "")
        if task_id in period_task_ids:
            evals_by_task[task_id].append(row)

    latest_report: Dict[tuple[str, str], Dict[str, Any]] = {}
    for row in sorted(reports, key=lambda r: _parse_timestamp(r.get("reported_at")) or datetime.min.replace(tzinfo=timezone.utc)):
        key = (str(row.get("task_id") or ""), str(row.get("worker_id") or ""))
        if key[0] in period_task_ids:
            latest_report[key] = row

    task_status_counts = Counter()
    recent_tasks: List[Dict[str, Any]] = []
    for task_id in period_task_ids:
        task_protocols = protocols_by_task.get(task_id, [])
        task_reports = reports_by_task.get(task_id, [])
        task_evals = evals_by_task.get(task_id, [])
        worker_ids = {
            str(row.get("worker_id") or "")
            for row in [*task_protocols, *task_reports, *task_evals]
            if row.get("worker_id")
        }
        statuses = [
            str(row.get("status") or "")
            for (report_task_id, _), row in latest_report.items()
            if report_task_id == task_id
        ]
        completed_steps = sum(1 for status in statuses if status == "completed")
        total_steps = len(task_protocols) or len(worker_ids)
        if any(status == "failed" for status in statuses):
            status = "failed"
        elif any(status == "blocked" for status in statuses):
            status = "blocked"
        elif total_steps > 0 and completed_steps >= total_steps:
            status = "completed"
        elif any(status == "in_progress" for status in statuses):
            status = "active"
        elif completed_steps > 0 or task_reports:
            status = "partial"
        else:
            status = "pending"
        task_status_counts[status] += 1
        latest = activity_by_task.get(task_id)
        recent_tasks.append({
            "task_id": task_id,
            "status": status,
            "workers": sorted(worker_ids),
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "tool_calls": sum(_to_int(row.get("tool_call_count")) for row in task_reports),
            "evaluations": len(task_evals),
            "last_activity": _iso_or_empty(latest),
        })

    recent_tasks.sort(key=lambda item: item.get("last_activity") or "", reverse=True)

    worker_metrics: Dict[str, Dict[str, Any]] = {}
    for worker in workers:
        worker_metrics[worker.id] = {
            "worker_id": worker.id,
            "display_name": worker.display_name,
            "role": worker.role,
            "model": worker.default_model,
            "provider": getattr(worker, "default_provider", ""),
            "tasks": set(),
            "reports": 0,
            "completed_reports": 0,
            "failed_reports": 0,
            "active_reports": 0,
            "tool_calls": 0,
            "scores": [],
            "last_activity": None,
        }

    def worker_row(worker_id: str) -> Dict[str, Any]:
        if worker_id not in worker_metrics:
            worker = worker_lookup.get(worker_id)
            worker_metrics[worker_id] = {
                "worker_id": worker_id,
                "display_name": worker.display_name if worker else worker_id,
                "role": worker.role if worker else "worker",
                "model": worker.default_model if worker else "",
                "provider": getattr(worker, "default_provider", "") if worker else "",
                "tasks": set(),
                "reports": 0,
                "completed_reports": 0,
                "failed_reports": 0,
                "active_reports": 0,
                "tool_calls": 0,
                "scores": [],
                "last_activity": None,
            }
        return worker_metrics[worker_id]

    for row in protocols:
        task_id = str(row.get("task_id") or "")
        if task_id not in period_task_ids:
            continue
        worker_id = str(row.get("worker_id") or "")
        if not worker_id:
            continue
        metric = worker_row(worker_id)
        metric["tasks"].add(task_id)
        parsed = _parse_timestamp(row.get("created_at"))
        if parsed and (metric["last_activity"] is None or parsed > metric["last_activity"]):
            metric["last_activity"] = parsed

    for row in reports:
        task_id = str(row.get("task_id") or "")
        if task_id not in period_task_ids:
            continue
        worker_id = str(row.get("worker_id") or "")
        if not worker_id:
            continue
        metric = worker_row(worker_id)
        metric["tasks"].add(task_id)
        metric["reports"] += 1
        metric["tool_calls"] += _to_int(row.get("tool_call_count"))
        status = str(row.get("status") or "")
        if status == "completed":
            metric["completed_reports"] += 1
        elif status == "failed":
            metric["failed_reports"] += 1
        elif status == "in_progress":
            metric["active_reports"] += 1
        parsed = _parse_timestamp(row.get("reported_at"))
        if parsed and (metric["last_activity"] is None or parsed > metric["last_activity"]):
            metric["last_activity"] = parsed

    score_dimensions: Dict[str, List[float]] = defaultdict(list)
    for row in evaluations:
        task_id = str(row.get("task_id") or "")
        if task_id not in period_task_ids:
            continue
        worker_id = str(row.get("worker_id") or "")
        scores = _load_scores(row.get("scores"))
        overall = _overall_score(scores)
        if worker_id and overall is not None:
            metric = worker_row(worker_id)
            metric["scores"].append(overall)
            parsed = _parse_timestamp(row.get("evaluated_at"))
            if parsed and (metric["last_activity"] is None or parsed > metric["last_activity"]):
                metric["last_activity"] = parsed
        for key, value in scores.items():
            score_dimensions[key].append(value)

    worker_activity = []
    for metric in worker_metrics.values():
        scores = metric.pop("scores")
        tasks = metric.pop("tasks")
        worker_activity.append({
            **metric,
            "tasks": len(tasks),
            "avg_quality": round(sum(scores) / len(scores), 3) if scores else None,
            "last_activity": _iso_or_empty(metric.pop("last_activity")),
        })
    worker_activity.sort(
        key=lambda row: (row["tasks"], row["reports"], row["avg_quality"] or 0),
        reverse=True,
    )

    model_provider: Dict[str, str] = {}
    try:
        from opc_hermes.model_manager import ModelManager

        mm = ModelManager()
        model_provider = {model.id: model.provider for model in mm.list_models()}
    except Exception:
        model_provider = {}

    model_rows: Dict[str, Dict[str, Any]] = {}

    def model_metric(model_id: str, provider: str = "") -> Dict[str, Any]:
        clean_model = model_id or "unassigned"
        if clean_model not in model_rows:
            model_rows[clean_model] = {
                "model": clean_model,
                "provider": provider or model_provider.get(clean_model, ""),
                "agents": set(),
                "workers": set(),
                "tasks": set(),
                "tool_calls": 0,
            }
        return model_rows[clean_model]

    for worker in workers:
        if worker.default_model:
            metric = model_metric(worker.default_model, getattr(worker, "default_provider", ""))
            metric["agents"].add(worker.id)
            metric["workers"].add(worker.id)

    reports_by_task_worker = defaultdict(list)
    for row in reports:
        reports_by_task_worker[(str(row.get("task_id") or ""), str(row.get("worker_id") or ""))].append(row)

    for row in protocols:
        task_id = str(row.get("task_id") or "")
        if task_id not in period_task_ids:
            continue
        worker_id = str(row.get("worker_id") or "")
        worker = worker_lookup.get(worker_id)
        model_id = str(row.get("model") or (worker.default_model if worker else "") or "unassigned")
        metric = model_metric(model_id, getattr(worker, "default_provider", "") if worker else "")
        metric["tasks"].add(task_id)
        metric["workers"].add(worker_id)
        metric["tool_calls"] += sum(_to_int(r.get("tool_call_count")) for r in reports_by_task_worker[(task_id, worker_id)])

    model_assignments = []
    for metric in model_rows.values():
        model_assignments.append({
            "model": metric["model"],
            "provider": metric["provider"],
            "agents": len(metric["agents"]),
            "workers": len(metric["workers"]),
            "tasks": len(metric["tasks"]),
            "tool_calls": metric["tool_calls"],
        })
    model_assignments.sort(key=lambda row: (row["tasks"], row["agents"], row["tool_calls"]), reverse=True)

    daily_activity: Dict[str, Dict[str, int]] = defaultdict(lambda: {
        "tasks_created": 0,
        "reports": 0,
        "evaluations": 0,
        "tool_calls": 0,
    })
    for row in protocols:
        day = _day_key(row.get("created_at"))
        if day and str(row.get("task_id") or "") in period_task_ids:
            daily_activity[day]["tasks_created"] += 1
    for row in reports:
        day = _day_key(row.get("reported_at"))
        if day and str(row.get("task_id") or "") in period_task_ids:
            daily_activity[day]["reports"] += 1
            daily_activity[day]["tool_calls"] += _to_int(row.get("tool_call_count"))
    for row in evaluations:
        day = _day_key(row.get("evaluated_at"))
        if day and str(row.get("task_id") or "") in period_task_ids:
            daily_activity[day]["evaluations"] += 1

    quality_scores = [
        _overall_score(_load_scores(row.get("scores")))
        for row in evaluations
        if str(row.get("task_id") or "") in period_task_ids
    ]
    quality_scores = [score for score in quality_scores if score is not None]
    quality_trend = []
    for row in sorted(evaluations, key=lambda r: r.get("evaluated_at") or ""):
        if str(row.get("task_id") or "") not in period_task_ids:
            continue
        score = _overall_score(_load_scores(row.get("scores")))
        if score is None:
            continue
        quality_trend.append({
            "date": row.get("evaluated_at") or "",
            "worker_id": row.get("worker_id") or "",
            "score": round(score, 3),
        })

    return {
        "period_days": days,
        "source": "opc-memory",
        "task_totals": {
            "total": len(period_task_ids),
            "completed": task_status_counts["completed"],
            "active": task_status_counts["active"],
            "partial": task_status_counts["partial"],
            "pending": task_status_counts["pending"],
            "failed": task_status_counts["failed"],
            "blocked": task_status_counts["blocked"],
        },
        "agent_totals": {
            "total": len(workers),
            "leader": sum(1 for worker in workers if worker.role == "leader"),
            "worker": sum(1 for worker in workers if worker.role == "worker"),
            "evaluator": sum(1 for worker in workers if worker.role == "evaluator"),
        },
        "evaluations_total": len([row for row in evaluations if str(row.get("task_id") or "") in period_task_ids]),
        "avg_quality": round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else None,
        "tool_calls": sum(_to_int(row.get("tool_call_count")) for row in reports if str(row.get("task_id") or "") in period_task_ids),
        "daily_activity": [
            {"day": day, **values}
            for day, values in sorted(daily_activity.items())
        ],
        "score_dimensions": [
            {"key": key, "avg": round(sum(values) / len(values), 3), "count": len(values)}
            for key, values in sorted(score_dimensions.items())
            if values
        ],
        "quality_trend": quality_trend[-60:],
        "recent_tasks": recent_tasks[:12],
        "worker_activity": worker_activity[:20],
        "model_assignments": model_assignments[:20],
    }


def _analytics_payload(days: int) -> Dict[str, Any]:
    period_days = _analytics_days(days)
    usage, usage_warning = _hermes_usage_analytics(period_days)
    models, model_warning = _hermes_model_analytics(period_days)
    warnings = [warning for warning in (usage_warning, model_warning) if warning]
    return {
        "period_days": period_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "usage": usage.get("source", "unknown"),
            "models": models.get("source", "unknown"),
            "opc": "opc-memory",
            "warnings": warnings,
        },
        "usage": usage,
        "models": models,
        "opc": _opc_analytics(period_days),
    }


@app.get("/api/analytics")
async def analytics(days: int = 30):
    """Return combined Hermes usage/model analytics and OPC workflow metrics."""
    return _analytics_payload(days)


@app.get("/api/analytics/usage")
async def analytics_usage(days: int = 30):
    """Return Hermes token/cost usage analytics with an empty fallback."""
    return _analytics_payload(days)["usage"]


@app.get("/api/analytics/models")
async def analytics_models(days: int = 30):
    """Return Hermes model usage analytics with an empty fallback."""
    return _analytics_payload(days)["models"]


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


@app.post("/api/agents/{agent_id}/model")
async def update_agent_model(agent_id: str, data: Dict[str, Any] = Body(...)):
    """Persist the default model assignment for one OPC agent."""
    registry = _get_registry()
    worker = registry.get_worker(agent_id)
    if not worker:
        raise HTTPException(404, f"Agent not found: {agent_id}")

    provider = str(data.get("provider", "") or "").strip()
    model = str(data.get("model", "") or "").strip()
    tier = str(data.get("model_tier", worker.model_tier or "standard") or "standard").strip()
    if tier not in {"budget", "standard", "premium"}:
        raise HTTPException(400, "model_tier must be one of: budget, standard, premium")

    worker.default_provider = provider
    worker.default_model = model
    worker.model_tier = tier
    registry.register_worker(worker)
    return {"ok": True, "agent": _worker_to_dict(worker)}


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


_LOCAL_MODEL_PROFILES = [
    {"id": "ollama", "name": "Ollama", "api_base": "http://localhost:11434/v1"},
    {"id": "lmstudio", "name": "LM Studio", "api_base": "http://localhost:1234/v1"},
    {"id": "vllm", "name": "vLLM", "api_base": "http://localhost:8000/v1"},
    {"id": "localai", "name": "LocalAI", "api_base": "http://localhost:8080/v1"},
    {"id": "llamacpp", "name": "llama.cpp Server", "api_base": "http://localhost:8081/v1"},
]


def _clean_slug(value: str) -> str:
    import re

    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip().lower())
    cleaned = cleaned.strip("-._")
    return cleaned


def _env_ref_name(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("${") and raw.endswith("}"):
        return raw[2:-1].strip()
    if raw.startswith("$"):
        return raw[1:].strip()
    return raw


def _default_api_key_env(provider_id: str, existing: str = "") -> str:
    existing = _env_ref_name(existing)
    if existing:
        return existing
    cleaned = (provider_id or "custom").upper().replace("-", "_").replace(".", "_")
    return f"{cleaned}_API_KEY"


def _is_local_provider(provider_id: str, api_base: str) -> bool:
    from urllib.parse import urlparse

    if provider_id in {p["id"] for p in _LOCAL_MODEL_PROFILES}:
        return True
    try:
        host = (urlparse(api_base).hostname or "").lower()
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _provider_entry_base_url(entry: Dict[str, Any]) -> str:
    for key in ("base_url", "api", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _model_meta_from_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    context_length = data.get("context_length")
    if isinstance(context_length, int) and context_length > 0:
        meta["context_length"] = context_length
    capabilities = data.get("capabilities")
    if isinstance(capabilities, dict):
        meta["capabilities"] = capabilities
    return meta


_MODELS_DEV_PROVIDER_ALIASES = {
    "openai-api": "openai",
    "google-gemini-cli": "google",
    "moonshot": "kimi-for-coding",
    "novita": "novita-ai",
    "kilocode": "kilo",
}


def _models_dev_provider_id(provider_id: str) -> str:
    try:
        from agent.models_dev import PROVIDER_TO_MODELS_DEV

        return _MODELS_DEV_PROVIDER_ALIASES.get(provider_id) or PROVIDER_TO_MODELS_DEV.get(provider_id, provider_id)
    except Exception:
        return _MODELS_DEV_PROVIDER_ALIASES.get(provider_id, provider_id)


def _models_dev_include_model(provider_id: str, model_id: str, raw: Dict[str, Any]) -> bool:
    if not isinstance(raw, dict):
        return False
    if str(raw.get("status") or "").lower() == "deprecated":
        return False
    modalities = raw.get("modalities") if isinstance(raw.get("modalities"), dict) else {}
    input_mods = modalities.get("input") if isinstance(modalities, dict) else None
    output_mods = modalities.get("output") if isinstance(modalities, dict) else None
    if isinstance(input_mods, list) and "text" not in input_mods:
        return False
    if isinstance(output_mods, list) and "text" not in output_mods:
        return False
    if raw.get("tool_call") is False:
        return False
    model_lower = model_id.lower()
    noise = ("embedding", "moderation", "tts", "transcribe", "whisper", "rerank")
    if any(part in model_lower for part in noise):
        return False
    try:
        from agent.models_dev import _should_hide_from_provider_catalog

        if _should_hide_from_provider_catalog(provider_id, model_id):
            return False
    except Exception:
        pass
    return True


def _models_dev_sort_key(item: tuple[str, Dict[str, Any]]) -> tuple[str, str, int, str]:
    model_id, raw = item
    released = str(raw.get("release_date") or "")
    updated = str(raw.get("last_updated") or "")
    tool_score = 1 if raw.get("tool_call") else 0
    return (released, updated, tool_score, model_id)


def _models_dev_model_entry(provider_id: str, model_id: str, raw: Dict[str, Any], api_base: str = "", api_key_ref: str = "") -> Dict[str, Any]:
    limit = raw.get("limit") if isinstance(raw.get("limit"), dict) else {}
    modalities = raw.get("modalities") if isinstance(raw.get("modalities"), dict) else {}
    input_mods = modalities.get("input") if isinstance(modalities, dict) and isinstance(modalities.get("input"), list) else []
    output_mods = modalities.get("output") if isinstance(modalities, dict) and isinstance(modalities.get("output"), list) else []
    context_length = int(limit.get("context", 0) or 0) if isinstance(limit, dict) else 0
    capabilities = {
        "vision": bool(raw.get("attachment")) or "image" in input_mods,
        "tool_calling": bool(raw.get("tool_call", False)),
        "image_gen": "image" in output_mods,
        "audio_stt": "audio" in input_mods and "text" in output_mods,
        "reasoning": bool(raw.get("reasoning", False)),
        "structured_output": bool(raw.get("structured_output", False)),
        "open_weights": bool(raw.get("open_weights", False)),
    }
    parts = []
    if raw.get("family"):
        parts.append(str(raw.get("family")))
    caps = [k for k, enabled in (
        ("reasoning", capabilities["reasoning"]),
        ("tools", capabilities["tool_calling"]),
        ("vision", capabilities["vision"]),
        ("structured output", capabilities["structured_output"]),
        ("open weights", capabilities["open_weights"]),
    ) if enabled]
    if caps:
        parts.append(", ".join(caps))
    if raw.get("release_date"):
        parts.append(f"released {raw.get('release_date')}")
    if raw.get("last_updated") and raw.get("last_updated") != raw.get("release_date"):
        parts.append(f"updated {raw.get('last_updated')}")
    return {
        "id": model_id,
        "display_name": str(raw.get("name") or model_id),
        "provider": provider_id,
        "tier": "premium" if capabilities["reasoning"] else "standard",
        "context_length": context_length,
        "capabilities": capabilities,
        "suitable_complexity": ["SIMPLE", "MEDIUM", "COMPLEX"] if capabilities["reasoning"] else ["SIMPLE", "MEDIUM"],
        "api_base": api_base or None,
        "api_key_ref": api_key_ref or None,
        "active": True,
        "description": " · ".join(parts) or "models.dev live catalog",
        "release_date": raw.get("release_date") or "",
        "last_updated": raw.get("last_updated") or "",
        "source": "models.dev",
    }


def _hermes_model_entry(provider_id: str, model_id: str, api_base: str = "", api_key_ref: str = "") -> Dict[str, Any]:
    """Return one UI/catalog model row from Hermes' current model registry."""
    display_name = model_id
    context_length = 0
    capabilities = {"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}
    description = "Hermes model catalog"
    try:
        from agent.models_dev import get_model_info as get_models_dev_model

        meta = get_models_dev_model(provider_id, model_id)
        if meta is not None:
            display_name = meta.name or model_id
            context_length = int(meta.context_window or 0)
            capabilities = {
                "vision": bool(meta.supports_vision()),
                "tool_calling": bool(meta.tool_call),
                "image_gen": "image" in meta.output_modalities,
                "audio_stt": meta.supports_audio_input(),
                "reasoning": bool(meta.reasoning),
                "structured_output": bool(meta.structured_output),
                "open_weights": bool(meta.open_weights),
            }
            parts = []
            if meta.family:
                parts.append(meta.family)
            caps = meta.format_capabilities()
            if caps and caps != "basic":
                parts.append(caps)
            if meta.release_date:
                parts.append(f"released {meta.release_date}")
            description = " · ".join(parts) or description
    except Exception:
        pass

    return {
        "id": model_id,
        "display_name": display_name,
        "provider": provider_id,
        "tier": "standard",
        "context_length": context_length,
        "capabilities": capabilities,
        "suitable_complexity": ["SIMPLE", "MEDIUM", "COMPLEX"] if capabilities.get("reasoning") else ["SIMPLE", "MEDIUM"],
        "api_base": api_base or None,
        "api_key_ref": api_key_ref or None,
        "active": True,
        "description": description,
    }


def _latest_hermes_provider_rows(force_refresh: bool = False, max_models: int = 0) -> Dict[str, Dict[str, Any]]:
    """Build provider rows from Hermes' live/static provider catalog.

    This is the same source family used by the Hermes model picker. It can
    refresh live/API-backed catalogs when requested and falls back to Hermes'
    curated static/models.dev-backed lists when offline.
    """
    rows: Dict[str, Dict[str, Any]] = {}
    models_dev: Dict[str, Any] = {}
    try:
        from agent.models_dev import fetch_models_dev

        models_dev = fetch_models_dev(force_refresh=force_refresh)
    except Exception:
        models_dev = {}

    try:
        from hermes_cli.models import CANONICAL_PROVIDERS, provider_model_ids
        from hermes_cli.providers import get_provider
    except Exception:
        return rows

    used_models_dev_ids: Set[str] = set()
    for entry in CANONICAL_PROVIDERS:
        provider_id = entry.slug
        try:
            pdef = get_provider(provider_id)
        except Exception:
            pdef = None
        api_base = getattr(pdef, "base_url", "") if pdef is not None else ""
        env_vars = list(getattr(pdef, "api_key_env_vars", ()) or ()) if pdef is not None else []
        api_key_env = env_vars[0] if env_vars else ""
        api_key_ref = f"${{{api_key_env}}}" if api_key_env else ""
        source = "hermes"
        models: List[Dict[str, Any]] = []
        mdev_id = _models_dev_provider_id(provider_id)
        raw_provider = models_dev.get(mdev_id) if isinstance(models_dev, dict) else None
        raw_models = raw_provider.get("models") if isinstance(raw_provider, dict) else None
        if isinstance(raw_provider, dict) and isinstance(raw_models, dict):
            used_models_dev_ids.add(mdev_id)
            api_base = api_base or str(raw_provider.get("api") or "")
            raw_env = raw_provider.get("env")
            if not api_key_env and isinstance(raw_env, list) and raw_env:
                api_key_env = str(raw_env[0])
                api_key_ref = f"${{{api_key_env}}}"
            latest_items = [
                (model_id, raw)
                for model_id, raw in raw_models.items()
                if _models_dev_include_model(provider_id, str(model_id), raw)
            ]
            latest_items.sort(key=_models_dev_sort_key, reverse=True)
            if max_models > 0:
                latest_items = latest_items[:max_models]
            models = [
                _models_dev_model_entry(provider_id, str(model_id), raw, api_base, api_key_ref)
                for model_id, raw in latest_items
            ]
            source = "models.dev"
        else:
            try:
                import contextlib
                import io

                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    model_ids = provider_model_ids(provider_id, force_refresh=force_refresh)
            except Exception:
                model_ids = []
            if max_models > 0:
                model_ids = model_ids[:max_models]
            models = [
                _hermes_model_entry(provider_id, model_id, api_base, api_key_ref)
                for model_id in model_ids
            ]
        if max_models > 0:
            models = models[:max_models]
        rows[provider_id] = {
            "id": provider_id,
            "slug": provider_id,
            "name": getattr(pdef, "name", "") if pdef is not None else str(raw_provider.get("name") or entry.label) if isinstance(raw_provider, dict) else entry.label,
            "api_base": api_base,
            "api_key_env": api_key_env,
            "api_key_ref": api_key_ref,
            "source": source,
            "total_models": len(models),
            "models": models,
        }

    for provider_id, raw_provider in (models_dev or {}).items():
        if provider_id in used_models_dev_ids or provider_id in rows:
            continue
        if not isinstance(raw_provider, dict):
            continue
        raw_models = raw_provider.get("models")
        if not isinstance(raw_models, dict):
            continue
        raw_env = raw_provider.get("env")
        api_key_env = str(raw_env[0]) if isinstance(raw_env, list) and raw_env else ""
        api_key_ref = f"${{{api_key_env}}}" if api_key_env else ""
        api_base = str(raw_provider.get("api") or "")
        latest_items = [
            (model_id, raw)
            for model_id, raw in raw_models.items()
            if _models_dev_include_model(str(provider_id), str(model_id), raw)
        ]
        latest_items.sort(key=_models_dev_sort_key, reverse=True)
        if max_models > 0:
            latest_items = latest_items[:max_models]
        models = [
            _models_dev_model_entry(str(provider_id), str(model_id), raw, api_base, api_key_ref)
            for model_id, raw in latest_items
        ]
        if not models:
            continue
        rows[str(provider_id)] = {
            "id": str(provider_id),
            "slug": str(provider_id),
            "name": str(raw_provider.get("name") or provider_id),
            "api_base": api_base,
            "api_key_env": api_key_env,
            "api_key_ref": api_key_ref,
            "source": "models.dev",
            "total_models": len(models),
            "models": models,
        }
    return rows


@app.get("/api/hermes/model-bindings")
async def hermes_model_bindings(refresh: bool = False):
    """Return the effective Hermes/OPC model-provider binding state."""
    if _HERMES_WEB_SERVER is None:
        raise HTTPException(503, "Hermes Agent Web API is not mounted")

    from hermes_cli.config import get_config_path, get_env_path, load_config, load_env
    from opc_hermes.model_manager import ModelManager

    mm = ModelManager()
    cfg = load_config()
    env = load_env()

    model_cfg = cfg.get("model", {})
    if not isinstance(model_cfg, dict):
        model_cfg = {"default": str(model_cfg) if model_cfg else ""}
    providers_cfg = cfg.get("providers", {})
    if not isinstance(providers_cfg, dict):
        providers_cfg = {}

    latest_providers = _latest_hermes_provider_rows(force_refresh=refresh)
    opc_providers = {p.id: p for p in mm.list_providers()}
    opc_models_by_provider: Dict[str, List[Dict[str, Any]]] = {}
    for model in mm.list_models():
        opc_models_by_provider.setdefault(model.provider, []).append(asdict(model))

    provider_ids = set(latest_providers) | set(opc_providers) | {str(k) for k in providers_cfg.keys()}
    providers: List[Dict[str, Any]] = []
    for provider_id in sorted(provider_ids):
        latest = latest_providers.get(provider_id, {})
        opc_provider = opc_providers.get(provider_id)
        entry = providers_cfg.get(provider_id, {})
        if not isinstance(entry, dict):
            entry = {}

        api_base = _provider_entry_base_url(entry) or str(latest.get("api_base") or "") or (opc_provider.api_base if opc_provider else "")
        api_key_env = str(entry.get("key_env", "") or "").strip()
        if not api_key_env:
            api_key_env = str(latest.get("api_key_env") or "").strip()
        if not api_key_env and opc_provider:
            api_key_env = _env_ref_name(opc_provider.api_key_ref)
        api_key_set = bool(
            (api_key_env and (env.get(api_key_env) or os.environ.get(api_key_env)))
            or str(entry.get("api_key", "") or "").strip()
        )

        models = list(latest.get("models") or [])
        seen_models = {m.get("id") for m in models}
        for opc_model in opc_models_by_provider.get(provider_id, []):
            if opc_model.get("id") in seen_models:
                continue
            models.append(opc_model)
            seen_models.add(opc_model.get("id"))
        raw_models = entry.get("models")
        if isinstance(raw_models, dict):
            for model_id, meta in raw_models.items():
                if model_id in seen_models:
                    continue
                meta = meta if isinstance(meta, dict) else {}
                models.append({
                    "id": str(model_id),
                    "display_name": str(model_id),
                    "provider": provider_id,
                    "tier": "standard",
                    "context_length": int(meta.get("context_length", 0) or 0),
                    "capabilities": meta.get("capabilities", {}),
                    "suitable_complexity": ["SIMPLE", "MEDIUM"],
                    "api_base": api_base,
                    "api_key_ref": f"${{{api_key_env}}}" if api_key_env else "",
                    "active": True,
                    "description": "Hermes configured model",
                })
        elif isinstance(raw_models, list):
            for model_id in raw_models:
                if not isinstance(model_id, str) or model_id in seen_models:
                    continue
                models.append({
                    "id": model_id,
                    "display_name": model_id,
                    "provider": provider_id,
                    "tier": "standard",
                    "context_length": 0,
                    "capabilities": {},
                    "suitable_complexity": ["SIMPLE", "MEDIUM"],
                    "api_base": api_base,
                    "api_key_ref": f"${{{api_key_env}}}" if api_key_env else "",
                    "active": True,
                    "description": "Hermes configured model",
                })

        providers.append({
            "id": provider_id,
            "name": str(entry.get("name") or latest.get("name") or (opc_provider.name if opc_provider else provider_id)),
            "api_base": api_base,
            "api_key_env": api_key_env,
            "api_key_set": api_key_set,
            "configured": bool(entry),
            "default_model": str(entry.get("default_model", "") or ""),
            "local": _is_local_provider(provider_id, api_base),
            "models": models,
            "total_models": len(models),
            "source": str(latest.get("source") or ("opc" if opc_provider else "user-config")),
        })

    return {
        "current": {
            "provider": str(model_cfg.get("provider", "") or ""),
            "model": str(model_cfg.get("default", model_cfg.get("name", "")) or ""),
            "base_url": str(model_cfg.get("base_url", "") or ""),
            "context_length": int(model_cfg.get("context_length", 0) or 0),
        },
        "providers": providers,
        "local_profiles": _LOCAL_MODEL_PROFILES,
        "source": "models.dev",
        "refreshed": bool(refresh),
        "config_path": str(get_config_path()),
        "env_path": str(get_env_path()),
    }


@app.post("/api/hermes/model-bindings")
async def save_hermes_model_binding(data: Dict[str, Any]):
    """Persist a provider/API/model binding into Hermes config and OPC catalog."""
    if _HERMES_WEB_SERVER is None:
        raise HTTPException(503, "Hermes Agent Web API is not mounted")

    from hermes_cli.config import load_config, save_config, save_env_value
    from opc_hermes.model_manager import ModelDef, ModelManager, ModelProvider

    provider_id = _clean_slug(str(data.get("provider_id", "") or ""))
    if not provider_id:
        raise HTTPException(400, "provider_id is required")

    provider_name = str(data.get("provider_name", "") or provider_id).strip()
    api_base = str(data.get("api_base", "") or "").strip().rstrip("/")
    api_key = str(data.get("api_key", "") or "").strip()
    api_key_env = str(data.get("api_key_env", "") or "").strip()
    model_id = str(data.get("model_id", "") or "").strip()
    display_name = str(data.get("display_name", "") or model_id or provider_name).strip()
    api_mode = str(data.get("api_mode", "") or "").strip()
    save_as_main = bool(data.get("save_as_main", False))

    mm = ModelManager()
    existing_provider = next((p for p in mm.list_providers() if p.id == provider_id), None)
    if not api_key_env and (api_key or not _is_local_provider(provider_id, api_base)):
        api_key_env = _default_api_key_env(provider_id, existing_provider.api_key_ref if existing_provider else "")

    if api_key:
        save_env_value(api_key_env, api_key)

    cfg = load_config()
    providers = cfg.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}

    entry = providers.get(provider_id, {})
    if not isinstance(entry, dict):
        entry = {}
    entry["name"] = provider_name
    if api_base:
        entry["base_url"] = api_base
        entry.pop("api", None)
        entry.pop("url", None)
    if api_key_env:
        entry["key_env"] = api_key_env
    if api_mode:
        entry["api_mode"] = api_mode
    if model_id:
        entry["default_model"] = model_id
        raw_models = entry.get("models")
        models = raw_models if isinstance(raw_models, dict) else {}
        models[model_id] = {**(models.get(model_id, {}) if isinstance(models.get(model_id), dict) else {}), **_model_meta_from_payload(data)}
        entry["models"] = models

    providers[provider_id] = entry
    cfg["providers"] = providers

    if save_as_main:
        if not model_id:
            raise HTTPException(400, "model_id is required when save_as_main is true")
        model_cfg = cfg.get("model", {})
        if not isinstance(model_cfg, dict):
            model_cfg = {}
        model_cfg["provider"] = provider_id
        model_cfg["default"] = model_id
        if api_base:
            model_cfg["base_url"] = api_base
        context_length = data.get("context_length")
        if isinstance(context_length, int) and context_length > 0:
            model_cfg["context_length"] = context_length
        elif "context_length" in model_cfg:
            model_cfg.pop("context_length", None)
        cfg["model"] = model_cfg

    save_config(cfg)

    mm.save_provider(ModelProvider(
        id=provider_id,
        name=provider_name,
        api_base=api_base,
        api_key_ref=f"${{{api_key_env}}}" if api_key_env else "",
    ))
    if model_id:
        mm.save_model(ModelDef(
            id=model_id,
            display_name=display_name,
            provider=provider_id,
            tier=str(data.get("tier", "") or "standard"),
            context_length=int(data.get("context_length", 0) or 128000),
            capabilities=data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False},
            suitable_complexity=data.get("suitable_complexity") if isinstance(data.get("suitable_complexity"), list) else ["SIMPLE", "MEDIUM"],
            api_base=api_base,
            api_key_ref=f"${{{api_key_env}}}" if api_key_env else "",
            active=True,
            description=str(data.get("description", "") or "Bound from OPC-Hermes /models"),
        ))

    return {
        "ok": True,
        "provider": provider_id,
        "model": model_id,
        "api_base": api_base,
        "api_key_env": api_key_env,
        "saved_main": save_as_main,
    }


def _discover_openai_compatible_models(api_base: str, provider_id: str = "") -> Dict[str, Any]:
    import json
    import urllib.request
    from urllib.parse import urlparse

    base = (api_base or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "models": [], "message": "api_base is required"}

    candidates = [f"{base}/models"]
    parsed = urlparse(base)
    root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    if provider_id == "ollama" or parsed.port == 11434:
        candidates.append(f"{root}/api/tags")

    errors: List[str] = []
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            models: List[str] = []
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                for item in payload["data"]:
                    if isinstance(item, dict) and item.get("id"):
                        models.append(str(item["id"]))
            elif isinstance(payload, dict) and isinstance(payload.get("models"), list):
                for item in payload["models"]:
                    if isinstance(item, dict) and item.get("name"):
                        models.append(str(item["name"]))
            models = sorted(set(models))
            if models:
                return {"ok": True, "endpoint": url, "models": models, "message": f"Detected {len(models)} model(s)"}
            errors.append(f"{url}: no models in response")
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    return {"ok": False, "endpoint": candidates[0], "models": [], "message": "; ".join(errors[-2:])}


@app.post("/api/hermes/local-models/discover")
async def discover_local_models(data: Dict[str, Any]):
    api_base = str(data.get("api_base", "") or "").strip()
    provider_id = _clean_slug(str(data.get("provider_id", "") or "local"))
    import asyncio

    return await asyncio.to_thread(_discover_openai_compatible_models, api_base, provider_id)


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
async def ingest_knowledge(payload: Dict[str, Any] = Body(...)):
    from opc_hermes.knowledge_pipeline import KnowledgePipeline

    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()
    tags = payload.get("tags", "")
    if not title:
        raise HTTPException(400, "Knowledge title is required.")
    if not content:
        raise HTTPException(400, "Knowledge content is required.")

    kp = KnowledgePipeline()
    if isinstance(tags, list):
        tag_list = [str(t).strip() for t in tags if str(t).strip()]
    else:
        tag_list = [t.strip() for t in str(tags or "").split(",") if t.strip()]
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
# OPC Model Catalog — all known providers + models
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/hermes/opc-model-catalog")
async def opc_model_catalog(refresh: bool = False):
    """Return the current Hermes-first model catalog plus OPC custom entries."""
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    models = mm.list_models()
    providers_list = mm.list_providers()
    groups = mm.list_groups()

    latest = _latest_hermes_provider_rows(force_refresh=refresh)

    # Build provider → OPC custom models mapping
    provider_models: Dict[str, List[Dict[str, Any]]] = {}
    for m in models:
        if not m.active:
            continue
        entry = {
            "id": m.id,
            "display_name": m.display_name,
            "tier": m.tier,
            "context_length": m.context_length,
            "capabilities": m.capabilities,
            "suitable_complexity": m.suitable_complexity,
            "api_base": m.api_base,
            "description": m.description,
        }
        provider_models.setdefault(m.provider, []).append(entry)

    # Start with Hermes' live/static catalog, then append OPC-only models.
    catalog_by_provider: Dict[str, Dict[str, Any]] = {}
    for provider_id, row in latest.items():
        catalog_by_provider[provider_id] = {
            "slug": provider_id,
            "name": row.get("name") or provider_id,
            "api_base": row.get("api_base") or "",
            "api_key_ref": row.get("api_key_ref") or "",
            "total_models": int(row.get("total_models") or len(row.get("models") or [])),
            "source": row.get("source") or "hermes",
            "models": list(row.get("models") or []),
        }

    for p in providers_list:
        row = catalog_by_provider.setdefault(p.id, {
            "slug": p.id,
            "name": p.name,
            "api_base": p.api_base,
            "api_key_ref": p.api_key_ref,
            "source": "opc",
            "models": [],
        })
        row["name"] = row.get("name") or p.name
        row["api_base"] = row.get("api_base") or p.api_base
        row["api_key_ref"] = row.get("api_key_ref") or p.api_key_ref
        seen = {m.get("id") for m in row["models"]}
        for model in provider_models.get(p.id, []):
            if model.get("id") not in seen:
                row["models"].append(model)
                seen.add(model.get("id"))
        row["total_models"] = len(row["models"])

    catalog_providers = sorted(
        catalog_by_provider.values(),
        key=lambda row: (0 if row.get("total_models", 0) else 1, str(row.get("name", ""))),
    )

    return {
        "providers": catalog_providers,
        "groups": [asdict(g) for g in groups],
        "source": "models.dev",
        "refreshed": bool(refresh),
        "default_tier_order": ["premium", "standard", "budget"],
        "capability_filters": [
            {"key": "vision", "label": "Vision"},
            {"key": "tool_calling", "label": "Tool Calling"},
            {"key": "image_gen", "label": "Image Generation"},
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# Static files (frontend build)
# ══════════════════════════════════════════════════════════════════════════

FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    class SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

def main(host: Optional[str] = None, port: Optional[int] = None, reload: bool = False):
    import uvicorn

    resolved_host = host or os.environ.get("OPC_WEBUI_HOST", "127.0.0.1")
    resolved_port = int(port or os.environ.get("OPC_WEBUI_PORT", "8765"))
    uvicorn.run(
        "opc_hermes.webui.server:app",
        host=resolved_host,
        port=resolved_port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
