"""V0.1 数据兼容层。

允许 v2.0 读取 V0.1 的 SQLite 数据库，实现数据继承。
"""

import sqlite3
from pathlib import Path
from typing import Any

from src.core.config import get_config


class V01Adapter:
    """V0.1 数据库适配器。

    只读访问 V0.1 的 mvp.sqlite3，将记录转换为 v2.0 格式。
    """

    def __init__(self, db_path: str | None = None):
        config = get_config()
        if db_path is None:
            db_path = config.get("database.v01_path", "../V0.1/data/mvp.sqlite3")

        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def get_records(self, limit: int = 1000) -> list[dict[str, Any]]:
        """读取 V0.1 的 records 表。"""
        conn = self._connect()
        cursor = conn.execute(
            "SELECT * FROM records ORDER BY recorded_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_flow_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """读取 V0.1 的 flow_sessions 表。"""
        conn = self._connect()
        cursor = conn.execute(
            "SELECT * FROM flow_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        """获取 V0.1 数据统计。"""
        conn = self._connect()
        stats = {}

        cursor = conn.execute("SELECT COUNT(*) FROM records")
        stats["total_records"] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM flow_sessions")
        stats["total_sessions"] = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT record_type, COUNT(*) FROM records GROUP BY record_type"
        )
        stats["type_distribution"] = {row[0]: row[1] for row in cursor.fetchall()}

        cursor = conn.execute(
            "SELECT primary_channel, COUNT(*) FROM records GROUP BY primary_channel"
        )
        stats["channel_distribution"] = {row[0]: row[1] for row in cursor.fetchall()}

        return stats

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
