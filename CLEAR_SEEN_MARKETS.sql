-- Clear seen_markets to force re-alerting on recent markets
-- Run this in Supabase SQL Editor to test the new spam-free alerts

-- Option 1: Clear ALL seen markets (will re-alert on all recent markets)
TRUNCATE TABLE seen_markets;

-- Option 2: Clear only AI-related markets (more targeted)
-- DELETE FROM seen_markets 
-- WHERE event_slug LIKE '%ai%' 
--    OR event_slug LIKE '%model%'
--    OR event_slug LIKE '%best%';

-- Verify it's empty
SELECT COUNT(*) as total_seen_markets FROM seen_markets;

