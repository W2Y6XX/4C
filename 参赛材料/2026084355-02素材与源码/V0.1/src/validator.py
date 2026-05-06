"""Validator helpers for the frozen v0.1 protocol."""

from __future__ import annotations

import re
from typing import Any

ALLOWED_TYPES = {"task", "action", "state", "idea", "review_note"}
TASK_STATUSES = {"active", "done", "cancelled", "paused"}
CHANNEL_TAGS = {
    "llm_engineering",
    "body_management",
    "teaching",
    "exam_prep",
    "mechanics_learning",
    "system_building",
    "daily_maintenance",
}
PRIMARY_VALUE_TAGS = {"高价值", "鸡肋", "无用"}
SECONDARY_VALUE_TAGS = {"恢复性", "不得不"}
ID_PATTERN = re.compile(r"^temp_[0-9]+$")
BUNDLE_PATTERN = re.compile(r"^bun_[0-9]{6}$")
EVENT_TIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
SUBJECT_EXPLANATION_MARKERS = ("无法可靠抽取", "未能可靠抽取", "无法确定", "未能确定")
TEMPORARY_MARKERS = ("临时候选", "临时", "推定", "估计", "待确认", "自然语言")
EVENT_TIME_FIELD_MARKERS = ("event_time", "时间")
DURATION_FIELD_MARKERS = ("duration_min", "duration", "时长")
CHANNEL_PLACEHOLDER_MARKERS = ("占位", "无法可靠判断通道", "未能可靠判断通道", "无法判断通道", "通道待确认")
VALUE_PLACEHOLDER_MARKERS = ("占位", "无法可靠判断价值", "未能可靠判断价值", "无法判断价值", "价值待确认")


def normalize_secondary_tag(primary_tag: str | None, secondary_tag: str | None) -> str | None:
    """Return a normalized secondary channel tag under the frozen protocol."""
    if primary_tag and secondary_tag == primary_tag:
        return None
    return secondary_tag


def validate_record(record: dict[str, Any]) -> list[str]:
    """Validate a single record and normalize duplicate secondary channel tags in-place."""
    errors: list[str] = []

    primary_channel_tag = record.get("primary_channel_tag")
    secondary_channel_tag = record.get("secondary_channel_tag")
    normalized_secondary_tag = normalize_secondary_tag(primary_channel_tag, secondary_channel_tag)
    if normalized_secondary_tag != secondary_channel_tag:
        record["secondary_channel_tag"] = normalized_secondary_tag

    record_type = record.get("type")
    if record_type not in ALLOWED_TYPES:
        errors.append("type must be one of task/action/state/idea/review_note.")

    parse_note = record.get("parse_note")
    if parse_note is None:
        errors.append("parse_note must exist on every record.")
        parse_note = ""
    elif not isinstance(parse_note, str) or parse_note.strip() == "":
        errors.append("parse_note must be a non-empty string.")
        parse_note = parse_note if isinstance(parse_note, str) else ""

    candidate_id = record.get("candidate_id")
    if not isinstance(candidate_id, str) or not ID_PATTERN.fullmatch(candidate_id):
        errors.append("candidate_id must use the temp_n format.")

    if not isinstance(record.get("content"), str) or record["content"].strip() == "":
        errors.append("content must be a non-empty string.")

    subject = record.get("subject")
    if not isinstance(subject, str) or subject.strip() == "":
        errors.append("subject must be a non-empty string.")
    elif subject == "待定" and not _contains_any(parse_note, SUBJECT_EXPLANATION_MARKERS):
        errors.append("subject='待定' requires parse_note to explain why extraction was unreliable.")

    needs_manual_review = record.get("needs_manual_review")
    if not isinstance(needs_manual_review, bool):
        errors.append("needs_manual_review must be a boolean.")

    if primary_channel_tag not in CHANNEL_TAGS:
        errors.append("primary_channel_tag must be present and valid.")
    elif (
        primary_channel_tag == "system_building"
        and needs_manual_review is True
        and not _contains_any(parse_note, CHANNEL_PLACEHOLDER_MARKERS)
    ):
        errors.append("placeholder primary_channel_tag=system_building requires parse_note to explain the placeholder or unreliable channel judgment.")

    secondary_channel_tag = record.get("secondary_channel_tag")
    if secondary_channel_tag is not None and secondary_channel_tag not in CHANNEL_TAGS:
        errors.append("secondary_channel_tag must be null or a valid channel tag.")

    primary_value_tag = record.get("primary_value_tag")
    if primary_value_tag not in PRIMARY_VALUE_TAGS:
        errors.append("primary_value_tag must be present and valid.")
    elif (
        primary_value_tag == "鸡肋"
        and needs_manual_review is True
        and not _contains_any(parse_note, VALUE_PLACEHOLDER_MARKERS)
    ):
        errors.append("placeholder primary_value_tag=鸡肋 requires parse_note to explain the placeholder or unreliable value judgment.")

    secondary_value_tag = record.get("secondary_value_tag")
    if secondary_value_tag is not None and secondary_value_tag not in SECONDARY_VALUE_TAGS:
        errors.append("secondary_value_tag must be null or a valid secondary value tag.")

    status = record.get("status")
    if record_type == "task":
        if status not in TASK_STATUSES:
            errors.append("task.status must be one of active/done/cancelled/paused.")
    elif status is not None:
        errors.append("non-task records must have status set to None.")

    value = record.get("value")
    unit = record.get("unit")
    if (value is None) != (unit is None):
        errors.append("value and unit must both be null or both be present.")
    if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        errors.append("value must be a number and cannot be bool when it is present.")
    if unit is not None and (not isinstance(unit, str) or unit.strip() == ""):
        errors.append("unit must be a non-empty string when it is present.")

    duration_min = record.get("duration_min")
    if duration_min is not None:
        if not isinstance(duration_min, int) or isinstance(duration_min, bool) or duration_min < 0:
            errors.append("duration_min must be a non-negative integer or null.")

    event_time = record.get("event_time")
    if event_time is not None:
        if not isinstance(event_time, str) or not EVENT_TIME_PATTERN.fullmatch(event_time):
            errors.append("event_time must be null or use the format YYYY-MM-DD HH:MM.")

    related_to = record.get("related_to")
    if related_to == "":
        errors.append("related_to must be null or a valid temp_n candidate_id, not an empty string.")
    elif related_to is not None and (not isinstance(related_to, str) or not ID_PATTERN.fullmatch(related_to)):
        errors.append("related_to must be null or a valid temp_n candidate_id.")
    elif related_to is not None and record_type != "state":
        errors.append("related_to may only be used on type=state records.")

    if event_time is not None and _is_temporary_field_note(parse_note, EVENT_TIME_FIELD_MARKERS):
        if needs_manual_review is not True:
            errors.append("temporary event_time candidates must set needs_manual_review=true.")

    if duration_min is not None and _is_temporary_field_note(parse_note, DURATION_FIELD_MARKERS):
        if needs_manual_review is not True:
            errors.append("temporary duration_min candidates must set needs_manual_review=true.")

    return errors


def validate_candidate_payload(payload: dict[str, Any]) -> list[str]:
    """Validate a full candidate payload under the frozen v0.1 protocol."""
    errors: list[str] = []

    if not isinstance(payload, dict):
        return ["payload must be an object."]

    expected_top_level_keys = {"schema_version", "bundle_id", "records"}
    payload_keys = set(payload.keys())
    if payload_keys != expected_top_level_keys:
        errors.append("payload must contain only schema_version, bundle_id, and records.")

    if payload.get("schema_version") != "v0.1":
        errors.append("schema_version must be v0.1.")

    bundle_id = payload.get("bundle_id")
    if not isinstance(bundle_id, str) or not BUNDLE_PATTERN.fullmatch(bundle_id):
        errors.append("bundle_id must use the bun_000001 format.")

    records = payload.get("records")
    if not isinstance(records, list) or not records:
        errors.append("records must be a non-empty list.")
        return errors

    candidate_ids: set[str] = set()
    main_candidates: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"records[{index}] must be an object.")
            continue

        record_errors = validate_record(record)
        errors.extend(f"records[{index}]: {message}" for message in record_errors)

        candidate_id = record.get("candidate_id")
        if isinstance(candidate_id, str) and ID_PATTERN.fullmatch(candidate_id):
            if candidate_id in candidate_ids:
                errors.append(f"records[{index}]: candidate_id must be unique within the bundle.")
            else:
                candidate_ids.add(candidate_id)

        related_to = record.get("related_to")
        record_type = record.get("type")
        if related_to is None:
            if record_type == "state":
                errors.append(f"records[{index}]: state cannot be the main candidate.")
            elif record_type in ALLOWED_TYPES:
                main_candidates.append(record)

    if len(main_candidates) != 1:
        errors.append("each bundle must contain exactly one main candidate.")

    main_candidate_id = None
    if len(main_candidates) == 1:
        main_candidate_id = main_candidates[0].get("candidate_id")

    for index, record in enumerate(records):
        related_to = record.get("related_to")
        if related_to is None:
            continue

        if related_to not in candidate_ids:
            errors.append(f"records[{index}]: related_to must reference an existing candidate_id in the same bundle.")
            continue

        if main_candidate_id is not None and related_to != main_candidate_id:
            errors.append(f"records[{index}]: related_to must reference the bundle's main candidate.")

    return errors


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _is_temporary_field_note(parse_note: str, field_markers: tuple[str, ...]) -> bool:
    return _contains_any(parse_note, field_markers) and _contains_any(parse_note, TEMPORARY_MARKERS)
