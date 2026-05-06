"""SQLAlchemy 数据模型。

兼容 V0.1 的 records + flow_sessions 表结构，并扩展 v2.0 新表。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Record(Base):
    """行为记录表——继承并扩展 V0.1 的 records 表。"""

    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    bundle_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_channel: Mapped[str] = mapped_column(String(40), nullable=False)
    secondary_channel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    primary_value_tag: Mapped[str] = mapped_column(String(20), nullable=False)
    secondary_value_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="feishu", nullable=False)
    related_to: Mapped[str | None] = mapped_column(String(32), ForeignKey("records.id"), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    quant_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)  # v2.0 新增：该记录的熵值

    __table_args__ = (
        CheckConstraint(
            "record_type IN ('task', 'action', 'state', 'idea', 'review_note')",
            name="ck_record_type",
        ),
        CheckConstraint(
            "primary_value_tag IN ('high_value', 'low_value', 'neutral')",
            name="ck_primary_value",
        ),
        CheckConstraint(
            "source IN ('openclaw', 'feishu', 'edge', 'api')",
            name="ck_source",
        ),
    )

    # 关系：关联的主记录
    parent: Mapped["Record"] = relationship("Record", remote_side=[id], backref="children")


class FlowSession(Base):
    """流程会话表——继承 V0.1 的 flow_sessions 表。"""

    __tablename__ = "flow_sessions"

    session_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    flow_state: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    source: Mapped[str] = mapped_column(String(20), default="feishu")

    __table_args__ = (
        CheckConstraint(
            "flow_state IN ('started', 'parsed', 'awaiting_confirmation', 'committed', 'cancelled')",
            name="ck_flow_state",
        ),
    )


class SelfModelSnapshot(Base):
    """SelfModel 快照表——v2.0 新增。

    定期保存四象限状态、约束、偏好等。
    """

    __tablename__ = "self_model_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"sms_{uuid.uuid4().hex[:8]}")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 四象限指标（JSON 存储，便于扩展）
    quadrant_states: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quadrant_traits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quadrant_channels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # 总体熵值
    total_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    mind_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    spirit_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    vocation_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 元数据
    constraints: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    review_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DecisionLog(Base):
    """决策审计日志表——v2.0 新增。

    记录 DecisionEngine 的每次决策过程，确保可审计。
    """

    __tablename__ = "decision_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"dl_{uuid.uuid4().hex[:8]}")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False)  # weekly_report / suggestion / alert
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 输入快照
    input_records_count: Mapped[int] = mapped_column(Integer, default=0)
    input_self_model_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 使用的规则/启发式
    rules_triggered: Mapped[list[str]] = mapped_column(JSON, default=list)
    persona_used: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # 输出
    output_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    deviation_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    deviation_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class QuantCache(Base):
    """量化缓存表——v2.0 新增。

    避免重复计算，按天缓存量化结果。
    """

    __tablename__ = "quant_cache"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"qc_{uuid.uuid4().hex[:8]}")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cache_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    cache_type: Mapped[str] = mapped_column(String(20), nullable=False)  # daily / weekly / monthly

    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
