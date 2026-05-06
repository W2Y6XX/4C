import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from flow_manager import FlowManager
from validator import validate_candidate_payload


class FlowManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = FlowManager()

    def test_start_session_uses_awaiting_input(self):
        session = self.manager.start_session("写了协议初稿")
        self.assertEqual(session["flow_state"], "awaiting_input")
        self.assertIsNone(session["candidate_payload"])
        self.assertTrue(session["session_id"].startswith("ses_"))

    def test_parse_session_stores_latest_candidate_payload(self):
        session = self.manager.start_session("推进协议字段整理")
        parsed_session = self.manager.parse_session(session)
        self.assertEqual(parsed_session["flow_state"], "awaiting_confirmation")
        self.assertIsInstance(parsed_session["candidate_payload"], dict)
        self.assertEqual(validate_candidate_payload(parsed_session["candidate_payload"]), [])

    def test_main_candidate_priority_prefers_action_over_task(self):
        payload = self.manager.parse_input_to_candidates("整理了协议，同时需要补充测试")
        main_record = payload["records"][0]
        self.assertEqual(main_record["type"], "action")
        self.assertIsNone(main_record["related_to"])

    def test_state_is_generated_as_independent_record(self):
        payload = self.manager.parse_input_to_candidates(
            "1. 事件：写了协议初稿\n2. 状态：很疲劳但还能专注\n3. 时间：今晚九点"
        )
        self.assertEqual(len(payload["records"]), 2)
        main_record = payload["records"][0]
        state_record = payload["records"][1]
        self.assertEqual(main_record["type"], "action")
        self.assertEqual(state_record["type"], "state")
        self.assertEqual(state_record["related_to"], main_record["candidate_id"])

    def test_placeholder_notes_exist_when_manual_review_and_default_tags_are_used(self):
        payload = self.manager.parse_input_to_candidates("随手记一下")
        main_record = payload["records"][0]
        self.assertTrue(main_record["needs_manual_review"])
        self.assertEqual(main_record["primary_channel_tag"], "system_building")
        self.assertEqual(main_record["primary_value_tag"], "鸡肋")
        self.assertIn("占位", main_record["parse_note"])
        self.assertIn("无法可靠判断通道", main_record["parse_note"])
        self.assertIn("无法可靠判断价值", main_record["parse_note"])

    def test_system_building_can_be_real_judgment_when_manual_review_is_false(self):
        payload = self.manager.parse_input_to_candidates("推进了协议字段整理")
        main_record = payload["records"][0]
        self.assertFalse(main_record["needs_manual_review"])
        self.assertEqual(main_record["primary_channel_tag"], "system_building")
        self.assertEqual(main_record["primary_value_tag"], "高价值")
        self.assertNotIn("无法可靠判断通道", main_record["parse_note"])

    def test_jile_can_be_real_judgment_when_manual_review_is_false(self):
        payload = self.manager.parse_input_to_candidates("处理了不得不做的杂务")
        main_record = payload["records"][0]
        self.assertFalse(main_record["needs_manual_review"])
        self.assertEqual(main_record["primary_value_tag"], "鸡肋")
        self.assertNotIn("无法可靠判断价值", main_record["parse_note"])

    def test_real_system_building_with_manual_review_should_not_be_forced_as_placeholder(self):
        payload = self.manager.parse_input_to_candidates("今晚九点左右推进了协议字段整理")
        main_record = payload["records"][0]
        self.assertEqual(main_record["primary_channel_tag"], "system_building")
        self.assertTrue(main_record["needs_manual_review"])
        self.assertIn("event_time 为临时候选", main_record["parse_note"])
        self.assertNotIn("无法可靠判断通道", main_record["parse_note"])
        self.assertNotIn("primary_channel_tag 使用占位值 system_building", main_record["parse_note"])

    def test_real_jile_with_manual_review_should_not_be_forced_as_placeholder(self):
        payload = self.manager.parse_input_to_candidates("今晚九点左右处理了不得不做的杂务")
        main_record = payload["records"][0]
        self.assertEqual(main_record["primary_value_tag"], "鸡肋")
        self.assertTrue(main_record["needs_manual_review"])
        self.assertIn("event_time 为临时候选", main_record["parse_note"])
        self.assertNotIn("无法可靠判断价值", main_record["parse_note"])
        self.assertNotIn("primary_value_tag 使用占位值 鸡肋", main_record["parse_note"])

    def test_explicit_numeric_duration_should_not_be_temporary_candidate(self):
        payload = self.manager.parse_input_to_candidates("推进了协议字段整理 45分钟")
        main_record = payload["records"][0]
        self.assertEqual(main_record["duration_min"], 45)
        self.assertFalse(main_record["needs_manual_review"])
        self.assertIn("明确数字时长直接抽取", main_record["parse_note"])
        self.assertNotIn("duration_min 为临时候选", main_record["parse_note"])

    def test_revision_overwrites_candidate_payload_and_keeps_bundle_id(self):
        session = self.manager.start_session("推进协议字段整理")
        parsed_session = self.manager.parse_session(session)
        original_bundle_id = parsed_session["candidate_payload"]["bundle_id"]

        revised_session = self.manager.apply_user_revision(parsed_session, "复盘协议结构并补充测试")
        revised_payload = revised_session["candidate_payload"]

        self.assertEqual(revised_session["flow_state"], "awaiting_confirmation")
        self.assertEqual(revised_session["last_user_revision"], "复盘协议结构并补充测试")
        self.assertEqual(revised_payload["bundle_id"], original_bundle_id)
        self.assertEqual(revised_payload["records"][0]["type"], "review_note")

    def test_confirm_candidates_sets_committed(self):
        session = self.manager.start_session("推进协议字段整理")
        parsed_session = self.manager.parse_session(session)
        committed_session = self.manager.confirm_candidates(parsed_session)
        self.assertEqual(committed_session["flow_state"], "committed")
        self.assertEqual(validate_candidate_payload(committed_session["candidate_payload"]), [])

    def test_cancel_session_sets_cancelled(self):
        session = self.manager.start_session("推进协议字段整理")
        cancelled_session = self.manager.cancel_session(session)
        self.assertEqual(cancelled_session["flow_state"], "cancelled")

    def test_build_candidate_payload_validates_before_return(self):
        class BrokenFlowManager(FlowManager):
            def _build_main_record(self, event_text):
                record = super()._build_main_record(event_text)
                del record["parse_note"]
                return record

        broken_manager = BrokenFlowManager()
        with self.assertRaises(ValueError):
            broken_manager.parse_input_to_candidates("写了协议初稿")


if __name__ == "__main__":
    unittest.main()
