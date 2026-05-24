-- ============================================
-- GENESIS SCANNER DIAGNOSTIC QUERIES
-- Run these in Supabase SQL Editor to debug
-- ============================================

-- 1. CHECK SERVER CONFIGURATION
-- Verify that new_markets_channel_id is set
SELECT 
    guild_id,
    guild_name,
    new_markets_channel_id,
    curated_channel_id,
    market_filters,
    enabled,
    is_banned
FROM servers
WHERE enabled = true AND is_banned = false;

-- Expected: At least 1 row with new_markets_channel_id populated
-- If NULL: Run /setup in Discord to configure the channel

-- ============================================

-- 2. CHECK SEEN MARKETS
-- See how many markets are marked as seen
SELECT 
    COUNT(*) as total_seen_markets,
    COUNT(DISTINCT event_slug) as unique_events,
    MAX(seen_at) as last_market_seen,
    MIN(seen_at) as oldest_market_seen
FROM seen_markets;

-- Expected: Shows how many markets the bot has already seen

-- ============================================

-- 3. RECENT SEEN MARKETS
-- View the 20 most recent markets seen by the bot
SELECT 
    market_id,
    event_slug,
    seen_at,
    EXTRACT(EPOCH FROM (NOW() - seen_at))/3600 as hours_ago
FROM seen_markets
ORDER BY seen_at DESC
LIMIT 20;

-- Expected: Shows when markets were last seen

-- ============================================

-- 4. CLEAR SEEN MARKETS (TESTING ONLY!)
-- ⚠️ WARNING: This will cause the bot to re-alert on ALL markets
-- Only run this if you want to test the alert system
-- TRUNCATE TABLE seen_markets;

-- ============================================

-- 5. CHECK FILTERS
-- See what category filters are configured per server
SELECT 
    guild_id,
    guild_name,
    market_filters as genesis_filters,
    lag_hunter_filters
FROM servers
WHERE enabled = true 
  AND (market_filters IS NOT NULL OR lag_hunter_filters IS NOT NULL);

-- Expected: Shows any category filters that might be blocking markets

-- ============================================

-- 6. MARKETS SEEN IN LAST HOUR
-- Check if the bot is actively discovering markets
SELECT 
    COUNT(*) as markets_last_hour
FROM seen_markets
WHERE seen_at > NOW() - INTERVAL '1 hour';

-- Expected: If > 0, the bot is actively scanning
-- If 0, either no new markets on Polymarket or bot is not running

-- ============================================

-- 7. CLEANUP OLD SEEN MARKETS (OPTIONAL)
-- Only keep markets seen in last 7 days (prevents table bloat)
-- DELETE FROM seen_markets
-- WHERE seen_at < NOW() - INTERVAL '7 days';

