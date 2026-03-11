-- Down migration: drop embedding sync triggers and functions

DROP TRIGGER IF EXISTS trg_embedding_sync_experience_ledger ON experience_ledger;
DROP FUNCTION IF EXISTS notify_embedding_sync_experience_ledger();

DROP TRIGGER IF EXISTS trg_embedding_sync_a2a_agent_cards ON a2a_agent_cards;
DROP FUNCTION IF EXISTS notify_embedding_sync_a2a_agent_cards();

DROP TRIGGER IF EXISTS trg_embedding_sync_blocks ON blocks;
DROP FUNCTION IF EXISTS notify_embedding_sync_blocks();

DROP TRIGGER IF EXISTS trg_embedding_sync_agents ON agents;
DROP FUNCTION IF EXISTS notify_embedding_sync_agents();

DROP FUNCTION IF EXISTS notify_embedding_sync();
