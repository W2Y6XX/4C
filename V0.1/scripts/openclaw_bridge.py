"""Local bridge commands for the frozen OpenClaw -> MVP handoff.

This module does not expose an HTTP server. It only provides a small CLI and
callable functions that OpenClaw can invoke locally.

The bridge deliberately keeps its own state under a separate directory instead
of extending the main SQLite schema. That bridge state stores:
- session_key: OpenClaw-facing conversation key
- flow_session: the in-memory FlowManager session snapshot
- db_session_id: the persisted flow_sessions.session_id in SQLite
- bundle_id: the current candidate bundle
- latest_candidate_summary: a compact summary for quick inspection

Important distinction:
- flow_session is an in-memory protocol session managed by FlowManager
- db_session_id is the persisted session row ID managed by db.py

The bridge never assumes they are the same identity source.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = Path("/opt/negative-entropy/v0.1/data/mvp.sqlite3")
DEFAULT_STATE_DIR = Path("/opt/negative-entropy/v0.1/data/bridge_state")
DEFAULT_LOG_PATH = Path("/opt/negative-entropy/v0.1/logs/bridge.log")
DB_PATH = Path(os.environ.get("NEGATIVE_ENTROPY_DB_PATH", str(DEFAULT_DB_PATH)))
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
STATE_DIR = Path(os.environ.get("NEGATIVE_ENTROPY_BRIDGE_STATE_DIR", str(DEFAULT_STATE_DIR)))
LOG_PATH = Path(os.environ.get("NEGATIVE_ENTROPY_BRIDGE_LOG_PATH", str(DEFAULT_LOG_PATH)))
FSYQ_TEMPLATE_PATH = PROJECT_ROOT / "config" / "fsyq_template.txt"

SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import db  # noqa: E402
from flow_manager import FlowManager  # noqa: E402
from validator import validate_candidate_payload  # noqa: E402


SESSION_KEY_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def command_start() -> str:
    """Return the frozen FSYQ template text for OpenClaw to display."""
    template = FSYQ_TEMPLATE_PATH.read_text(encoding="utf-8")
    _log("start template requested")
    return template


def command_parse(session_key: str, raw_input: str) -> str:
    """Create a new bridge session, parse input, persist latest candidate state, and summarize it."""
    _validate_session_key(session_key)
    raw_input = _coerce_text(raw_input, "raw_input")
    state_path = _state_file_path(session_key)
    if state_path.exists():
        raise ValueError(f"session_key {session_key!r} already exists; use revise/commit/cancel.")

    _ensure_runtime_paths()
    conn = db.connect_db(str(DB_PATH))
    try:
        db.init_db(conn, str(SCHEMA_PATH))

        manager = FlowManager()
        flow_session = manager.start_session(raw_input)
        parsed_session = manager.parse_session(flow_session)
        candidate_payload = parsed_session["candidate_payload"]
        _assert_payload_valid(candidate_payload)

        db_session_id = db.insert_flow_session(
            conn,
            raw_input=raw_input,
            candidate_payload=None,
            flow_state="awaiting_input",
            last_user_revision=None,
        )
        db.update_candidate_payload(
            conn,
            session_id=db_session_id,
            candidate_payload=candidate_payload,
            last_user_revision=None,
            flow_state="awaiting_confirmation",
        )

        bridge_state = {
            "session_key": session_key,
            "flow_session": parsed_session,
            "db_session_id": db_session_id,
            "bundle_id": candidate_payload["bundle_id"],
            "latest_candidate_summary": _summarize_candidate_payload(candidate_payload),
            "persisted_record_ids": [],
        }
        _write_bridge_state(session_key, bridge_state)
        _log(f"parse completed session_key={session_key} db_session_id={db_session_id}")
        return _format_candidate_summary("parsed", bridge_state)
    finally:
        conn.close()


def command_revise(session_key: str, revision_text: str) -> str:
    """Re-parse a revised input and overwrite the latest candidate payload in SQLite and bridge state."""
    _validate_session_key(session_key)
    revision_text = _coerce_text(revision_text, "revision_text")
    bridge_state = _read_bridge_state(session_key)
    if bridge_state["flow_session"]["flow_state"] == "cancelled":
        raise ValueError("cannot revise a cancelled bridge session.")

    _ensure_runtime_paths()
    conn = db.connect_db(str(DB_PATH))
    try:
        db.init_db(conn, str(SCHEMA_PATH))

        manager = FlowManager()
        revised_session = manager.apply_user_revision(bridge_state["flow_session"], revision_text)
        candidate_payload = revised_session["candidate_payload"]
        _assert_payload_valid(candidate_payload)

        db.update_candidate_payload(
            conn,
            session_id=bridge_state["db_session_id"],
            candidate_payload=candidate_payload,
            last_user_revision=revision_text,
            flow_state="awaiting_confirmation",
        )

        bridge_state["flow_session"] = revised_session
        bridge_state["bundle_id"] = candidate_payload["bundle_id"]
        bridge_state["latest_candidate_summary"] = _summarize_candidate_payload(candidate_payload)
        _write_bridge_state(session_key, bridge_state)
        _log(f"revise completed session_key={session_key} db_session_id={bridge_state['db_session_id']}")
        return _format_candidate_summary("revised", bridge_state)
    finally:
        conn.close()


def command_commit(session_key: str) -> str:
    """Confirm the current candidate payload, persist records, and return bundle/record IDs."""
    _validate_session_key(session_key)
    bridge_state = _read_bridge_state(session_key)

    if bridge_state.get("persisted_record_ids"):
        return _format_commit_result(
            bundle_id=bridge_state["bundle_id"],
            record_ids=bridge_state["persisted_record_ids"],
            db_session_id=bridge_state["db_session_id"],
            already_committed=True,
        )
    if bridge_state["flow_session"]["flow_state"] == "cancelled":
        raise ValueError("cannot commit a cancelled bridge session.")

    _ensure_runtime_paths()
    conn = db.connect_db(str(DB_PATH))
    try:
        db.init_db(conn, str(SCHEMA_PATH))

        manager = FlowManager()
        committed_session = manager.confirm_candidates(bridge_state["flow_session"])
        candidate_payload = committed_session["candidate_payload"]
        _assert_payload_valid(candidate_payload)

        db.update_flow_session_state(conn, bridge_state["db_session_id"], "committed")
        bundle_id, record_ids = db.insert_records(
            conn,
            bundle_id=candidate_payload["bundle_id"],
            records=candidate_payload["records"],
        )

        bridge_state["flow_session"] = committed_session
        bridge_state["bundle_id"] = bundle_id
        bridge_state["latest_candidate_summary"] = _summarize_candidate_payload(candidate_payload)
        bridge_state["persisted_record_ids"] = record_ids
        _write_bridge_state(session_key, bridge_state)
        _log(f"commit completed session_key={session_key} bundle_id={bundle_id}")
        return _format_commit_result(
            bundle_id=bundle_id,
            record_ids=record_ids,
            db_session_id=bridge_state["db_session_id"],
            already_committed=False,
        )
    finally:
        conn.close()


def command_cancel(session_key: str) -> str:
    """Cancel the current bridge session and persist flow_state=cancelled in SQLite."""
    _validate_session_key(session_key)
    bridge_state = _read_bridge_state(session_key)
    if bridge_state.get("persisted_record_ids"):
        raise ValueError("cannot cancel a session that has already been committed to records.")

    _ensure_runtime_paths()
    conn = db.connect_db(str(DB_PATH))
    try:
        db.init_db(conn, str(SCHEMA_PATH))

        manager = FlowManager()
        cancelled_session = manager.cancel_session(bridge_state["flow_session"])
        db.update_flow_session_state(conn, bridge_state["db_session_id"], "cancelled")

        bridge_state["flow_session"] = cancelled_session
        _write_bridge_state(session_key, bridge_state)
        _log(f"cancel completed session_key={session_key} db_session_id={bridge_state['db_session_id']}")
        return (
            f"cancelled\n"
            f"session_key={session_key}\n"
            f"flow_session_id={cancelled_session['session_id']}\n"
            f"db_session_id={bridge_state['db_session_id']}\n"
            f"flow_state={cancelled_session['flow_state']}"
        )
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    """Dispatch a local bridge command and print a concise OpenClaw-facing result."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "start":
            output = command_start()
        elif args.command == "parse":
            output = command_parse(args.session_key, _coerce_cli_text(args.raw_input, "raw_input"))
        elif args.command == "revise":
            output = command_revise(args.session_key, _coerce_cli_text(args.revision_text, "revision_text"))
        elif args.command == "commit":
            output = command_commit(args.session_key)
        elif args.command == "cancel":
            output = command_cancel(args.session_key)
        else:
            raise ValueError(f"unsupported command: {args.command}")
    except Exception as exc:
        _log(f"error command={getattr(args, 'command', 'unknown')} error={exc}")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local OpenClaw bridge for the frozen v0.1 MVP.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("start", help="Print the frozen FSYQ template.")

    parse_parser = subparsers.add_parser("parse", help="Create a bridge session and parse raw_input.")
    parse_parser.add_argument("--session-key", required=True, help="OpenClaw-side session key.")
    parse_parser.add_argument("--raw-input", help="Raw input text. If omitted, stdin will be used.")

    revise_parser = subparsers.add_parser("revise", help="Apply a user revision to an existing session.")
    revise_parser.add_argument("--session-key", required=True, help="OpenClaw-side session key.")
    revise_parser.add_argument("--revision-text", help="Revised input text. If omitted, stdin will be used.")

    commit_parser = subparsers.add_parser("commit", help="Commit the latest candidate payload into records.")
    commit_parser.add_argument("--session-key", required=True, help="OpenClaw-side session key.")

    cancel_parser = subparsers.add_parser("cancel", help="Cancel an existing bridge session.")
    cancel_parser.add_argument("--session-key", required=True, help="OpenClaw-side session key.")

    return parser


