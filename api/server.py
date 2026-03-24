# Copyright 2026 AXLPROTOCOL INC.
# Licensed under the Apache License, Version 2.0
"""
AXL Silo — API Server

Flask REST API + WebSocket for real-time packet streaming.

Endpoints:
  GET  /                          — Serve the web UI
  GET  /api/status                — Workspace status
  POST /api/workspace/create      — Create workspace from config
  POST /api/workspace/run         — Start the round loop
  POST /api/workspace/pause       — Pause
  POST /api/workspace/resume      — Resume
  POST /api/workspace/stop        — Stop
  GET  /api/bus                   — Read all packets
  GET  /api/bus/since/<id>        — Read packets since ID
  POST /api/bus/inject            — Operator injects a packet
  GET  /api/signal                — Current intelligence signal
  GET  /api/agents                — Agent statuses
  GET  /api/seeds                 — List available seeds
  WS   /ws                        — WebSocket for real-time packet feed
"""

import os
import json
import glob
import logging
from flask import Flask, jsonify, request, send_from_directory
from flask_sock import Sock

from ..core.workspace import Workspace, WorkspaceConfig
from ..core.codec import parse_packet, decode_packet
from ..core.report import ReportGenerator

logger = logging.getLogger(__name__)

# Global workspace (single workspace per instance for now)
_workspace = None
_ws_clients = set()

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web", "static")
SEEDS_DIR = os.path.join(BASE_DIR, "seeds")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/static")
    sock = Sock(app)

    # ═══ STATIC FILES ═══

    @app.route("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.route("/compress")
    def compress_page():
        return send_from_directory(WEB_DIR, "compress.html")

    @app.route("/static/<path:path>")
    def static_files(path):
        return send_from_directory(WEB_DIR, path)

    # ═══ WORKSPACE ═══

    @app.route("/api/status")
    def status():
        if not _workspace:
            return jsonify({"state": "NO_WORKSPACE", "message": "Create a workspace first."})
        return jsonify(_workspace.get_status())

    @app.route("/api/workspace/create", methods=["POST"])
    def workspace_create():
        global _workspace
        data = request.get_json()

        config = WorkspaceConfig(
            name=data.get("name", "Untitled"),
            seed_path=data.get("seed_path", ""),
            rounds=data.get("rounds", 12),
            agents=data.get("agents", []),
            rosetta_path=data.get("rosetta_path", ""),
            max_bus_context=data.get("max_bus_context", 20),
            delay_between_agents=data.get("delay_between_agents", 0.5),
            delay_between_rounds=data.get("delay_between_rounds", 1.0),
        )

        _workspace = Workspace(config)

        # Wire up WebSocket broadcasting
        def on_packet(packet):
            _broadcast_ws({
                "type": "packet",
                "data": packet.to_dict(),
            })

        def on_round(round_num):
            _broadcast_ws({
                "type": "round",
                "data": {"round": round_num, "status": _workspace.get_status()},
            })

        def on_complete(signal):
            _broadcast_ws({
                "type": "complete",
                "data": signal,
            })

        _workspace.on_packet(on_packet)
        _workspace.on_round(on_round)
        _workspace.on_complete(on_complete)

        try:
            _workspace.load()
            return jsonify({"status": "ok", "workspace": _workspace.get_status()})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/workspace/run", methods=["POST"])
    def workspace_run():
        if not _workspace:
            return jsonify({"error": "No workspace"}), 400
        _workspace.run(blocking=False)
        return jsonify({"status": "running"})

    @app.route("/api/workspace/pause", methods=["POST"])
    def workspace_pause():
        if not _workspace:
            return jsonify({"error": "No workspace"}), 400
        _workspace.pause()
        return jsonify({"status": "paused"})

    @app.route("/api/workspace/resume", methods=["POST"])
    def workspace_resume():
        if not _workspace:
            return jsonify({"error": "No workspace"}), 400
        _workspace.resume()
        return jsonify({"status": "running"})

    @app.route("/api/workspace/stop", methods=["POST"])
    def workspace_stop():
        if not _workspace:
            return jsonify({"error": "No workspace"}), 400
        _workspace.stop()
        return jsonify({"status": "stopped", "signal": _workspace.get_signal()})

    # ═══ BUS ═══

    @app.route("/api/bus")
    def bus_read():
        if not _workspace:
            return jsonify({"packets": []})
        packets = _workspace.bus.read()
        return jsonify({"packets": [p.to_dict() for p in packets]})

    @app.route("/api/bus/since/<int:packet_id>")
    def bus_since(packet_id):
        if not _workspace:
            return jsonify({"packets": []})
        packets = _workspace.bus.read(since_id=packet_id)
        return jsonify({"packets": [p.to_dict() for p in packets]})

    @app.route("/api/bus/inject", methods=["POST"])
    def bus_inject():
        if not _workspace:
            return jsonify({"error": "No workspace"}), 400
        data = request.get_json()
        content = data.get("content", "")
        if not content:
            return jsonify({"error": "No content"}), 400
        result = _workspace.inject(content)
        return jsonify({"status": "ok", "packet": result})

    # ═══ SIGNAL ═══

    @app.route("/api/signal")
    def signal():
        if not _workspace:
            return jsonify({"error": "No workspace"}), 400
        return jsonify(_workspace.get_signal())

    # ═══ AGENTS ═══

    @app.route("/api/agents")
    def agents():
        if not _workspace:
            return jsonify({"agents": []})
        return jsonify({"agents": [a.status() for a in _workspace.agents]})

    # ═══ SEEDS ═══

    @app.route("/api/seeds")
    def seeds():
        seed_files = glob.glob(os.path.join(SEEDS_DIR, "*.md"))
        result = []
        for sf in seed_files:
            name = os.path.basename(sf).replace(".md", "").replace("-", " ").title()
            with open(sf, "r") as f:
                preview = f.read(200)
            result.append({
                "filename": os.path.basename(sf),
                "path": sf,
                "name": name,
                "preview": preview,
            })
        return jsonify({"seeds": result})

    # ═══ REPORT ═══

    @app.route("/api/report")
    def report_json():
        """Get the full report as JSON."""
        if not _workspace:
            return jsonify({"error": "No workspace"}), 400
        gen = ReportGenerator(
            _workspace.bus.read(),
            config={"name": _workspace.config.name}
        )
        return jsonify(gen.generate_json())

    @app.route("/api/report/markdown")
    def report_markdown():
        """Get the full report as Markdown."""
        if not _workspace:
            return "No workspace", 400
        gen = ReportGenerator(
            _workspace.bus.read(),
            config={"name": _workspace.config.name}
        )
        md = gen.generate_markdown()
        return md, 200, {"Content-Type": "text/markdown; charset=utf-8"}

    @app.route("/api/report/download")
    def report_download():
        """Download the report as a .md file."""
        if not _workspace:
            return "No workspace", 400
        gen = ReportGenerator(
            _workspace.bus.read(),
            config={"name": _workspace.config.name}
        )
        md = gen.generate_markdown()
        filename = _workspace.config.name.lower().replace(" ", "-") + "-report.md"
        return md, 200, {
            "Content-Type": "text/markdown; charset=utf-8",
            "Content-Disposition": f"attachment; filename={filename}",
        }

    # ═══ QUEUE STATS ═══

    @app.route("/api/queue")
    def queue_stats():
        """Queue server statistics (if available)."""
        return jsonify({"status": "embedded", "message": "Queue runs within workspace"})

    # ═══ WEBSOCKET ═══

    @sock.route("/ws")
    def ws_handler(ws):
        _ws_clients.add(ws)
        logger.info(f"WebSocket client connected. Total: {len(_ws_clients)}")
        try:
            while True:
                # Keep connection alive, receive any operator messages
                data = ws.receive(timeout=60)
                if data is None:
                    break
                # Handle operator commands via WebSocket
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "inject" and _workspace:
                        _workspace.inject(msg.get("content", ""))
                except (json.JSONDecodeError, Exception):
                    pass
        except Exception:
            pass
        finally:
            _ws_clients.discard(ws)
            logger.info(f"WebSocket client disconnected. Total: {len(_ws_clients)}")

    return app


def _broadcast_ws(message: dict):
    """Broadcast a message to all connected WebSocket clients."""
    data = json.dumps(message)
    dead = set()
    for ws in _ws_clients:
        try:
            ws.send(data)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead
