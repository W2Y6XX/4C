import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from validator import validate_candidate_payload, validate_record


def build_record(**overrides):
    record = {
        "candidate_id": "temp_1",
        "type": "task",
        "content": "整理力学题目",
        "subject": "力学题目",
        "value": None,
        "unit": None,
        "duration_min": None,
        "event_time": None,
        "primary_channel_tag": "mechanics_learning",
        "secondary_channel_tag": None,
        "primary_value_tag": "高价值",
        "secondary_value_tag": None,
        "status": "active",
        "related_to": None,
        "needs_manual_review": False,
        "parse_note": "按规则直接抽取。",
    }
    record.update(overrides)
    return record


def build_payload(records):
    return {
        "schema_version": "v0.1",
        "bundle_id": "bun_000001",
        "records": records,
    }


class ValidatorTests(unittest.TestCase):
    def test_parse_note_is_required_on_every_record(self):
        record = build_record()
        del record["parse_note"]
        errors = validate_record(record)
        self.assertTrue(any("parse_note" in error for error in errors))

    def test_primary_channel_tag_and_primary_value_tag_cannot_be_empty(self):
        record = build_record(primary_channel_tag="", primary_value_tag="")
        errors = validate_record(record)
        self.assertTrue(any("primary_channel_tag" in error for error in errors))
        self.assertTrue(any("primary_value_tag" in error for error in errors))

    def test_placeholder_primary_channel_requires_parse_note_explanation(self):
        record = build_record(
            primary_channel_tag="system_building",
            needs_manual_review=True,
            parse_note="按规则直接抽取。",
        )
        errors = validate_record(record)
        self.assertTrue(any("placeholder primary_channel_tag=system_building" in error for error in errors))

    def test_placeholder_primary_value_requires_parse_note_explanation(self):
        record = build_record(
            primary_value_tag="鸡肋",
            needs_manual_review=True,
            parse_note="按规则直接抽取。",
        )
        errors = validate_record(record)
        self.assertTrue(any("placeholder primary_value_tag=鸡肋" in error for error in errors))

    def test_non_task_status_must_be_none(self):
        record = build_record(type="action", status="done")
        errors = validate_record(record)
        self.assertTrue(any("non-task" in error for error in errors))

    def test_task_status_must_be_one_of_four_values(self):
        record = build_record(status="queued")
        errors = validate_record(record)
        self.assertTrue(any("task.status" in error for error in errors))

    def test_value_and_unit_must_be_paired(self):
        record = build_record(value=30, unit=None)
        errors = validate_record(record)
        self.assertTrue(any("value and unit" in error for error in errors))

    def test_value_cannot_be_bool(self):
        record = build_record(value=True, unit="次")
        errors = validate_record(record)
        self.assertTrue(any("value must be a number" in error for error in errors))

    def test_unit_must_be_non_empty_string(self):
        record = build_record(value=3, unit="")
        errors = validate_record(record)
        self.assertTrue(any("unit must be a non-empty string" in error for error in errors))

    def test_duplicate_secondary_channel_is_cleared(self):
        record = build_record(
            primary_channel_tag="system_building",
            secondary_channel_tag="system_building",
        )
        errors = validate_record(record)
        self.assertEqual(errors, [])
        self.assertIsNone(record["secondary_channel_tag"])

    def test_subject_taiding_requires_explanation(self):
        record = build_record(subject="待定", parse_note="按规则直接抽取。")
        errors = validate_record(record)
        self.assertTrue(any("subject='待定'" in error for error in errors))

    def test_temporary_event_time_requires_manual_review_and_parse_note(self):
        record = build_record(
            event_time="2026-03-29 21:00",
            needs_manual_review=False,
            parse_note="event_time 为临时候选，待确认。",
        )
        errors = validate_record(record)
        self.assertTrue(any("temporary event_time" in error for error in errors))

    def test_temporary_duration_requires_manual_review_and_parse_note(self):
        record = build_record(
            duration_min=90,
            needs_manual_review=False,
            parse_note="duration_min 为临时估计值，待确认。",
        )
        errors = validate_record(record)
        self.assertTrue(any("temporary duration_min" in error for error in errors))

    def test_related_to_must_reference_main_candidate(self):
        payload = build_payload(
            [
                build_record(candidate_id="temp_1", type="task", status="active", related_to=None),
                build_record(
                    candidate_id="temp_2",
                    type="state",
                    status=None,
                    related_to="temp_3",
                    subject="状态描述",
                    parse_note="按规则拆分状态记录。",
                ),
            ]
        )
        errors = validate_candidate_payload(payload)
        self.assertTrue(any("related_to must reference an existing candidate_id" in error for error in errors))

    def test_related_to_requires_state_type(self):
        record = build_record(type="action", status=None, related_to="temp_1")
        errors = validate_record(record)
        self.assertTrue(any("related_to may only be used on type=state" in error for error in errors))

    def test_bundle_must_have_exactly_one_main_candidate(self):
        payload = build_payload(
            [
                build_record(candidate_id="temp_1", type="task", status="active", related_to=None),
                build_record(candidate_id="temp_2", type="idea", status=None, related_to=None),
            ]
        )
        errors = validate_candidate_payload(payload)
        self.assertTrue(any("exactly one main candidate" in error for error in errors))

    def test_state_cannot_be_main_candidate(self):
        payload = build_payload(
            [
                build_record(
                    candidate_id="temp_1",
                    type="state",
                    status=None,
                    related_to=None,
                    subject="状态描述",
                    parse_note="按规则拆分状态记录。",
                ),
            ]
        )
        errors = validate_candidate_payload(payload)
        self.assertTrue(any("state cannot be the main candidate" in error for error in errors))

    def test_related_to_empty_string_is_invalid(self):
        record = build_record(type="state", status=None, related_to="", subject="状态描述")
        errors = validate_record(record)
        self.assertTrue(any("related_to" in error for error in errors))

    def test_payload_must_not_have_extra_top_level_keys(self):
        payload = build_payload([build_record()])
        payload["extra"] = "forbidden"
        errors = validate_candidate_payload(payload)
        self.assertTrue(any("payload must contain only schema_version, bundle_id, and records" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