def _coerce_cli_text(text: str | None, field_name: str) -> str:
    if text is not None and text.strip():
        return text
    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read()
        if stdin_text.strip():
            return stdin_text
    raise ValueError(f"{field_name} must be provided via argument or stdin.")


def _coerce_text(text: str, field_name: str) -> str:
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


def _validate_session_key(session_key: str) -> None:
    if not isinstance(session_key, str) or session_key.strip() == "":
        raise ValueError("session_key must be a non-empty string.")


def _ensure_runtime_paths() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _read_bridge_state(session_key: str) -> dict[str, Any]:
    state_path = _state_file_path(session_key)
    if not state_path.exists():
        raise FileNotFoundError(f"bridge state not found for session_key {session_key!r}.")
    return json.loads(state_path.read_text(encoding="utf-8"))


def _write_bridge_state(session_key: str, bridge_state: dict[str, Any]) -> None:
    _ensure_runtime_paths()
    state_path = _state_file_path(session_key)
    state_path.write_text(json.dumps(bridge_state, ensure_ascii=False, indent=2), encoding="utf-8")


def _state_file_path(session_key: str) -> Path:
    sanitized = SESSION_KEY_FILENAME_PATTERN.sub("_", session_key.strip())
    if not sanitized:
        raise ValueError("session_key cannot be reduced to an empty filename.")
    return STATE_DIR / f"{sanitized}.json"


