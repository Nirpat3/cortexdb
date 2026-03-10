-- ============================================================
-- CortexDB Embedding Sync Triggers
-- Fires NOTIFY on INSERT/UPDATE/DELETE for synced tables.
-- The EmbeddingSyncPipeline listens on 'embedding_sync' channel
-- and re-embeds changed rows into Qdrant automatically.
--
-- Idempotent: safe to run on every startup.
-- ============================================================

-- Trigger function: sends table name, operation, row id, and tenant_id
-- as a JSON payload via pg_notify.
CREATE OR REPLACE FUNCTION notify_embedding_sync()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', OLD.id::text,
            'tenant_id', COALESCE(OLD.tenant_id::text, '')
        )::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', NEW.id::text,
            'tenant_id', COALESCE(NEW.tenant_id::text, '')
        )::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Trigger: agents
-- Primary key: agent_id (aliased as id in the notify payload)
-- ============================================================
CREATE OR REPLACE FUNCTION notify_embedding_sync_agents()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', OLD.agent_id::text,
            'tenant_id', ''
        )::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', NEW.agent_id::text,
            'tenant_id', ''
        )::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_embedding_sync_agents ON agents;
CREATE TRIGGER trg_embedding_sync_agents
    AFTER INSERT OR UPDATE OR DELETE ON agents
    FOR EACH ROW EXECUTE FUNCTION notify_embedding_sync_agents();

-- ============================================================
-- Trigger: blocks
-- Primary key: block_id
-- ============================================================
CREATE OR REPLACE FUNCTION notify_embedding_sync_blocks()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', OLD.block_id::text,
            'tenant_id', ''
        )::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', NEW.block_id::text,
            'tenant_id', ''
        )::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_embedding_sync_blocks ON blocks;
CREATE TRIGGER trg_embedding_sync_blocks
    AFTER INSERT OR UPDATE OR DELETE ON blocks
    FOR EACH ROW EXECUTE FUNCTION notify_embedding_sync_blocks();

-- ============================================================
-- Trigger: a2a_agent_cards
-- Primary key: agent_id, has tenant_id
-- ============================================================
CREATE OR REPLACE FUNCTION notify_embedding_sync_a2a_agent_cards()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', OLD.agent_id::text,
            'tenant_id', COALESCE(OLD.tenant_id::text, '')
        )::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', NEW.agent_id::text,
            'tenant_id', COALESCE(NEW.tenant_id::text, '')
        )::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_embedding_sync_a2a_agent_cards ON a2a_agent_cards;
CREATE TRIGGER trg_embedding_sync_a2a_agent_cards
    AFTER INSERT OR UPDATE OR DELETE ON a2a_agent_cards
    FOR EACH ROW EXECUTE FUNCTION notify_embedding_sync_a2a_agent_cards();

-- ============================================================
-- Trigger: experience_ledger
-- Primary key: experience_id
-- ============================================================
CREATE OR REPLACE FUNCTION notify_embedding_sync_experience_ledger()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', OLD.experience_id::text,
            'tenant_id', ''
        )::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('embedding_sync', json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', NEW.experience_id::text,
            'tenant_id', ''
        )::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_embedding_sync_experience_ledger ON experience_ledger;
CREATE TRIGGER trg_embedding_sync_experience_ledger
    AFTER INSERT OR UPDATE OR DELETE ON experience_ledger
    FOR EACH ROW EXECUTE FUNCTION notify_embedding_sync_experience_ledger();
