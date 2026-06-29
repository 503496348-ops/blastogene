"""Web看板模块 - 提供只读API和HTML看板

原有模块：Flask Web服务器，提供社群数据看板
增强：集成MetricsRegistry指标引擎（来自metrics_engine.py）
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

from .config import BlastogeneConfig
from .metrics_engine import MetricsRegistry, Dashboard, setup_blastogene_dashboard


logger = logging.getLogger(__name__)


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器"""

    def log_message(self, format, *args):
        logger.info(format, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/dashboard":
            self._serve_dashboard()
        elif path == "/api/stats":
            self._serve_stats()
        elif path == "/api/messages":
            self._serve_messages(params)
        elif path == "/api/metrics":
            self._serve_metrics()
        else:
            self.send_error(404)

    def _serve_dashboard(self):
        html = self.server.dashboard.render_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_stats(self):
        stats = self.server.get_stats()
        self._send_json(stats)

    def _serve_messages(self, params):
        limit = int(params.get("limit", [50])[0])
        messages = self.server.get_recent_messages(limit)
        self._send_json(messages)

    def _serve_metrics(self):
        metrics = self.server.registry.list_stats()
        self._send_json(metrics)

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())


class DashboardApp:
    """Web看板应用"""

    def __init__(self, config: BlastogeneConfig, db_path: Optional[str] = None):
        self.config = config
        self.db_path = db_path or config.database.path
        self.registry = MetricsRegistry()
        self.dashboard = setup_blastogene_dashboard(self.registry)
        self._server = None
        self._thread = None

    def start(self, host: str = "0.0.0.0", port: int = 8081):
        """启动Web服务器"""
        self._server = HTTPServer((host, port), DashboardHandler)
        self._server.dashboard = self.dashboard
        self._server.registry = self.registry
        self._server.get_stats = self._get_stats
        self._server.get_recent_messages = self._get_recent_messages

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Dashboard started at http://%s:%d", host, port)

    def stop(self):
        if self._server:
            self._server.shutdown()

    def _get_stats(self) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM messages WHERE timestamp > datetime('now', '-24 hours')")
            today = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT sender_id) FROM messages WHERE timestamp > datetime('now', '-7 days')")
            active = cursor.fetchone()[0]
            conn.close()
            return {"total_messages": total, "today_messages": today, "active_users": active}
        except Exception as e:
            logger.error("Stats query failed: %s", e)
            return {"total_messages": 0, "today_messages": 0, "active_users": 0}

    def _get_recent_messages(self, limit: int = 50) -> list:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error("Messages query failed: %s", e)
            return []
