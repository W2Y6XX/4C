"""NegEntropy.Orchestrator —— 多 Agent 调度核心。

职责：
1. 接收输入（飞书 / CLI / 边缘设备）
2. 管理会话状态机（idle → parsing → quantifying → reviewing → deciding → responding）
3. 协调 LLM Provider、FlowManager、QuantEngine、DecisionEngine
4. 支持人工介入（revise / commit / cancel）
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.core.config import get_config
from src.llm.base import LLMProvider
from src.llm.kimi_provider import KimiProvider
from src.storage.db import DatabaseManager
from src.storage.models import FlowSession, Record


class SessionState(Enum):
    """会话状态机。

    必须与数据库约束 (ck_flow_state) 保持一致。
    """

    STARTED = "started"
    PARSED = "parsed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMMITTED = "committed"
    CANCELLED = "cancelled"


@dataclass
class ActionPlan:
    """Orchestrator 的输出计划。"""

    session_id: str
    state: SessionState
    candidate: dict[str, Any] = field(default_factory=dict)
    records_to_insert: list[dict[str, Any]] = field(default_factory=list)
    message_to_user: str = ""
    requires_confirmation: bool = True


class Orchestrator:
    """负熵引擎调度核心。

    每个用户会话由一个 Orchestrator 实例管理。
    支持状态持久化（通过 FlowSession 表）。
    """

    def __init__(self, user_id: str, db: DatabaseManager | None = None):
        self.user_id = user_id
        self.config = get_config()
        self.db = db or DatabaseManager()

        # 初始化 LLM Provider（根据配置）
        provider_name = self.config.get("llm.provider", "kimi")
        llm_config = self.config.get(f"llm.{provider_name}", {})
        if provider_name == "kimi":
            self.llm: LLMProvider = KimiProvider(llm_config)
        else:
            # Fallback to Kimi if unknown
            self.llm = KimiProvider(self.config.get("llm.kimi", {}))

        # 内存中的会话状态（尚未持久化的）
        self._active_sessions: dict[str, dict[str, Any]] = {}

    def _generate_id(self, prefix: str = "ses") -> str:
        """生成 v2.0 风格 ID。"""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    async def start_session(self, raw_input: str, source: str = "feishu") -> ActionPlan:
        """启动新会话：创建 FlowSession → 解析输入 → 生成候选。"""
        session_id = self._generate_id("ses")

        # 1. 创建数据库会话记录
        with self.db.get_session() as session:
            flow = FlowSession(
                session_id=session_id,
                user_id=self.user_id,
                flow_state=SessionState.STARTED.value,
                raw_input=raw_input,
                source=source,
            )
            session.add(flow)
            session.commit()

        # 2. 调用 LLM 解析 FSYQ
        parsed = await self.llm.parse_fsyq(raw_input)

        # 3. 更新状态为 awaiting_confirmation
        with self.db.get_session() as session:
            flow = session.get(FlowSession, session_id)
            if flow:
                flow.flow_state = SessionState.AWAITING_CONFIRMATION.value
                flow.candidate_payload = parsed
                session.commit()

        # 4. 构建候选记录列表
        records = self._build_records_from_candidate(session_id, parsed)

        # 5. 内存缓存
        self._active_sessions[session_id] = {
            "state": SessionState.AWAITING_CONFIRMATION,
            "candidate": parsed,
            "records": records,
        }

        # 6. 生成用户消息
        message = self._format_candidate_message(parsed, records)

        return ActionPlan(
            session_id=session_id,
            state=SessionState.AWAITING_CONFIRMATION,
            candidate=parsed,
            records_to_insert=records,
            message_to_user=message,
            requires_confirmation=True,
        )

    def _build_records_from_candidate(
        self, session_id: str, candidate: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """将解析结果转换为 Record 列表（支持 bundle：主记录 + state 记录）。"""
        bundle_id = self._generate_id("bun")
        records: list[dict[str, Any]] = []

        # 解析 event_time 为 datetime
        event_time_raw = candidate.get("event_time")
        if isinstance(event_time_raw, str):
            try:
                event_time = datetime.fromisoformat(event_time_raw.replace("Z", "+00:00"))
            except Exception:
                event_time = datetime.utcnow()
        elif isinstance(event_time_raw, datetime):
            event_time = event_time_raw
        else:
            event_time = datetime.utcnow()

        # 主记录
        main_record = {
            "id": self._generate_id("rec"),
            "bundle_id": bundle_id,
            "record_type": candidate.get("main_type", "action"),
            "content": candidate.get("main_subject", candidate.get("description", "")),
            "event_time": event_time,
            "recorded_at": datetime.utcnow(),
            "duration_minutes": candidate.get("duration_minutes"),
            "primary_channel": candidate.get("primary_channel", "daily_maintenance"),
            "primary_value_tag": candidate.get("primary_value_tag", "neutral"),
            "source": "feishu",
            "related_to": None,
            "metadata_json": {"session_id": session_id, "parsed_from": candidate},
        }
        records.append(main_record)

        # 关联的 state 记录
        if candidate.get("state_related") and candidate.get("state_description"):
            state_record = {
                "id": self._generate_id("rec"),
                "bundle_id": bundle_id,
                "record_type": "state",
                "content": candidate["state_description"],
                "event_time": event_time,
                "recorded_at": datetime.utcnow(),
                "primary_channel": main_record["primary_channel"],
                "primary_value_tag": "neutral",
                "source": "feishu",
                "related_to": main_record["id"],
                "metadata_json": {"session_id": session_id, "state_for": main_record["id"]},
            }
            records.append(state_record)

        return records

    def _format_candidate_message(
        self, candidate: dict[str, Any], records: list[dict[str, Any]]
    ) -> str:
        """格式化候选消息给用户（飞书卡片文本版）。"""
        lines = ["📋 检测到以下记录："]
        for i, rec in enumerate(records, 1):
            emoji = {"task": "📌", "action": "✅", "state": "😊", "idea": "💡", "review_note": "📝"}.get(
                rec["record_type"], "•"
            )
            lines.append(f"{emoji} {i}. [{rec['record_type']}] {rec['content']}")
            if rec["record_type"] != "state":
                lines.append(f"   通道: {rec['primary_channel']} | 价值: {rec['primary_value_tag']}")
        lines.append("\n请确认或修改：[确认] [修改] [取消]")
        return "\n".join(lines)

    async def revise_session(
        self, session_id: str, revision: dict[str, Any]
    ) -> ActionPlan:
        """用户修订候选内容。"""
        # 读取现有候选
        with self.db.get_session() as session:
            flow = session.get(FlowSession, session_id)
            if not flow or flow.user_id != self.user_id:
                return ActionPlan(
                    session_id=session_id,
                    state=SessionState.CANCELLED,
                    message_to_user="会话不存在或无权访问。",
                )

            # 合并修订
            candidate = dict(flow.candidate_payload or {})
            candidate.update(revision)
            flow.candidate_payload = candidate
            flow.flow_state = SessionState.AWAITING_CONFIRMATION.value
            flow.updated_at = datetime.utcnow()
            session.commit()

        # 重新构建记录
        records = self._build_records_from_candidate(session_id, candidate)
        self._active_sessions[session_id] = {
            "state": SessionState.AWAITING_CONFIRMATION,
            "candidate": candidate,
            "records": records,
        }

        message = self._format_candidate_message(candidate, records)
        return ActionPlan(
            session_id=session_id,
            state=SessionState.AWAITING_CONFIRMATION,
            candidate=candidate,
            records_to_insert=records,
            message_to_user=message,
            requires_confirmation=True,
        )

    async def commit_session(self, session_id: str) -> ActionPlan:
        """用户确认，正式写入 records 表。"""
        active = self._active_sessions.get(session_id)
        if not active:
            with self.db.get_session() as session:
                flow = session.get(FlowSession, session_id)
                if flow and flow.candidate_payload:
                    active = {
                        "records": self._build_records_from_candidate(
                            session_id, flow.candidate_payload
                        )
                    }
                else:
                    return ActionPlan(
                        session_id=session_id,
                        state=SessionState.CANCELLED,
                        message_to_user="会话已过期，请重新输入。",
                    )

        records = active.get("records", [])

        with self.db.get_session() as session:
            # 写入 records
            for rec_data in records:
                record = Record(**rec_data)
                session.add(record)

            # 更新 flow_session 状态
            flow = session.get(FlowSession, session_id)
            if flow:
                flow.flow_state = SessionState.COMMITTED.value
                flow.updated_at = datetime.utcnow()

            session.commit()

        # 清理内存缓存
        self._active_sessions.pop(session_id, None)

        return ActionPlan(
            session_id=session_id,
            state=SessionState.COMMITTED,
            records_to_insert=records,
            message_to_user=f"✅ 已确认并保存 {len(records)} 条记录。",
            requires_confirmation=False,
        )

    async def cancel_session(self, session_id: str) -> ActionPlan:
        """用户取消会话。"""
        with self.db.get_session() as session:
            flow = session.get(FlowSession, session_id)
            if flow:
                flow.flow_state = SessionState.CANCELLED.value
                flow.updated_at = datetime.utcnow()
                session.commit()

        self._active_sessions.pop(session_id, None)

        return ActionPlan(
            session_id=session_id,
            state=SessionState.CANCELLED,
            message_to_user="已取消本次记录。",
            requires_confirmation=False,
        )

    async def close(self) -> None:
        """关闭资源。"""
        if hasattr(self.llm, "close"):
            await self.llm.close()
        self.db.close()
