-- ============================================================
-- DATABASE MIGRATION: Genesis Scanner Persistence V2
-- ============================================================
-- Run this in Supabase SQL Editor to add persistence for Genesis Scanner
-- This prevents re-alerting on old markets after bot restart
-- ============================================================

-- 1. Create seen_markets table (prevents restart spam)
CREATE TABLE IF NOT EXISTS seen_markets (
    market_id TEXT PRIMARY KEY,
    event_slug TEXT,
    seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Create index for cleanup queries
CREATE INDEX IF NOT EXISTS idx_seen_markets_seen_at 
ON seen_markets(seen_at);

-- 3. Create index for event deduplication lookups
CREATE INDEX IF NOT EXISTS idx_seen_markets_event_slug 
ON seen_markets(event_slug);

-- 4. Add lag_hunter_filters column if not exists (for /filter command)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'servers' AND column_name = 'lag_hunter_filters'
    ) THEN
        ALTER TABLE servers ADD COLUMN lag_hunter_filters TEXT;
        RAISE NOTICE 'Added lag_hunter_filters column to servers table';
    ELSE
        RAISE NOTICE 'lag_hunter_filters column already exists';
    END IF;
END $$;

-- 5. Create scheduled cleanup (optional - run manually or via cron)
-- This deletes seen_markets older than 7 days to prevent table bloat
-- DELETE FROM seen_markets WHERE seen_at < NOW() - INTERVAL '7 days';

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

-- Check table created:
-- SELECT * FROM seen_markets LIMIT 10;

-- Check columns exist:
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'servers' 
-- ORDER BY ordinal_position;

-- ============================================================
-- NOTES
-- ============================================================
-- 
-- seen_markets table:
--   - market_id: Unique Polymarket market ID
--   - event_slug: Event slug for variant deduplication
--   - seen_at: Timestamp when first seen (for cleanup)
--
-- On bot startup, Genesis Scanner loads markets seen in last 7 days.
-- This prevents re-alerting after bot restart or Railway redeploy.
--
-- Table auto-cleans records older than 7 days via periodic cleanup.
-- ============================================================

