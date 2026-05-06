"""Minimal flow manager for the frozen v0.1 protocol."""

from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from validator import validate_candidate_payload

FLOW_STATES = {
    "awaiting_input",
    "parsing",
    "awaiting_confirmation",
    "revising",
    "committed",
    "cancelled",
}

ACTION_KEYWORDS = ("做了", "完成了", "处理了", "整理了", "学习了", "写了", "记录了", "推进了", "推进", "提交了")
TASK_KEYWORDS = ("待办", "todo", "TODO", "需要", "计划", "待完成", "准备", "待做", "暂停", "取消")
IDEA_KEYWORDS = ("想法", "点子", "思路", "idea")
REVIEW_KEYWORDS = ("复盘", "回顾", "总结", "反思", "review")
STATE_KEYWORDS = ("状态", "疲劳", "专注", "压力", "精神", "身体", "困", "累", "焦虑")

CHANNEL_KEYWORDS = {
    "llm_engineering": ("llm", "rag", "agent", "模型", "提示词", "prompt", "openclaw"),
    "body_management": ("身体", "恢复", "锻炼", "睡觉", "饮食", "疲劳"),
    "teaching": ("教学", "代课", "讲课", "备课"),
    "exam_prep": ("考研", "刷题"),
    "mechanics_learning": ("力学", "理论力学", "材料力学", "mechanics", "题目"),
    "system_building": ("协议", "字段", "系统", "引擎", "schema", "validator"),
    "daily_maintenance": ("杂务", "日常", "维护", "报销", "沟通"),
}

CHANNEL_PLACEHOLDER_NOTE = "primary_channel_tag 使用占位值 system_building，因为无法可靠判断通道。"
VALUE_PLACEHOLDER_NOTE = "primary_value_tag 使用占位值 鸡肋，因为无法可靠判断价值。"


