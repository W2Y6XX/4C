"""数据库管理器。"""

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from src.core.config import get_config
from src.storage.models import Base


class DatabaseManager:
    """统一数据库管理器。

    管理 v2.0 主数据库，并提供 V0.1 兼容接口。
    """

    def __init__(self, db_path: str | None = None):
        config = get_config()
        if db_path is None:
            db_path = config.get("database.v20_path", "data/v2_0.db")

        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=config.get("database.echo", False),
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self) -> None:
        """创建所有表。"""
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """获取新会话。"""
        return self.SessionLocal()

    def close(self) -> None:
        self.engine.dispose()
