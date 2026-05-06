"""NegEntropy.QuantEngine —— 四象限量化引擎。

核心职责：
1. 将记录转化为可观测的"熵指标"
2. 计算 Body / Mind / Spirit / Vocation 四象限的熵值
3. 检测偏离模式（用户行为 vs 目标）
4. 生成 SelfModel 快照

熵的概念来源：
- 信息论：熵 = 不确定性 / 混乱度
- 负熵引擎：熵 = 1 - (实际达成 / 目标值)，范围 [0, 1]
  - 熵 = 0：完全达成目标，系统有序
  - 熵 = 1：完全未达成，系统混乱
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.config import get_config
from src.storage.db import DatabaseManager
from src.storage.models import QuantCache, Record, SelfModelSnapshot


@dataclass
class QuadrantMetrics:
    """四象限指标数据类。"""

    body_entropy: float = 0.0
    mind_entropy: float = 0.0
    spirit_entropy: float = 0.0
    vocation_entropy: float = 0.0
    total_entropy: float = 0.0

    # 细分指标
    body_recovery_hours: float = 0.0
    body_exercise_minutes: float = 0.0
    mind_deep_work_hours: float = 0.0
    mind_learning_minutes: float = 0.0
    spirit_social_minutes: float = 0.0
    spirit_reflection_minutes: float = 0.0
    vocation_high_value_hours: float = 0.0
    vocation_output_count: int = 0

    # 行为分布
    channel_distribution: dict[str, float] = field(default_factory=dict)
    value_distribution: dict[str, int] = field(default_factory=dict)
    type_distribution: dict[str, int] = field(default_factory=dict)

    # 状态关联
    state_correlation: dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        lines = [
            f"总体熵值: {self.total_entropy:.2f}",
            f"  Body: {self.body_entropy:.2f}",
            f"  Mind: {self.mind_entropy:.2f}",
            f"  Spirit: {self.spirit_entropy:.2f}",
            f"  Vocation: {self.vocation_entropy:.2f}",
            f"高价值行为: {self.value_distribution.get('high_value', 0)} 条",
            f"低价值行为: {self.value_distribution.get('low_value', 0)} 条",
        ]
        return "\n".join(lines)


class QuantEngine:
    """四象限量化引擎。"""

    def __init__(self, db: DatabaseManager | None = None):
        self.config = get_config()
        self.db = db or DatabaseManager()
        self.targets = self.config.get("quant.quadrant_targets", {})
        self.decay = self.config.get("quant.entropy.decay_factor", 0.95)
        self.min_records = self.config.get("quant.entropy.min_records_for_analysis", 7)

    def compute(
        self,
        user_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        use_cache: bool = True,
    ) -> QuadrantMetrics:
        """计算指定时间段内的四象限指标。

        Args:
            user_id: 用户 ID
            start_time: 开始时间（默认 7 天前）
            end_time: 结束时间（默认现在）
            use_cache: 是否使用缓存
        """
        if end_time is None:
            end_time = datetime.utcnow()
        if start_time is None:
            start_time = end_time - timedelta(days=7)

        # 检查缓存
        if use_cache:
            cache_key = f"{user_id}_{start_time.date()}_{end_time.date()}"
            cached = self._get_cache(user_id, start_time, "daily")
            if cached:
                return self._metrics_from_dict(cached)

        # 查询记录
        with self.db.get_session() as session:
            records = self._fetch_records(session, user_id, start_time, end_time)

        if len(records) < self.min_records:
            # 记录不足，返回空指标
            return QuadrantMetrics()

        # 计算指标
        metrics = self._calculate_metrics(records)

        # 写入缓存
        if use_cache:
            self._save_cache(user_id, start_time, "daily", metrics)

        return metrics

    def _fetch_records(
        self,
        session: Session,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Record]:
        """查询记录。"""
        # 注：Record 表目前没有 user_id 字段，需要通过 metadata_json 或 source 推断
        # v2.0 中 FlowSession 有 user_id，可以通过 session_id 关联
        # 简化处理：先查询所有记录（后续按 user_id 过滤）
        stmt = (
            select(Record)
            .where(Record.event_time >= start_time)
            .where(Record.event_time <= end_time)
            .where(Record.record_type != "state")  # state 记录不单独计入统计
        )
        return list(session.scalars(stmt))

    def _calculate_metrics(self, records: list[Record]) -> QuadrantMetrics:
        """计算四象限指标。"""
        metrics = QuadrantMetrics()

        # 按通道映射到四象限
        channel_to_quadrant = {
            "body_management": "body",
            "llm_engineering": "mind",
            "mechanics_learning": "mind",
            "exam_prep": "mind",
            "teaching": "vocation",
            "system_building": "vocation",
            "daily_maintenance": "vocation",
        }

        # 累加各维度实际值
        for rec in records:
            quad = channel_to_quadrant.get(rec.primary_channel, "vocation")
            duration = (rec.duration_minutes or 0) / 60.0  # 转为小时

            if quad == "body":
                if rec.primary_value_tag == "high_value":
                    metrics.body_exercise_minutes += rec.duration_minutes or 0
                # recovery 从 state 记录推断（简化版）
            elif quad == "mind":
                if rec.primary_value_tag == "high_value":
                    metrics.mind_deep_work_hours += duration
                metrics.mind_learning_minutes += rec.duration_minutes or 0
            elif quad == "spirit":
                metrics.spirit_social_minutes += rec.duration_minutes or 0
                if rec.record_type == "review_note":
                    metrics.spirit_reflection_minutes += rec.duration_minutes or 0
            elif quad == "vocation":
                if rec.primary_value_tag == "high_value":
                    metrics.vocation_high_value_hours += duration
                    metrics.vocation_output_count += 1

            # 分布统计
            metrics.channel_distribution[rec.primary_channel] = (
                metrics.channel_distribution.get(rec.primary_channel, 0) + duration
            )
            metrics.value_distribution[rec.primary_value_tag] = (
                metrics.value_distribution.get(rec.primary_value_tag, 0) + 1
            )
            metrics.type_distribution[rec.record_type] = (
                metrics.type_distribution.get(rec.record_type, 0) + 1
            )

        # 计算熵值 = 1 - min(实际/目标, 1)
        t = self.targets
        metrics.body_entropy = self._entropy(
            metrics.body_exercise_minutes / 60.0,
            t.get("body", {}).get("exercise_minutes", 30) / 60.0,
        )
        metrics.mind_entropy = self._entropy(
            metrics.mind_deep_work_hours,
            t.get("mind", {}).get("deep_work_hours", 4),
        )
        metrics.spirit_entropy = self._entropy(
            (metrics.spirit_reflection_minutes + metrics.spirit_social_minutes) / 60.0,
            (t.get("spirit", {}).get("reflection_minutes", 10) + t.get("spirit", {}).get("social_minutes", 30)) / 60.0,
        )
        metrics.vocation_entropy = self._entropy(
            metrics.vocation_high_value_hours,
            t.get("vocation", {}).get("high_value_hours", 3),
        )

        # 总体熵（加权平均）
        weights = {"body": 0.25, "mind": 0.3, "spirit": 0.2, "vocation": 0.25}
        metrics.total_entropy = (
            weights["body"] * metrics.body_entropy
            + weights["mind"] * metrics.mind_entropy
            + weights["spirit"] * metrics.spirit_entropy
            + weights["vocation"] * metrics.vocation_entropy
        )

        return metrics

    def _entropy(self, actual: float, target: float) -> float:
        """计算单维度熵值。

        公式: entropy = 1 - min(actual / target, 1.0)
        如果 target <= 0, 返回 0
        """
        if target <= 0:
            return 0.0
        ratio = min(actual / target, 1.0)
        return max(0.0, 1.0 - ratio)

    def _get_cache(
        self, user_id: str, cache_date: datetime, cache_type: str
    ) -> dict[str, Any] | None:
        """读取缓存。"""
        with self.db.get_session() as session:
            stmt = (
                select(QuantCache)
                .where(QuantCache.user_id == user_id)
                .where(QuantCache.cache_date == cache_date.date())
                .where(QuantCache.cache_type == cache_type)
            )
            cache = session.scalar(stmt)
            if cache:
                return cache.metrics_json
        return None

    def _save_cache(
        self,
        user_id: str,
        cache_date: datetime,
        cache_type: str,
        metrics: QuadrantMetrics,
    ) -> None:
        """保存缓存。"""
        with self.db.get_session() as session:
            cache = QuantCache(
                user_id=user_id,
                cache_date=cache_date,
                cache_type=cache_type,
                metrics_json={
                    "body_entropy": metrics.body_entropy,
                    "mind_entropy": metrics.mind_entropy,
                    "spirit_entropy": metrics.spirit_entropy,
                    "vocation_entropy": metrics.vocation_entropy,
                    "total_entropy": metrics.total_entropy,
                    "channel_distribution": metrics.channel_distribution,
                    "value_distribution": metrics.value_distribution,
                    "type_distribution": metrics.type_distribution,
                },
            )
            session.add(cache)
            session.commit()

    def _metrics_from_dict(self, data: dict[str, Any]) -> QuadrantMetrics:
        """从字典恢复指标。"""
        return QuadrantMetrics(
            body_entropy=data.get("body_entropy", 0.0),
            mind_entropy=data.get("mind_entropy", 0.0),
            spirit_entropy=data.get("spirit_entropy", 0.0),
            vocation_entropy=data.get("vocation_entropy", 0.0),
            total_entropy=data.get("total_entropy", 0.0),
            channel_distribution=data.get("channel_distribution", {}),
            value_distribution=data.get("value_distribution", {}),
            type_distribution=data.get("type_distribution", {}),
        )

    def save_self_model_snapshot(
        self, user_id: str, metrics: QuadrantMetrics
    ) -> str:
        """保存 SelfModel 快照，返回快照 ID。"""
        with self.db.get_session() as session:
            snapshot = SelfModelSnapshot(
                user_id=user_id,
                quadrant_states={
                    "body": {"entropy": metrics.body_entropy},
                    "mind": {"entropy": metrics.mind_entropy},
                    "spirit": {"entropy": metrics.spirit_entropy},
                    "vocation": {"entropy": metrics.vocation_entropy},
                },
                quadrant_traits={
                    "dominant_channel": max(
                        metrics.channel_distribution,
                        key=metrics.channel_distribution.get,
                        default="",
                    ),
                    "value_ratio": {
                        "high": metrics.value_distribution.get("high_value", 0),
                        "low": metrics.value_distribution.get("low_value", 0),
                        "neutral": metrics.value_distribution.get("neutral", 0),
                    },
                },
                quadrant_channels=metrics.channel_distribution,
                total_entropy=metrics.total_entropy,
                body_entropy=metrics.body_entropy,
                mind_entropy=metrics.mind_entropy,
                spirit_entropy=metrics.spirit_entropy,
                vocation_entropy=metrics.vocation_entropy,
            )
            session.add(snapshot)
            session.commit()
            return snapshot.id

    def close(self) -> None:
        self.db.close()
