import json
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import db


def build_candidate_payload(bundle_id="bun_000001"):
    return {
        "schema_version": "v0.1",
        "bundle_id": bundle_id,
        "records": [
            {
                "candidate_id": "temp_1",
                "type": "action",
                "content": "推进了协议字段整理",
                "subject": "协议字段整理",
                "value": None,
                "unit": None,
                "duration_min": 45,
                "event_time": "2026-03-30 21:00",
                "primary_channel_tag": "system_building",
                "secondary_channel_tag": None,
                "primary_value_tag": "高价值",
                "secondary_value_tag": None,
                "status": None,
                "related_to": None,
                "needs_manual_review": False,
                "parse_note": "按规则直接抽取。",
            },
            {
                "candidate_id": "temp_2",
                "type": "state",
                "content": "有点疲劳",
                "subject": "疲劳",
                "value": None,
                "unit": None,
                "duration_min": None,
                "event_time": None,
                "primary_channel_tag": "system_building",
                "secondary_channel_tag": None,
                "primary_value_tag": "高价值",
                "secondary_value_tag": None,
                "status": None,
                "related_to": "temp_1",
                "needs_manual_review": False,
                "parse_note": "按规则拆分状态记录。",
            },
        ],
    }


class DbTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect_db(":memory:")
        db.init_db(self.conn, os.path.join(ROOT_DIR, "sql", "schema.sql"))

    def tearDown(self):
        self.conn.close()

    def test_insert_flow_session_generates_sequential_session_id(self):
        session_id = db.insert_flow_session(self.conn, raw_input="写了协议初稿")
        self.assertEqual(session_id, "ses_000001")

    def test_update_candidate_payload_overwrites_latest_candidate_json(self):
        session_id = db.insert_flow_session(self.conn, raw_input="写了协议初稿")
        first_payload = build_candidate_payload()
        second_payload = build_candidate_payload(bundle_id="bun_000002")

        db.update_candidate_payload(self.conn, session_id, first_payload, flow_state="awaiting_confirmation")
        db.update_candidate_payload(
            self.conn,
            session_id,
            second_payload,
            last_user_revision="修订后的输入",
            flow_state="revising",
        )

        row = self.conn.execute(
            "SELECT candidate_payload, last_user_revision, flow_state FROM flow_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        self.assertEqual(json.loads(row["candidate_payload"]), second_payload)
        self.assertEqual(row["last_user_revision"], "修订后的输入")
        self.assertEqual(row["flow_state"], "revising")

    def test_insert_records_maps_related_to_temp_id_to_record_id(self):
        payload = build_candidate_payload()
        bundle_id, record_ids = db.insert_records(self.conn, payload["bundle_id"], payload["records"])

        self.assertEqual(bundle_id, "bun_000001")
        self.assertEqual(record_ids, ["rec_000001", "rec_000002"])

        rows = db.fetch_records_by_bundle(self.conn, bundle_id)
        self.assertEqual(rows[0]["record_id"], "rec_000001")
        self.assertEqual(rows[1]["record_id"], "rec_000002")
        self.assertEqual(rows[1]["related_to"], "rec_000001")
        self.assertEqual(rows[0]["source"], "openclaw")

    def test_insert_records_raises_for_unmapped_temp_related_to(self):
        payload = build_candidate_payload()
        payload["records"][1]["related_to"] = "temp_99"

        with self.assertRaises(ValueError):
            db.insert_records(self.conn, payload["bundle_id"], payload["records"])

        count = self.conn.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"]
        self.assertEqual(count, 0)

    def test_fetch_records_by_bundle_returns_inserted_records(self):
        payload = build_candidate_payload()
        bundle_id, _ = db.insert_records(self.conn, payload["bundle_id"], payload["records"])

        rows = db.fetch_records_by_bundle(self.conn, bundle_id)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bundle_id"], bundle_id)
        self.assertEqual(rows[0]["subject"], "协议字段整理")
        self.assertEqual(rows[1]["type"], "state")


if __name__ == "__main__":
    unittest.main()
