"""SQLite helpers for the frozen v0.1 protocol."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

FLOW_STATES = {
    "awaiting_input",
    "parsing",
    "awaiting_confirmation",
    "revising",
    "committed",
    "cancelled",
}

SESSION_ID_PATTERN = re.compile(r"^ses_[0-9]{6}$")
BUNDLE_ID_PATTERN = re.compile(r"^bun_[0-9]{6}$")
RECORD_ID_PATTERN = re.compile(r"^rec_[0-9]{6}$")
TEMP_CANDIDATE_ID_PATTERN = re.compile(r"^temp_[0-9]+$")


def connect_db(path: str) -> sqlite3.Connection:
    """Open a SQLite connection configured for dict-like row access."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection, schema_sql_path: str) -> None:
    """Initialize the database using the frozen schema.sql file."""
    schema_sql = Path(schema_sql_path).read_text(encoding="utf-8")
    with conn:
        conn.executescript(schema_sql)


def insert_flow_session(
    conn: sqlite3.Connection,
    raw_input: str,
    candidate_payload: Any | None = None,
    flow_state: str = "awaiting_input",
    last_user_revision: str | None = None,
) -> str:
    """Insert one flow session and return the generated session_id."""
    _require_non_blank_text(raw_input, "raw_input")
    _validate_flow_state(flow_state)

    session_id = _format_identifier(_next_sequence_number(conn, "flow_sessions", "session_id", "ses_"), "ses_")
    now = _now_string()
    payload_json = _serialize_candidate_payload(candidate_payload)

    with conn:
        conn.execute(
            """
            INSERT INTO flow_sessions (
                session_id,
                raw_input,
                last_user_revision,
                candidate_payload,
                flow_state,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                raw_input,
                last_user_revision,
                payload_json,
                flow_state,
                now,
                now,
            ),
        )
    return session_id


def update_flow_session_state(conn: sqlite3.Connection, session_id: str, flow_state: str) -> None:
    """Update only the flow_state of an existing session."""
    _validate_identifier(session_id, SESSION_ID_PATTERN, "session_id")
    _validate_flow_state(flow_state)

    with conn:
        cursor = conn.execute(
            """
            UPDATE flow_sessions
            SET flow_state = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (flow_state, _now_string(), session_id),
        )
    _ensure_row_updated(cursor, f"flow session {session_id}")


