import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import db  # noqa: E402
import openclaw_bridge  # noqa: E402


class OpenClawBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="openclaw_bridge_test_")
        self.addCleanup(self.temp_dir.cleanup)

        base_dir = Path(self.temp_dir.name)
        openclaw_bridge.DB_PATH = base_dir / "data" / "mvp.sqlite3"
        openclaw_bridge.STATE_DIR = base_dir / "bridge_state"
        openclaw_bridge.LOG_PATH = base_dir / "logs" / "bridge.log"

    def test_start_outputs_template(self):
        output = openclaw_bridge.command_start()
        expected = openclaw_bridge.FSYQ_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertEqual(output, expected)

    def test_parse_generates_candidates_and_writes_state(self):
        output = openclaw_bridge.command_parse(
            session_key="case_parse",
            raw_input="今晚九点左右推进了协议字段整理，有点疲劳",
        )
        self.assertIn("parsed", output)
        self.assertIn("bundle_id=", output)

        state_path = openclaw_bridge._state_file_path("case_parse")
        self.assertTrue(state_path.exists())

        bridge_state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("flow_session", bridge_state)
        self.assertIn("db_session_id", bridge_state)
        self.assertIn("bundle_id", bridge_state)
        self.assertIn("latest_candidate_summary", bridge_state)
        self.assertEqual(bridge_state["flow_session"]["flow_state"], "awaiting_confirmation")

    def test_revise_overwrites_latest_candidate(self):
        openclaw_bridge.command_parse(
            session_key="case_revise",
            raw_input="今晚九点左右推进了协议字段整理",
        )
        before_state = json.loads(
            openclaw_bridge._state_file_path("case_revise").read_text(encoding="utf-8")
        )
        before_payload = before_state["flow_session"]["candidate_payload"]

        output = openclaw_bridge.command_revise(
            session_key="case_revise",
            revision_text="2026-03-30 21:00 推进了协议字段整理与校验规则",
        )
        self.assertIn("revised", output)

        after_state = json.loads(
            openclaw_bridge._state_file_path("case_revise").read_text(encoding="utf-8")
        )
        after_payload = after_state["flow_session"]["candidate_payload"]
        self.assertNotEqual(before_payload, after_payload)

        conn = db.connect_db(str(openclaw_bridge.DB_PATH))
        try:
            row = conn.execute(
                "SELECT candidate_payload, last_user_revision FROM flow_sessions WHERE session_id = ?",
                (after_state["db_session_id"],),
            ).fetchone()
            self.assertEqual(json.loads(row["candidate_payload"]), after_payload)
            self.assertEqual(row["last_user_revision"], "2026-03-30 21:00 推进了协议字段整理与校验规则")
        finally:
            conn.close()

    def test_commit_writes_records_and_returns_bundle_and_record_ids(self):
        openclaw_bridge.command_parse(
            session_key="case_commit",
            raw_input="今晚九点左右推进了协议字段整理，有点疲劳",
        )
        output = openclaw_bridge.command_commit("case_commit")

        self.assertIn("committed", output)
        self.assertIn("bundle_id=", output)
        self.assertIn("record_ids=", output)

        bridge_state = json.loads(
            openclaw_bridge._state_file_path("case_commit").read_text(encoding="utf-8")
        )
        record_ids = bridge_state["persisted_record_ids"]
        self.assertTrue(record_ids)

        conn = db.connect_db(str(openclaw_bridge.DB_PATH))
        try:
            rows = db.fetch_records_by_bundle(conn, bridge_state["bundle_id"])
            self.assertEqual(len(rows), len(bridge_state["flow_session"]["candidate_payload"]["records"]))
            self.assertEqual([row["record_id"] for row in rows], record_ids)
            for row in rows:
                self.assertEqual(row["source"], "openclaw")
                if isinstance(row["related_to"], str):
                    self.assertFalse(row["related_to"].startswith("temp_"))
        finally:
            conn.close()

    def test_cancel_updates_flow_state_cancelled(self):
        openclaw_bridge.command_parse(
            session_key="case_cancel",
            raw_input="推进了协议字段整理",
        )
        output = openclaw_bridge.command_cancel("case_cancel")
        self.assertIn("cancelled", output)
        self.assertIn("flow_state=cancelled", output)

        bridge_state = json.loads(
            openclaw_bridge._state_file_path("case_cancel").read_text(encoding="utf-8")
        )
        self.assertEqual(bridge_state["flow_session"]["flow_state"], "cancelled")

        conn = db.connect_db(str(openclaw_bridge.DB_PATH))
        try:
            row = conn.execute(
                "SELECT flow_state FROM flow_sessions WHERE session_id = ?",
                (bridge_state["db_session_id"],),
            ).fetchone()
            self.assertEqual(row["flow_state"], "cancelled")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