def _assert_payload_valid(candidate_payload: dict[str, Any]) -> None:
    errors = validate_candidate_payload(candidate_payload)
    if errors:
        raise ValueError("; ".join(errors))


def _summarize_candidate_payload(candidate_payload: dict[str, Any]) -> dict[str, Any]:
    records = candidate_payload["records"]
    main_record = next(record for record in records if record.get("related_to") is None)
    manual_review_count = sum(1 for record in records if record.get("needs_manual_review") is True)
    return {
        "bundle_id": candidate_payload["bundle_id"],
        "record_count": len(records),
        "main_type": main_record["type"],
        "main_subject": main_record["subject"],
        "manual_review_count": manual_review_count,
    }


def _format_candidate_summary(action: str, bridge_state: dict[str, Any]) -> str:
    summary = bridge_state["latest_candidate_summary"]
    flow_session = bridge_state["flow_session"]
    return (
        f"{action}\n"
        f"session_key={bridge_state['session_key']}\n"
        f"flow_session_id={flow_session['session_id']}\n"
        f"db_session_id={bridge_state['db_session_id']}\n"
        f"bundle_id={summary['bundle_id']}\n"
        f"flow_state={flow_session['flow_state']}\n"
        f"main_type={summary['main_type']}\n"
        f"main_subject={summary['main_subject']}\n"
        f"record_count={summary['record_count']}\n"
        f"manual_review_count={summary['manual_review_count']}"
    )


def _format_commit_result(
    bundle_id: str,
    record_ids: list[str],
    db_session_id: str,
    already_committed: bool,
) -> str:
    status_line = "already_committed" if already_committed else "committed"
    return (
        f"{status_line}\n"
        f"db_session_id={db_session_id}\n"
        f"bundle_id={bundle_id}\n"
        f"record_ids={','.join(record_ids)}"
    )


def _log(message: str) -> None:
    _ensure_runtime_paths()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


if __name__ == "__main__":
    raise SystemExit(main())
