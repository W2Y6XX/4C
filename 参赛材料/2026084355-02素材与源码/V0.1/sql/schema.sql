PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS flow_sessions (
    session_id TEXT PRIMARY KEY CHECK (session_id GLOB 'ses_[0-9][0-9][0-9][0-9][0-9][0-9]'),
    raw_input TEXT NOT NULL,
    last_user_revision TEXT,
    candidate_payload TEXT,
    flow_state TEXT NOT NULL CHECK (
        flow_state IN (
            'awaiting_input',
            'parsing',
            'awaiting_confirmation',
            'revising',
            'committed',
            'cancelled'
        )
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- NOTE: candidate_payload stores only the latest candidate JSON for the session.
-- NOTE: when the user revises a candidate set, candidate_payload must be overwritten with the newest JSON.
-- NOTE: session_id generation is fixed to ses_000001 upward and must use current MAX(session_id) + 1 in application code.
-- NOTE: IDs must never be reused, even if rows are deleted; SQLite DDL alone does not safely enforce that rule under the frozen protocol.

CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY CHECK (record_id GLOB 'rec_[0-9][0-9][0-9][0-9][0-9][0-9]'),
    bundle_id TEXT NOT NULL CHECK (bundle_id GLOB 'bun_[0-9][0-9][0-9][0-9][0-9][0-9]'),
    related_to TEXT,
    event_time TEXT CHECK (
        event_time IS NULL
        OR event_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]'
    ),
    recorded_at TEXT NOT NULL,
    type TEXT NOT NULL CHECK (
        type IN ('task', 'action', 'state', 'idea', 'review_note')
    ),
    content TEXT NOT NULL,
    subject TEXT NOT NULL CHECK (length(trim(subject)) > 0),
    value REAL,
    unit TEXT,
    duration_min INTEGER,
    primary_channel_tag TEXT NOT NULL CHECK (
        primary_channel_tag IN (
            'llm_engineering',
            'body_management',
            'teaching',
            'exam_prep',
            'mechanics_learning',
            'system_building',
            'daily_maintenance'
        )
    ),
    secondary_channel_tag TEXT CHECK (
        secondary_channel_tag IS NULL OR secondary_channel_tag IN (
            'llm_engineering',
            'body_management',
            'teaching',
            'exam_prep',
            'mechanics_learning',
            'system_building',
            'daily_maintenance'
        )
    ),
    primary_value_tag TEXT NOT NULL CHECK (
        primary_value_tag IN ('高价值', '鸡肋', '无用')
    ),
    secondary_value_tag TEXT CHECK (
        secondary_value_tag IS NULL OR secondary_value_tag IN ('恢复性', '不得不')
    ),
    status TEXT CHECK (
        (type = 'task' AND status IN ('active', 'done', 'cancelled', 'paused'))
        OR (type <> 'task' AND status IS NULL)
    ),
    source TEXT NOT NULL CHECK (source = 'openclaw'),
    CHECK (
        (value IS NULL AND unit IS NULL)
        OR (value IS NOT NULL AND unit IS NOT NULL)
    ),
    CHECK (
        secondary_channel_tag IS NULL OR secondary_channel_tag <> primary_channel_tag
    )
);

CREATE INDEX IF NOT EXISTS idx_records_bundle_id ON records(bundle_id);
CREATE INDEX IF NOT EXISTS idx_records_related_to ON records(related_to);
CREATE INDEX IF NOT EXISTS idx_flow_sessions_state ON flow_sessions(flow_state);

-- NOTE: bundle_id generation is fixed to bun_000001 upward and must use current MAX(bundle_id) + 1 in application code.
-- NOTE: record_id generation is fixed to rec_000001 upward and must use current MAX(record_id) + 1 in application code.
-- NOTE: IDs must never be reused, even if rows are deleted; this is an application-level guarantee for v0.1.
-- NOTE: related_to may only point to a main record inside the same bundle, but SQLite CHECK cannot express this cross-row rule cleanly without adding non-protocol triggers or helper tables.
-- NOTE: event_time receives only a minimal SQL format check. Validator remains the main enforcement layer for semantic correctness and temporary-candidate review rules.
-- NOTE: primary_channel_tag defaults to system_building and primary_value_tag defaults to 鸡肋 only at candidate-generation time, not at storage time; if placeholders were used, candidate parse_note must explain that reason before commit.
