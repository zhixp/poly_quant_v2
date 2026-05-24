-- PolyQuant Multi-Tenant SaaS Database Schema
-- Execute this in your Supabase SQL Editor

-- 1. Servers Table (Multi-Tenant Configuration)
CREATE TABLE IF NOT EXISTS servers (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT UNIQUE NOT NULL,
    guild_name TEXT NOT NULL,
    
    -- Channels
    alert_channel_id BIGINT,              -- Legacy: do not use for new alert routing
    query_channel_id BIGINT,              -- Legacy: replaced by ask_channel_id
    ask_channel_id BIGINT,                -- /ask analysis responses
    lag_hunter_channel_id BIGINT,         -- Lag Hunter alerts only
    new_markets_channel_id BIGINT,        -- Genesis Scanner: ALL new markets (firehose)
    curated_channel_id BIGINT,            -- Legacy: replaced by curated_markets_channel_id
    curated_markets_channel_id BIGINT,    -- Genesis Scanner: High-confidence picks only
    arb_channel_id BIGINT,                -- Arbitrage alerts only
    geo_channel_id BIGINT,                -- Geo Sniper: geopolitical mispricing alerts only
    copy_tracker_channel_id BIGINT,       -- Wallet/copy-trade tracker alerts
    
    -- Market Filters (Genesis Scanner)
    market_filters TEXT,                  -- Comma-separated categories (e.g., 'Politics,Crypto,Sports') or NULL for all
    
    -- Subscription
    tier TEXT DEFAULT 'free' CHECK (tier IN ('free', 'pro', 'enterprise')),
    enabled BOOLEAN DEFAULT TRUE,
    is_banned BOOLEAN DEFAULT FALSE,
    ban_reason TEXT,
    banned_at TIMESTAMP WITH TIME ZONE,
    
    -- Rate Limiting
    max_queries_per_day INTEGER DEFAULT 50,
    query_count_today INTEGER DEFAULT 0,
    last_reset TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Analysis Logs Table (Enhanced with Guild Tracking)
CREATE TABLE IF NOT EXISTS analysis_logs (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT REFERENCES servers(guild_id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_servers_guild_id ON servers(guild_id);
CREATE INDEX IF NOT EXISTS idx_servers_enabled ON servers(enabled) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_servers_banned ON servers(is_banned) WHERE is_banned = FALSE;
CREATE INDEX IF NOT EXISTS idx_analysis_logs_guild_id ON analysis_logs(guild_id);
CREATE INDEX IF NOT EXISTS idx_analysis_logs_created_at ON analysis_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_logs_query ON analysis_logs(query);

-- 4. PostgreSQL Function: Increment Query Count (Atomic)
CREATE OR REPLACE FUNCTION increment_query_count(g_id BIGINT)
RETURNS VOID AS $$
BEGIN
    UPDATE servers
    SET query_count_today = query_count_today + 1,
        updated_at = NOW()
    WHERE guild_id = g_id;
END;
$$ LANGUAGE plpgsql;

-- 5. PostgreSQL Function: Auto-Reset Daily Counters (Cron Job)
CREATE OR REPLACE FUNCTION reset_daily_counters()
RETURNS VOID AS $$
BEGIN
    UPDATE servers
    SET query_count_today = 0,
        last_reset = NOW()
    WHERE last_reset < NOW() - INTERVAL '1 day';
END;
$$ LANGUAGE plpgsql;

-- 6. Row-Level Security (Optional - for multi-tenant data isolation)
-- ALTER TABLE servers ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE analysis_logs ENABLE ROW LEVEL SECURITY;

-- Note: Configure Supabase Cron Extension to run reset_daily_counters() at midnight UTC:
-- SELECT cron.schedule('reset-query-counters', '0 0 * * *', 'SELECT reset_daily_counters()');

-- 7. Market Mappings Table (Cross-Venue Arbitrage Support)
-- Maps Polymarket events/markets to external bookmaker markets
CREATE TABLE IF NOT EXISTS market_mappings (
    id BIGSERIAL PRIMARY KEY,
    polymarket_event_slug TEXT NOT NULL,
    polymarket_market_slug TEXT,
    venue TEXT NOT NULL,              -- e.g. 'pinnacle', 'betfair', 'draftkings'
    venue_market_id TEXT NOT NULL,    -- bookmaker's internal market ID
    normalized_name TEXT NOT NULL,    -- canonical name for matching
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'expired')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Indexes for Market Mappings
CREATE INDEX IF NOT EXISTS idx_market_mappings_poly_event 
    ON market_mappings(polymarket_event_slug);
CREATE INDEX IF NOT EXISTS idx_market_mappings_poly_venue 
    ON market_mappings(polymarket_event_slug, venue);
CREATE INDEX IF NOT EXISTS idx_market_mappings_venue_id 
    ON market_mappings(venue, venue_market_id);
CREATE INDEX IF NOT EXISTS idx_market_mappings_status 
    ON market_mappings(status) WHERE status = 'active';

-- 9. Sample Data (Optional - for testing)
-- INSERT INTO servers (guild_id, guild_name, tier) VALUES
-- (123456789, 'Test Server', 'free'),
-- (987654321, 'Pro Server', 'pro');

-- Sample market mapping (Honduras election example):
-- INSERT INTO market_mappings (polymarket_event_slug, venue, venue_market_id, normalized_name) VALUES
-- ('honduras-presidential-election', 'pinnacle', 'pol-12345', 'Honduras Presidential Election 2025');

