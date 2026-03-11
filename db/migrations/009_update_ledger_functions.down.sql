-- Restore original ledger functions (no advisory lock, no pagination)

CREATE OR REPLACE FUNCTION append_to_ledger(
    p_entry_type VARCHAR,
    p_payload JSONB,
    p_actor VARCHAR DEFAULT 'system',
    p_related_id UUID DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_prev_hash VARCHAR;
    v_entry_hash VARCHAR;
    v_entry_id UUID;
BEGIN
    SELECT entry_hash INTO v_prev_hash FROM immutable_ledger ORDER BY sequence_id DESC LIMIT 1;
    v_entry_hash := compute_ledger_hash(p_entry_type, p_payload, v_prev_hash);
    v_entry_id := gen_random_uuid();
    INSERT INTO immutable_ledger (entry_id, entry_type, payload, actor, related_id, prev_hash, entry_hash)
    VALUES (v_entry_id, p_entry_type, p_payload, p_actor, p_related_id, v_prev_hash, v_entry_hash);
    RETURN v_entry_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION verify_ledger_integrity()
RETURNS TABLE(is_valid BOOLEAN, broken_at BIGINT, total_entries BIGINT) AS $$
DECLARE
    r RECORD;
    expected_hash VARCHAR;
    prev_hash VARCHAR;
    entry_count BIGINT := 0;
BEGIN
    FOR r IN SELECT * FROM immutable_ledger ORDER BY sequence_id ASC LOOP
        entry_count := entry_count + 1;
        expected_hash := compute_ledger_hash(r.entry_type, r.payload, prev_hash);
        IF r.entry_hash != expected_hash THEN
            RETURN QUERY SELECT FALSE, r.sequence_id, entry_count;
            RETURN;
        END IF;
        prev_hash := r.entry_hash;
    END LOOP;
    RETURN QUERY SELECT TRUE, 0::BIGINT, entry_count;
END;
$$ LANGUAGE plpgsql;
