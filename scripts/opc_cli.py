#!/usr/bin/env python3
"""
OPC-Hermes 快速启动脚本（Python 版）

可作为 console_script 安装:  pip install -e .  →  opc start

用法:
  opc start                          # 启动 WebUI
  opc start --seed                   # 初始化数据 + 启动
  opc start --port 9000              # 指定端口
  opc seed                           # 仅初始化默认数据
  opc status                         # 查看系统状态
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ensure_path():
    """Add project root to sys.path for OPC imports."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


def cmd_seed():
    """Initialize default data."""
    ensure_path()
    print("🌱 初始化 OPC-Hermes 默认数据...")

    from opc_hermes.pipeline_manager import PipelineManager, PRESET_TEMPLATES
    pm = PipelineManager()
    existing = {t.id for t in pm.load_all()}
    count = 0
    for t in PRESET_TEMPLATES:
        if t.id not in existing:
            pm.save(t)
            print(f"   + 管道模板: {t.name} ({t.id})")
            count += 1

    from opc_hermes.model_manager import ModelManager
    import os as _os
    mm = ModelManager()
    # Force re-seed by deleting old files
    for _f in [mm.models_file, mm.groups_file, mm.providers_file]:
        if _f.exists():
            _os.remove(_f)
    mm._seed_defaults()
    m_count = len(mm.list_models())
    g_count = len(mm.list_groups())
    p_count = len(mm.list_providers())
    print(f"   + 模型库: {m_count} 模型, {g_count} 分组, {p_count} 供应商")

    # Seed five agent groups
    from opc_hermes.agent_list.registry import AgentGroup, get_group_manager
    gm = get_group_manager()
    preset_groups = [
        AgentGroup("doc_team", "文档制作团队", "文档/PPT 制作", ["researcher", "writer", "illustrator", "ppt_maker", "reviewer"]),
        AgentGroup("dev_team", "开发团队", "软件开发", ["software_architect", "backend_engineer", "qa_engineer", "code_reviewer"]),
        AgentGroup("security_team", "安全审计团队", "安全审查", ["security_engineer", "code_reviewer", "qa_engineer"]),
        AgentGroup("data_team", "数据分析团队", "数据分析", ["data_analyst", "illustrator", "ppt_maker"]),
        AgentGroup("research_team", "快速研究组", "快速研究", ["researcher", "writer", "reviewer"]),
    ]
    for g in preset_groups:
        if not gm.get_group(g.id):
            gm.save_group(g)
            print(f"   + 智能体组: {g.name} ({g.id})")

    print("✅ 默认数据初始化完成。")


def cmd_start(port: int = 8765, seed: bool = False):
    """Start the WebUI server."""
    if seed:
        cmd_seed()

    ensure_path()
    print(f"🚀 启动 OPC-Hermes WebUI (http://127.0.0.1:{port})...")

    try:
        import uvicorn
        uvicorn.run(
            "opc_hermes.webui.server:app",
            host="127.0.0.1",
            port=port,
            reload=False,
            log_level="info",
        )
    except ImportError:
        print("❌ uvicorn 未安装。运行: pip install fastapi uvicorn")
        sys.exit(1)


def cmd_status():
    """Print system status."""
    ensure_path()
    print("📊 OPC-Hermes 系统状态\n")

    # Agent Registry
    from opc_hermes.agent_list.registry import get_registry, get_group_manager
    registry = get_registry()
    workers = registry.list_workers()
    print(f"  Agent Registry:  {len(workers)} workers, {len(registry.list_skills())} skills")
    for w in workers[:5]:
        print(f"    {'👑' if w.role == 'leader' else '🔧' if w.role == 'worker' else '🔍'} {w.display_name} ({w.id}) [{w.model_tier}]")
    if len(workers) > 5:
        print(f"    ... 还有 {len(workers) - 5} 个 Worker")

    # Agent Groups
    gm = get_group_manager()
    groups = gm.list_groups()
    print(f"\n  Agent Groups:  {len(groups)} groups")
    for g in groups:
        print(f"    📁 {g.name} ({len(g.worker_ids)} members)")

    # Models
    from opc_hermes.model_manager import ModelManager
    mm = ModelManager()
    models = mm.list_models()
    print(f"\n  Model Manager:  {len(models)} models, {len(mm.list_groups())} groups, {len(mm.list_providers())} providers")
    for m in models[:5]:
        caps = ""
        if m.capabilities.get("vision"): caps += "👁 "
        if m.capabilities.get("tool_calling"): caps += "🔧"
        print(f"    ● {m.display_name} [{m.tier}] {m.context_length//1000}K {caps}")

    # Pipelines
    from opc_hermes.pipeline_manager import PipelineManager
    pm = PipelineManager()
    templates = pm.load_all()
    print(f"\n  Pipeline Templates:  {len(templates)} templates")
    for t in templates[:5]:
        print(f"    📋 {t.name} ({t.mode}) — {len(t.steps)} steps")

    # Memory
    from opc_hermes.memory_layer.gated_memory import get_memory_layer
    memory = get_memory_layer()
    evals = memory.get_evaluations(limit=5)
    print(f"\n  Eval Memory:  {len(evals)} evaluations")

    print("\n✅ 状态检查完成。")


def main():
    parser = argparse.ArgumentParser(description="OPC-Hermes CLI")
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="启动 WebUI 服务器")
    start_p.add_argument("--port", type=int, default=8765, help="端口号 (默认: 8765)")
    start_p.add_argument("--seed", action="store_true", help="启动前初始化默认数据")

    sub.add_parser("seed", help="初始化默认数据（管道模板、模型、智能体组）")
    sub.add_parser("status", help="查看系统状态")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args.port, args.seed)
    elif args.command == "seed":
        cmd_seed()
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
