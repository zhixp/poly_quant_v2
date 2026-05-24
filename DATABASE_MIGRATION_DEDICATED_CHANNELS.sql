-- Dedicated channel routing migration.
-- Existing legacy columns are intentionally retained for compatibility.

ALTER TABLE servers
ADD COLUMN IF NOT EXISTS ask_channel_id BIGINT,
ADD COLUMN IF NOT EXISTS lag_hunter_channel_id BIGINT,
ADD COLUMN IF NOT EXISTS curated_markets_channel_id BIGINT,
ADD COLUMN IF NOT EXISTS arb_channel_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_servers_ask_channel
    ON servers(ask_channel_id)
    WHERE ask_channel_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_servers_lag_hunter_channel
    ON servers(lag_hunter_channel_id)
    WHERE lag_hunter_channel_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_servers_curated_markets_channel
    ON servers(curated_markets_channel_id)
    WHERE curated_markets_channel_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_servers_arb_channel
    ON servers(arb_channel_id)
    WHERE arb_channel_id IS NOT NULL;
