-- Vanuoc v3.0 Authoritative SQLite Target Schema
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS core_schema_versions (
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version > 0),
    applied_at_utc REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS core_sessions (
    session_id TEXT PRIMARY KEY,
    channel TEXT NOT NULL CHECK (channel IN ('voice', 'web', 'cli')),
    auth_scope_ref TEXT NOT NULL,
    lifecycle TEXT NOT NULL CHECK (lifecycle IN ('active', 'ended')),
    created_at_utc REAL NOT NULL,
    ended_at_utc REAL,
    CHECK ((lifecycle = 'active' AND ended_at_utc IS NULL)
        OR (lifecycle = 'ended' AND ended_at_utc IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS core_requests (
    request_id TEXT PRIMARY KEY,
    engine_id TEXT NOT NULL,
    engine_revision TEXT NOT NULL,
    state_schema_version INTEGER NOT NULL CHECK (state_schema_version > 0),
    pinned_bundle_json TEXT NOT NULL CHECK (json_valid(pinned_bundle_json)),
    owner_kind TEXT NOT NULL CHECK (owner_kind IN ('ai', 'operator', 'none')),
    owner_session_id TEXT REFERENCES core_sessions(session_id),
    owner_generation INTEGER NOT NULL CHECK (owner_generation > 0),
    state_version INTEGER NOT NULL DEFAULT 0 CHECK (state_version >= 0),
    booking_status TEXT NOT NULL CHECK (booking_status IN (
        'collecting', 'awaiting_confirmation', 'submitting', 'request_recorded',
        'cancel_pending', 'cancelled', 'operator_required', 'submit_failed')),
    conversation_json TEXT NOT NULL CHECK (json_valid(conversation_json)),
    created_at_utc REAL NOT NULL,
    updated_at_utc REAL NOT NULL,
    resume_expires_at_utc REAL,
    CHECK (owner_kind != 'ai' OR owner_session_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS core_request_sessions (
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    session_id TEXT NOT NULL REFERENCES core_sessions(session_id),
    owner_generation_at_link INTEGER NOT NULL CHECK (owner_generation_at_link > 0),
    authorized_scope_ref TEXT NOT NULL,
    linked_at_utc REAL NOT NULL,
    PRIMARY KEY (request_id, session_id)
);

CREATE TABLE IF NOT EXISTS core_drafts (
    draft_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    booking_revision INTEGER NOT NULL DEFAULT 0 CHECK (booking_revision >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    slots_json TEXT NOT NULL CHECK (json_valid(slots_json)),
    location_evidence_json TEXT NOT NULL CHECK (json_valid(location_evidence_json)),
    updated_at_utc REAL NOT NULL,
    UNIQUE (draft_id, request_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS core_one_active_draft
    ON core_drafts(request_id) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS core_inputs (
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    input_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'user_turn', 'delivery', 'interrupt', 'timeout', 'session_end', 'ownership_changed')),
    canonical_input_hash TEXT NOT NULL CHECK (length(canonical_input_hash) = 64),
    session_id TEXT NOT NULL REFERENCES core_sessions(session_id),
    protected_payload_json TEXT CHECK (
        protected_payload_json IS NULL OR json_valid(protected_payload_json)),
    admitted_context_json TEXT NOT NULL CHECK (json_valid(admitted_context_json)),
    received_at_utc REAL NOT NULL,
    PRIMARY KEY (request_id, input_id)
);

CREATE TABLE IF NOT EXISTS core_turns (
    turn_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES core_sessions(session_id),
    expected_state_version INTEGER NOT NULL CHECK (expected_state_version >= 0),
    captured_owner_generation INTEGER NOT NULL CHECK (captured_owner_generation > 0),
    phase TEXT NOT NULL CHECK (phase IN (
        'admitted', 'preparing', 'committed', 'cancelled', 'stale',
        'deadline_exceeded', 'rejected', 'retryable_error')),
    executor_claim_token TEXT,
    executor_lease_expires_at_utc REAL,
    expires_at_utc REAL NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    committed_state_version INTEGER CHECK (committed_state_version > 0),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    created_at_utc REAL NOT NULL,
    completed_at_utc REAL,
    UNIQUE (request_id, input_id),
    UNIQUE (turn_id, request_id),
    FOREIGN KEY (request_id, input_id) REFERENCES core_inputs(request_id, input_id),
    CHECK (phase != 'committed' OR (
        committed_state_version IS NOT NULL AND result_json IS NOT NULL
        AND completed_at_utc IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS core_turns_recovery
    ON core_turns(phase, executor_lease_expires_at_utc, expires_at_utc);

CREATE TABLE IF NOT EXISTS core_domain_events (
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    event_id TEXT NOT NULL UNIQUE,
    turn_id TEXT,
    state_version INTEGER NOT NULL CHECK (state_version > 0),
    event_kind TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at_utc REAL NOT NULL,
    PRIMARY KEY (request_id, event_sequence),
    FOREIGN KEY (turn_id, request_id) REFERENCES core_turns(turn_id, request_id)
);

CREATE TABLE IF NOT EXISTS core_operations (
    operation_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    draft_id TEXT NOT NULL,
    booking_revision INTEGER NOT NULL CHECK (booking_revision >= 0),
    operation_kind TEXT NOT NULL CHECK (operation_kind IN (
        'local_intake', 'external_submit', 'external_cancel', 'external_modify', 'handoff')),
    action_intent_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
    protected_payload_json TEXT NOT NULL CHECK (json_valid(protected_payload_json)),
    phase TEXT NOT NULL CHECK (phase IN (
        'prepared', 'sending', 'succeeded', 'failed', 'unknown', 'cancelled')),
    provider_ref TEXT,
    external_reference TEXT,
    outcome_json TEXT CHECK (outcome_json IS NULL OR json_valid(outcome_json)),
    unknown_reason_code TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    claim_token TEXT,
    claim_expires_at_utc REAL,
    next_reconcile_at_utc REAL,
    created_at_utc REAL NOT NULL,
    updated_at_utc REAL NOT NULL,
    CHECK (operation_kind != 'handoff' OR action_intent_id IS NOT NULL),
    UNIQUE (operation_id, request_id),
    FOREIGN KEY (draft_id, request_id) REFERENCES core_drafts(draft_id, request_id),
    CHECK (phase != 'unknown' OR unknown_reason_code IS NOT NULL),
    CHECK (phase NOT IN ('succeeded', 'failed') OR outcome_json IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS core_operations_reconcile
    ON core_operations(phase, next_reconcile_at_utc, claim_expires_at_utc);
CREATE UNIQUE INDEX IF NOT EXISTS core_trip_operation_identity
    ON core_operations(request_id, draft_id, booking_revision, operation_kind)
    WHERE operation_kind != 'handoff';
CREATE UNIQUE INDEX IF NOT EXISTS core_handoff_intent_identity
    ON core_operations(request_id, action_intent_id)
    WHERE operation_kind = 'handoff';

CREATE TABLE IF NOT EXISTS sample_support_requests (
    support_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    operation_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('open', 'assigned', 'resolved', 'cancelled')),
    reason_code TEXT NOT NULL,
    protected_detail_json TEXT NOT NULL CHECK (json_valid(protected_detail_json)),
    created_at_utc REAL NOT NULL,
    updated_at_utc REAL NOT NULL,
    FOREIGN KEY (operation_id, request_id) REFERENCES core_operations(operation_id, request_id)
);

CREATE TABLE IF NOT EXISTS sample_bookings (
    booking_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    draft_id TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL UNIQUE REFERENCES core_sessions(session_id),
    booking_revision INTEGER NOT NULL CHECK (booking_revision >= 0),
    status TEXT NOT NULL CHECK (status IN ('confirmed', 'canceled')),
    dispatch_status TEXT NOT NULL CHECK (dispatch_status IN (
        'not_integrated', 'pending', 'accepted', 'failed')),
    protected_booking_json TEXT NOT NULL CHECK (json_valid(protected_booking_json)),
    created_at_utc REAL NOT NULL,
    UNIQUE (request_id, draft_id),
    UNIQUE (booking_id, request_id),
    FOREIGN KEY (draft_id, request_id) REFERENCES core_drafts(draft_id, request_id),
    FOREIGN KEY (operation_id, request_id) REFERENCES core_operations(operation_id, request_id)
);

CREATE TABLE IF NOT EXISTS sample_operator_tasks (
    task_id TEXT PRIMARY KEY,
    booking_id TEXT NOT NULL REFERENCES sample_bookings(booking_id),
    kind TEXT NOT NULL CHECK (kind IN ('new_booking', 'follow_up')),
    request_kind TEXT CHECK (request_kind IN ('change', 'cancel', 'human')),
    status TEXT NOT NULL CHECK (status IN ('open', 'assigned', 'in_progress', 'resolved')),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    protected_detail_json TEXT NOT NULL CHECK (json_valid(protected_detail_json)),
    created_at_utc REAL NOT NULL,
    updated_at_utc REAL NOT NULL,
    CHECK ((kind = 'new_booking' AND request_kind IS NULL)
        OR (kind = 'follow_up' AND request_kind IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS sample_one_booking_task
    ON sample_operator_tasks(booking_id) WHERE kind = 'new_booking';
CREATE UNIQUE INDEX IF NOT EXISTS sample_one_open_follow_up
    ON sample_operator_tasks(booking_id, request_kind)
    WHERE kind = 'follow_up' AND status != 'resolved';

CREATE TABLE IF NOT EXISTS core_responses (
    response_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL,
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    state_version INTEGER NOT NULL CHECK (state_version > 0),
    booking_revision INTEGER NOT NULL CHECK (booking_revision >= 0),
    segments_json TEXT NOT NULL CHECK (json_valid(segments_json)),
    facts_json TEXT NOT NULL CHECK (json_valid(facts_json)),
    created_at_utc REAL NOT NULL,
    UNIQUE (turn_id),
    UNIQUE (response_id, request_id),
    FOREIGN KEY (turn_id, request_id) REFERENCES core_turns(turn_id, request_id)
);

CREATE TABLE IF NOT EXISTS core_questions (
    question_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    decision_kind TEXT NOT NULL CHECK (decision_kind IN (
        'clarify_slot', 'confirm_location', 'confirm_trip', 'confirm_cancel',
        'resume_request', 'choose_candidate', 'choose_handoff')),
    target_ref TEXT NOT NULL,
    booking_revision INTEGER,
    location_version INTEGER,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'suspended', 'answered', 'invalidated', 'expired')),
    binding_json TEXT NOT NULL CHECK (json_valid(binding_json)),
    expires_at_utc REAL,
    created_at_utc REAL NOT NULL,
    UNIQUE (question_id, request_id),
    CHECK (decision_kind != 'confirm_trip' OR booking_revision IS NOT NULL),
    CHECK (decision_kind != 'confirm_location' OR location_version IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS core_one_offered_decision
    ON core_questions(request_id) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS core_question_offers (
    response_id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    owner_generation INTEGER NOT NULL CHECK (owner_generation > 0),
    offered_at_utc REAL NOT NULL,
    FOREIGN KEY (response_id, request_id) REFERENCES core_responses(response_id, request_id),
    FOREIGN KEY (question_id, request_id) REFERENCES core_questions(question_id, request_id)
);

CREATE TABLE IF NOT EXISTS core_presentations (
    playback_id TEXT PRIMARY KEY,
    response_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES core_sessions(session_id),
    owner_generation INTEGER NOT NULL CHECK (owner_generation > 0),
    transport TEXT NOT NULL CHECK (transport IN ('voice', 'text')),
    phase TEXT NOT NULL CHECK (phase IN (
        'prepared', 'sent', 'completed', 'interrupted', 'failed')),
    required_segment_ids_json TEXT NOT NULL CHECK (json_valid(required_segment_ids_json)),
    server_completed_at_utc REAL,
    client_output_available_ack_at_utc REAL,
    text_presented_at_utc REAL,
    created_at_utc REAL NOT NULL,
    FOREIGN KEY (response_id, request_id) REFERENCES core_responses(response_id, request_id),
    CHECK (transport != 'voice' OR text_presented_at_utc IS NULL),
    CHECK (transport != 'text' OR client_output_available_ack_at_utc IS NULL)
);

CREATE INDEX IF NOT EXISTS core_presentations_response ON core_presentations(response_id, created_at_utc);

CREATE TABLE IF NOT EXISTS sample_dashboard_outbox (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL REFERENCES core_requests(request_id),
    topic TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    phase TEXT NOT NULL CHECK (phase IN ('pending', 'leased', 'published', 'dead')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    claim_token TEXT,
    claim_expires_at_utc REAL,
    next_attempt_at_utc REAL,
    created_at_utc REAL NOT NULL,
    published_at_utc REAL,
    CHECK (phase != 'published' OR published_at_utc IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS sample_outbox_pending ON sample_dashboard_outbox(phase, next_attempt_at_utc, sequence);