def update_candidate_payload(
    conn: sqlite3.Connection,
    session_id: str,
    candidate_payload: Any,
    last_user_revision: str | None = None,
    flow_state: str | None = None,
) -> None:
    """Overwrite candidate_payload with the current latest candidate JSON."""
    _validate_identifier(session_id, SESSION_ID_PATTERN, "session_id")
    if flow_state is not None:
        _validate_flow_state(flow_state)

    current_session = conn.execute(
        "SELECT flow_state FROM flow_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if current_session is None:
        raise ValueError(f"flow session {session_id} does not exist.")

    resolved_flow_state = flow_state or current_session["flow_state"]
    payload_json = _serialize_candidate_payload(candidate_payload)

    with conn:
        cursor = conn.execute(
            """
            UPDATE flow_sessions
            SET candidate_payload = ?,
                last_user_revision = ?,
                flow_state = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                payload_json,
                last_user_revision,
                resolved_flow_state,
                _now_string(),
                session_id,
            ),
        )
    _ensure_row_updated(cursor, f"flow session {session_id}")


def insert_records(
    conn: sqlite3.Connection,
    bundle_id: str | None,
    records: Iterable[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    """Insert records for one bundle and return the resolved bundle_id plus new record_ids."""
    materialized_records = list(records)
    if not materialized_records:
        raise ValueError("records must be a non-empty iterable.")

    resolved_bundle_id = bundle_id or _format_identifier(
        _next_sequence_number(conn, "records", "bundle_id", "bun_"),
        "bun_",
    )
    _validate_identifier(resolved_bundle_id, BUNDLE_ID_PATTERN, "bundle_id")

    next_record_number = _next_sequence_number(conn, "records", "record_id", "rec_")
    now = _now_string()

    candidate_id_to_record_id: dict[str, str] = {}
    generated_record_ids: list[str] = []
    for offset, record in enumerate(materialized_records):
        record_id = _format_identifier(next_record_number + offset, "rec_")
        generated_record_ids.append(record_id)

        candidate_id = record.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id.strip():
            candidate_id_to_record_id[candidate_id] = record_id

    with conn:
        for record_id, record in zip(generated_record_ids, materialized_records):
            related_to = record.get("related_to")
            if isinstance(related_to, str) and TEMP_CANDIDATE_ID_PATTERN.fullmatch(related_to):
                if related_to not in candidate_id_to_record_id:
                    raise ValueError(f"related_to {related_to} could not be mapped to a record_id in the current batch.")
                persisted_related_to = candidate_id_to_record_id[related_to]
            else:
                persisted_related_to = related_to

            conn.execute(
                """
                INSERT INTO records (
                    record_id,
                    bundle_id,
                    related_to,
                    event_time,
                    recorded_at,
                    type,
                    content,
                    subject,
                    value,
                    unit,
                    duration_min,
                    primary_channel_tag,
                    secondary_channel_tag,
                    primary_value_tag,
                    secondary_value_tag,
                    status,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    resolved_bundle_id,
                    persisted_related_to,
                    record.get("event_time"),
                    now,
                    record.get("type"),
                    record.get("content"),
                    record.get("subject"),
                    record.get("value"),
                    record.get("unit"),
                    record.get("duration_min"),
                    record.get("primary_channel_tag"),
                    record.get("secondary_channel_tag"),
                    record.get("primary_value_tag"),
                    record.get("secondary_value_tag"),
                    record.get("status"),
                    "openclaw",
                ),
            )

    return resolved_bundle_id, generated_record_ids


def fetch_records_by_bundle(conn: sqlite3.Connection, bundle_id: str) -> list[dict[str, Any]]:
    """Fetch persisted records for one bundle_id ordered by record_id."""
    _validate_identifier(bundle_id, BUNDLE_ID_PATTERN, "bundle_id")
    rows = conn.execute(
        """
        SELECT
            record_id,
            bundle_id,
            related_to,
            event_time,
            recorded_at,
            type,
            content,
            subject,
            value,
            unit,
            duration_min,
            primary_channel_tag,
            secondary_channel_tag,
            primary_value_tag,
            secondary_value_tag,
            status,
            source
        FROM records
        WHERE bundle_id = ?
        ORDER BY record_id
        """,
        (bundle_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _next_sequence_number(conn: sqlite3.Connection, table: str, column: str, prefix: str) -> int:
    """Return the next zero-padded sequence number using the current max stored ID."""
    row = conn.execute(
        f"""
        SELECT {column}
        FROM {table}
        WHERE {column} GLOB ?
        ORDER BY {column} DESC
        LIMIT 1
        """,
        (f"{prefix}[0-9][0-9][0-9][0-9][0-9][0-9]",),
    ).fetchone()

    if row is None or row[column] is None:
        return 1

    current_identifier = row[column]
    try:
        return int(current_identifier.split("_", 1)[1]) + 1
    except (IndexError, ValueError) as exc:
        raise ValueError(f"stored identifier {current_identifier!r} is malformed.") from exc


def _format_identifier(number: int, prefix: str) -> str:
    return f"{prefix}{number:06d}"


def _serialize_candidate_payload(candidate_payload: Any | None) -> str | None:
    if candidate_payload is None:
        return None
    if isinstance(candidate_payload, str):
        if candidate_payload.strip() == "":
            raise ValueError("candidate_payload must not be an empty string.")
        return candidate_payload
    return json.dumps(candidate_payload, ensure_ascii=False, separators=(",", ":"))


def _validate_flow_state(flow_state: str) -> None:
    if flow_state not in FLOW_STATES:
        raise ValueError("flow_state must be one of the six frozen states.")


def _validate_identifier(value: str, pattern: re.Pattern[str], field_name: str) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{field_name} format is invalid.")


def _require_non_blank_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be a non-empty string.")


def _ensure_row_updated(cursor: sqlite3.Cursor, target: str) -> None:
    if cursor.rowcount != 1:
        raise ValueError(f"{target} was not updated.")


def _now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