class FlowManager:
    """Builds and revises candidate payloads without touching storage."""

    def __init__(self) -> None:
        self._session_counter = 0
        self._bundle_counter = 0

    def start_session(self, raw_input: str) -> dict[str, Any]:
        """Create a new in-memory flow session."""
        self._require_text(raw_input, "raw_input")
        now = self._now_string()
        self._session_counter += 1
        return {
            "session_id": f"ses_{self._session_counter:06d}",
            "raw_input": raw_input,
            "last_user_revision": None,
            "candidate_payload": None,
            "flow_state": "awaiting_input",
            "created_at": now,
            "updated_at": now,
        }

    def parse_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """Parse the session raw_input and store the latest candidate payload."""
        self._validate_session_shape(session)
        updated_session = copy.deepcopy(session)
        updated_session["flow_state"] = "parsing"

        existing_payload = updated_session.get("candidate_payload")
        bundle_id = existing_payload.get("bundle_id") if isinstance(existing_payload, dict) else None
        payload = self._build_candidate_payload(updated_session["raw_input"], bundle_id=bundle_id)

        updated_session["candidate_payload"] = payload
        updated_session["flow_state"] = "awaiting_confirmation"
        updated_session["updated_at"] = self._now_string()
        return updated_session

    def parse_input_to_candidates(self, raw_input: str) -> dict[str, Any]:
        """Parse user input into a valid candidate payload."""
        self._require_text(raw_input, "raw_input")
        return self._build_candidate_payload(raw_input, bundle_id=None)

    def apply_user_revision(self, session: dict[str, Any], revision_text: str) -> dict[str, Any]:
        """Re-parse the revised input and overwrite candidate_payload with the latest version."""
        self._validate_session_shape(session)
        self._require_text(revision_text, "revision_text")

        updated_session = copy.deepcopy(session)
        updated_session["flow_state"] = "revising"
        updated_session["last_user_revision"] = revision_text

        existing_payload = updated_session.get("candidate_payload")
        bundle_id = existing_payload.get("bundle_id") if isinstance(existing_payload, dict) else None
        payload = self._build_candidate_payload(revision_text, bundle_id=bundle_id)

        updated_session["candidate_payload"] = payload
        updated_session["flow_state"] = "awaiting_confirmation"
        updated_session["updated_at"] = self._now_string()
        return updated_session

    def confirm_candidates(
        self,
        session: dict[str, Any],
        candidate_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark the session as committed after validating the latest payload."""
        self._validate_session_shape(session)
        payload = candidate_payload if candidate_payload is not None else session.get("candidate_payload")
        errors = validate_candidate_payload(payload)
        if errors:
            raise ValueError("; ".join(errors))

        updated_session = copy.deepcopy(session)
        updated_session["candidate_payload"] = payload
        updated_session["flow_state"] = "committed"
        updated_session["updated_at"] = self._now_string()
        return updated_session

    def cancel_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """Cancel a session without mutating any other field."""
        self._validate_session_shape(session)
        updated_session = copy.deepcopy(session)
        updated_session["flow_state"] = "cancelled"
        updated_session["updated_at"] = self._now_string()
        return updated_session

    def _build_candidate_payload(self, raw_input: str, bundle_id: str | None) -> dict[str, Any]:
        event_text, state_text = self._extract_sections(raw_input)
        resolved_bundle_id = bundle_id or self._next_bundle_id()

        main_record = self._build_main_record(event_text)
        records = [main_record]

        if state_text:
            records.append(self._build_state_record(state_text, main_record))

        payload = {
            "schema_version": "v0.1",
            "bundle_id": resolved_bundle_id,
            "records": records,
        }
        errors = validate_candidate_payload(payload)
        if errors:
            raise ValueError("; ".join(errors))
        return payload

    def _build_main_record(self, event_text: str) -> dict[str, Any]:
        candidate_type, type_note, type_manual_review = self._infer_main_type(event_text)
        parse_notes = [type_note]
        needs_manual_review = type_manual_review

        subject, subject_note, subject_manual_review = self._extract_subject(event_text)
        parse_notes.append(subject_note)
        needs_manual_review = needs_manual_review or subject_manual_review

        event_time, event_time_note, event_time_manual_review = self._extract_event_time(event_text)
        if event_time_note:
            parse_notes.append(event_time_note)
        needs_manual_review = needs_manual_review or event_time_manual_review

        duration_min, duration_note, duration_manual_review = self._extract_duration(event_text)
        if duration_note:
            parse_notes.append(duration_note)
        needs_manual_review = needs_manual_review or duration_manual_review

        primary_channel_tag, channel_note, channel_placeholder_used = self._infer_primary_channel(event_text)
        parse_notes.append(channel_note)
        needs_manual_review = needs_manual_review or channel_placeholder_used

        primary_value_tag, value_note, value_placeholder_used = self._infer_primary_value(event_text)
        parse_notes.append(value_note)
        needs_manual_review = needs_manual_review or value_placeholder_used

        status, status_note = self._infer_status(candidate_type, event_text)
        if status_note:
            parse_notes.append(status_note)

        self._append_manual_review_tag_context(
            parse_notes=parse_notes,
            primary_channel_tag=primary_channel_tag,
            primary_value_tag=primary_value_tag,
            needs_manual_review=needs_manual_review,
            channel_placeholder_used=channel_placeholder_used,
            value_placeholder_used=value_placeholder_used,
        )

        return {
            "candidate_id": "temp_1",
            "type": candidate_type,
            "content": event_text,
            "subject": subject,
            "value": None,
            "unit": None,
            "duration_min": duration_min,
            "event_time": event_time,
            "primary_channel_tag": primary_channel_tag,
            "secondary_channel_tag": None,
            "primary_value_tag": primary_value_tag,
            "secondary_value_tag": None,
            "status": status,
            "related_to": None,
            "needs_manual_review": needs_manual_review,
            "parse_note": " ".join(parse_notes),
        }

    def _build_state_record(self, state_text: str, main_record: dict[str, Any]) -> dict[str, Any]:
        subject = self._extract_state_subject(state_text)
        parse_notes = [
            "根据输入中的状态描述独立生成 type=state 记录，并通过 related_to 指向主候选。",
            f"state.subject 初步抽取为“{subject}”。",
            "primary_channel_tag 与 primary_value_tag 沿用主候选。",
        ]

        needs_manual_review = False
        if CHANNEL_PLACEHOLDER_NOTE in main_record["parse_note"]:
            parse_notes.append(CHANNEL_PLACEHOLDER_NOTE)
            needs_manual_review = True
        if VALUE_PLACEHOLDER_NOTE in main_record["parse_note"]:
            parse_notes.append(VALUE_PLACEHOLDER_NOTE)
            needs_manual_review = True

        return {
            "candidate_id": "temp_2",
            "type": "state",
            "content": state_text,
            "subject": subject,
            "value": None,
            "unit": None,
            "duration_min": None,
            "event_time": None,
            "primary_channel_tag": main_record["primary_channel_tag"],
            "secondary_channel_tag": None,
            "primary_value_tag": main_record["primary_value_tag"],
            "secondary_value_tag": None,
            "status": None,
            "related_to": main_record["candidate_id"],
            "needs_manual_review": needs_manual_review,
            "parse_note": " ".join(parse_notes),
        }

    def _extract_sections(self, raw_input: str) -> tuple[str, str | None]:
        event_match = re.search(r"(?m)^\s*1\.\s*事件[:：]\s*(.+?)\s*$", raw_input)
        state_match = re.search(r"(?m)^\s*2\.\s*状态[:：]\s*(.+?)\s*$", raw_input)
        time_match = re.search(r"(?m)^\s*3\.\s*时间[:：]\s*(.+?)\s*$", raw_input)

        if event_match:
            event_text = event_match.group(1).strip()
        else:
            event_text = raw_input.strip()

        if time_match and time_match.group(1).strip():
            event_text = f"{event_text} {time_match.group(1).strip()}".strip()

        if state_match:
            state_text = state_match.group(1).strip()
        else:
            state_text = self._find_state_fragment(raw_input)

        return event_text, state_text

    def _infer_main_type(self, event_text: str) -> tuple[str, str, bool]:
        lowered = event_text.lower()

        if any(keyword in event_text for keyword in ACTION_KEYWORDS):
            return "action", "主候选依据动作关键词按 action 判定。", False
        if any(keyword in event_text for keyword in TASK_KEYWORDS) or "todo" in lowered:
            return "task", "主候选依据任务关键词按 task 判定。", False
        if any(keyword in event_text for keyword in IDEA_KEYWORDS):
            return "idea", "主候选依据想法关键词按 idea 判定。", False
        if any(keyword in event_text for keyword in REVIEW_KEYWORDS) or "review" in lowered:
            return "review_note", "主候选依据复盘关键词按 review_note 判定。", False
        if any(keyword in event_text for keyword in STATE_KEYWORDS):
            return "review_note", "仅检测到状态线索；由于 state 不能作为主候选，主候选暂以 review_note 占位。", True
        if "了" in event_text:
            return "action", "未命中明确类型关键词，但事件文本更像已发生行为，主候选暂以 action 占位。", True
        return "review_note", "未命中明确类型关键词，主候选暂以 review_note 占位。", True

    def _extract_subject(self, event_text: str) -> tuple[str, str, bool]:
        patterns = (
            r"(?:写了|整理了|学习了|处理了|推进了|记录了|提交了|完成了)(.+)",
            r"(?:需要|计划|准备)(.+)",
            r"(?:想法[:：]?|点子[:：]?|思路[:：]?)(.+)",
            r"(?:复盘|回顾|总结|反思)(.+)",
            r"[:：]\s*(.+)",
        )
        for pattern in patterns:
            match = re.search(pattern, event_text)
            if not match:
                continue
            subject = self._clean_subject(match.group(1))
            if subject:
                return subject, f"subject 初步抽取为“{subject}”。", False

        stripped = self._clean_subject(event_text)
        if stripped and len(stripped) <= 12 and not any(keyword in stripped for keyword in STATE_KEYWORDS):
            return stripped, f"subject 初步抽取为“{stripped}”。", False

        return "待定", "subject 无法可靠抽取，暂记为待定。", True

    def _extract_event_time(self, event_text: str) -> tuple[str | None, str | None, bool]:
        exact_match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", event_text)
        if exact_match:
            return exact_match.group(1), "event_time 依据输入中的明确时间直接抽取。", False

        today = datetime.now().strftime("%Y-%m-%d")
        if "今晚九点左右" in event_text:
            return f"{today} 21:00", "event_time 为临时候选，基于自然语言时间词推定，待确认。", True
        if "今晚九点" in event_text:
            return f"{today} 21:00", "event_time 为临时候选，基于自然语言时间词推定，待确认。", True
        if "今天下午" in event_text:
            return f"{today} 15:00", "event_time 为临时候选，基于自然语言时间词推定，待确认。", True
        if "今早" in event_text or "早上" in event_text:
            return f"{today} 08:00", "event_time 为临时候选，基于自然语言时间词推定，待确认。", True

        return None, None, False

    def _extract_duration(self, event_text: str) -> tuple[int | None, str | None, bool]:
        fuzzy_duration_markers = ("约", "左右", "大概", "差不多", "将近", "多")
        hour_match = re.search(r"(\d+)\s*小时", event_text)
        if hour_match:
            hours = int(hour_match.group(1))
            duration_text = hour_match.group(0)
            if any(marker in event_text for marker in fuzzy_duration_markers):
                return hours * 60, "duration_min 为临时候选，基于模糊时长估计，待确认。", True
            return hours * 60, f"duration_min 依据明确数字时长直接抽取（{duration_text}）。", False

        minute_match = re.search(r"(\d+)\s*分钟", event_text)
        if minute_match:
            minutes = int(minute_match.group(1))
            duration_text = minute_match.group(0)
            if any(marker in event_text for marker in fuzzy_duration_markers):
                return minutes, "duration_min 为临时候选，基于模糊时长估计，待确认。", True
            return minutes, f"duration_min 依据明确数字时长直接抽取（{duration_text}）。", False

        return None, None, False

    def _infer_primary_channel(self, event_text: str) -> tuple[str, str, bool]:
        lowered = event_text.lower()
        for tag, keywords in CHANNEL_KEYWORDS.items():
            if any(keyword in event_text or keyword in lowered for keyword in keywords):
                return tag, f"primary_channel_tag 根据关键词判断为 {tag}。", False
        return "system_building", CHANNEL_PLACEHOLDER_NOTE, True

    def _infer_primary_value(self, event_text: str) -> tuple[str, str, bool]:
        if any(keyword in event_text for keyword in ("高价值", "关键", "核心", "主线", "推进")):
            return "高价值", "primary_value_tag 根据推进/核心语义判断为 高价值。", False
        if any(keyword in event_text for keyword in ("无用", "浪费")):
            return "无用", "primary_value_tag 根据明显低价值语义判断为 无用。", False
        if any(keyword in event_text for keyword in ("鸡肋", "杂务", "不得不", "被动", "边际")):
            return "鸡肋", "primary_value_tag 根据输入语义判断为 鸡肋。", False
        return "鸡肋", VALUE_PLACEHOLDER_NOTE, True

    def _infer_status(self, candidate_type: str, event_text: str) -> tuple[str | None, str | None]:
        if candidate_type != "task":
            return None, None
        if "暂停" in event_text or "搁置" in event_text:
            return "paused", "task.status 依据任务语义判定为 paused。"
        if "取消" in event_text:
            return "cancelled", "task.status 依据任务语义判定为 cancelled。"
        if "完成" in event_text:
            return "done", "task.status 依据任务语义判定为 done。"
        return "active", "task.status 依据任务语义判定为 active。"

    def _extract_state_subject(self, state_text: str) -> str:
        for keyword in ("疲劳", "专注", "压力", "精神", "身体", "焦虑", "困", "累"):
            if keyword in state_text:
                return keyword
        return "状态描述"

    def _find_state_fragment(self, raw_input: str) -> str | None:
        fragments = re.split(r"[，。；;\n]", raw_input)
        matched_fragments = [fragment.strip() for fragment in fragments if fragment.strip() and any(keyword in fragment for keyword in STATE_KEYWORDS)]
        if not matched_fragments:
            return None
        return "；".join(matched_fragments)

    def _append_manual_review_tag_context(
        self,
        parse_notes: list[str],
        primary_channel_tag: str,
        primary_value_tag: str,
        needs_manual_review: bool,
        channel_placeholder_used: bool,
        value_placeholder_used: bool,
    ) -> None:
        if not needs_manual_review:
            return

        if primary_channel_tag == "system_building" and not channel_placeholder_used:
            parse_notes.append("primary_channel_tag 判断为 system_building，为真实判断，非占位；本条需人工复核是因为其他字段待确认。")
        if primary_value_tag == "鸡肋" and not value_placeholder_used:
            parse_notes.append("primary_value_tag 判断为 鸡肋，为真实判断，非占位；本条需人工复核是因为其他字段待确认。")

    def _next_bundle_id(self) -> str:
        self._bundle_counter += 1
        return f"bun_{self._bundle_counter:06d}"

    def _validate_session_shape(self, session: dict[str, Any]) -> None:
        if not isinstance(session, dict):
            raise ValueError("session must be a dictionary.")
        if session.get("flow_state") not in FLOW_STATES:
            raise ValueError("session.flow_state must be one of the six frozen states.")
        self._require_text(session.get("session_id"), "session_id")
        self._require_text(session.get("raw_input"), "raw_input")

    def _require_text(self, value: Any, field_name: str) -> None:
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(f"{field_name} must be a non-empty string.")

    def _clean_subject(self, raw_subject: str) -> str:
        cleaned = raw_subject.strip(" ：:，,。；;")
        cleaned = re.split(r"(今天|今晚|今早|早上|下午|上午|晚上|\d{4}-\d{2}-\d{2}|\d+\s*(?:小时|分钟))", cleaned)[0]
        return cleaned.strip(" ：:，,。；;")

    def _now_string(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")
