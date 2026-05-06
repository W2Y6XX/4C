"""NegEntropy.DecisionEngine —— 自研决策引擎（替代 counsel）。

职责：
1. 基于 QuantEngine 输出生成复盘报告（周报/月报）
2. 检测偏离模式并生成告警
3. 基于四象限状态生成行动建议
4. 支持 nuwa-skill 启发式规则注入
5. 支持 agency-agents 角色偏好加载
6. 所有决策写入审计日志（DecisionLog）

设计原则：
- v1 使用规则引擎（非 ML），确保可解释性
- 决策过程完全可审计
- 支持人工 override
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.core.config import get_config
from src.llm.base import LLMProvider
from src.llm.kimi_provider import KimiProvider
from src.quant.engine import QuadrantMetrics
from src.storage.db import DatabaseManager
from src.storage.models import DecisionLog


@dataclass
class DecisionResult:
    """决策结果。"""

    decision_type: str  # weekly_report / suggestion / alert
    content: str
    deviation_detected: bool = False
    deviation_score: float = 0.0
    rules_triggered: list[str] = field(default_factory=list)
    persona_used: str | None = None

    def to_markdown(self) -> str:
        """转为 Markdown 格式（用于飞书卡片）。"""
        lines = [f"## {self.decision_type}"]
        if self.deviation_detected:
            lines.append(f"⚠️ **偏离告警** (偏离度: {self.deviation_score:.2f})")
        lines.append("")
        lines.append(self.content)
        if self.rules_triggered:
            lines.append("")
            lines.append("*触发规则:* " + ", ".join(self.rules_triggered))
        return "\n".join(lines)


class DecisionEngine:
    """自研决策引擎。"""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        llm: LLMProvider | None = None,
    ):
        self.config = get_config()
        self.db = db or DatabaseManager()

        # LLM 用于生成报告文本
        if llm is None:
            provider_name = self.config.get("llm.provider", "kimi")
            llm_config = self.config.get(f"llm.{provider_name}", {})
            self.llm: LLMProvider = KimiProvider(llm_config)
        else:
            self.llm = llm

        # 加载启发式规则（来自 nuwa-skill）
        self.heuristics: list[dict[str, Any]] = []

        # 偏离阈值
        self.deviation_threshold = self.config.get("decision.deviation_threshold", 0.3)

    def load_nuwa_heuristics(self, heuristics: list[dict[str, Any]]) -> None:
        """加载 nuwa-skill 的决策启发式规则。

        规则格式示例：
        {
            "name": "high_value_first",
            "description": "优先处理高价值任务",
            "condition": "vocation_entropy > 0.5",
            "action": "suggest_focus_on_high_value"
        }
        """
        self.heuristics = heuristics

    def evaluate_heuristics(self, metrics: QuadrantMetrics) -> list[str]:
        """评估启发式规则，返回触发的规则名称列表。"""
        triggered: list[str] = []

        for h in self.heuristics:
            try:
                # 简单规则引擎：将条件中的变量替换为实际值
                condition = h.get("condition", "")
                # 替换变量
                condition = condition.replace("body_entropy", str(metrics.body_entropy))
                condition = condition.replace("mind_entropy", str(metrics.mind_entropy))
                condition = condition.replace("spirit_entropy", str(metrics.spirit_entropy))
                condition = condition.replace("vocation_entropy", str(metrics.vocation_entropy))
                condition = condition.replace("total_entropy", str(metrics.total_entropy))

                # 安全求值
                if eval(condition, {"__builtins__": {}}, {}):
                    triggered.append(h.get("name", "unknown"))
            except Exception:
                continue

        # 内置规则
        if metrics.total_entropy > self.deviation_threshold:
            triggered.append("builtin_high_total_entropy")
        if metrics.vocation_entropy > 0.5:
            triggered.append("builtin_vocation_crisis")
        if metrics.body_entropy > 0.7:
            triggered.append("builtin_body_needs_attention")
        if metrics.mind_entropy > 0.6:
            triggered.append("builtin_mind_scattered")

        return triggered

    async def generate_weekly_report(
        self,
        user_id: str,
        metrics: QuadrantMetrics,
        records_summary: str = "",
    ) -> DecisionResult:
        """生成周报。"""
        triggered = self.evaluate_heuristics(metrics)

        # 使用 LLM 生成报告文本
        if not records_summary:
            records_summary = metrics.summary

        report_text = await self.llm.generate_report(
            records_summary=records_summary,
            quadrant_metrics=metrics.__dict__,
            report_type="weekly",
        )

        deviation = metrics.total_entropy > self.deviation_threshold
        result = DecisionResult(
            decision_type="weekly_report",
            content=report_text,
            deviation_detected=deviation,
            deviation_score=metrics.total_entropy,
            rules_triggered=triggered,
        )

        # 写入审计日志
        self._log_decision(user_id, result)

        return result

    async def generate_suggestions(
        self,
        user_id: str,
        metrics: QuadrantMetrics,
        persona: str | None = None,
    ) -> DecisionResult:
        """基于当前状态生成行动建议。"""
        triggered = self.evaluate_heuristics(metrics)

        # 基于规则生成建议（不依赖 LLM，确保即时响应）
        suggestions: list[str] = []

        if "builtin_vocation_crisis" in triggered:
            suggestions.append("📌 职业象限熵值过高：本周高价值产出不足，建议明天优先完成 1 项核心任务。")
        if "builtin_body_needs_attention" in triggered:
            suggestions.append("💤 身体象限告警：恢复不足，建议今晚提前 30 分钟休息。")
        if "builtin_mind_scattered" in triggered:
            suggestions.append("🧠 心智象限分散：深度工作时间不足，建议明天使用番茄工作法，保护 2 小时不间断时间。")
        if metrics.total_entropy < 0.2:
            suggestions.append("🎉 本周状态优秀！四象限均衡，建议保持当前节奏。")
        elif metrics.total_entropy < 0.4:
            suggestions.append("👍 整体状态良好，注意微调即可。")
        else:
            suggestions.append("⚠️ 整体熵值偏高，建议做一次全面复盘，重新校准目标。")

        # 如果有 persona，追加角色化建议
        if persona:
            suggestions.append(f"[角色视角: {persona}] 作为 {persona}，我会建议你关注...")

        content = "\n\n".join(suggestions)

        result = DecisionResult(
            decision_type="suggestion",
            content=content,
            deviation_detected=metrics.total_entropy > self.deviation_threshold,
            deviation_score=metrics.total_entropy,
            rules_triggered=triggered,
            persona_used=persona,
        )

        self._log_decision(user_id, result)

        return result

    def detect_deviation(
        self,
        current_metrics: QuadrantMetrics,
        historical_metrics: list[QuadrantMetrics] | None = None,
    ) -> DecisionResult:
        """检测偏离模式（与历史对比）。"""
        deviation_score = current_metrics.total_entropy
        deviation = deviation_score > self.deviation_threshold

        alerts: list[str] = []
        if deviation:
            alerts.append(f"总体熵值 {deviation_score:.2f} 超过阈值 {self.deviation_threshold}")

        # 与历史对比
        if historical_metrics:
            avg_entropy = sum(m.total_entropy for m in historical_metrics) / len(historical_metrics)
            if deviation_score > avg_entropy + 0.2:
                alerts.append(f"熵值较历史均值 ({avg_entropy:.2f}) 显著上升")

        content = "\n".join(alerts) if alerts else "未发现明显偏离。"

        result = DecisionResult(
            decision_type="alert",
            content=content,
            deviation_detected=deviation,
            deviation_score=deviation_score,
            rules_triggered=["builtin_deviation_check"],
        )

        return result

    def _log_decision(self, user_id: str, result: DecisionResult) -> None:
        """写入决策审计日志。"""
        with self.db.get_session() as session:
            log = DecisionLog(
                user_id=user_id,
                decision_type=result.decision_type,
                output_summary=result.content[:500],  # 摘要
                output_full=result.content,
                deviation_detected=result.deviation_detected,
                deviation_score=result.deviation_score,
                rules_triggered=result.rules_triggered,
                persona_used=result.persona_used,
            )
            session.add(log)
            session.commit()

    async def close(self) -> None:
        if hasattr(self.llm, "close"):
            await self.llm.close()
        self.db.close()
