-- Database Migration: Add Market Filters Column
-- Run this in Supabase SQL Editor to add per-server market filtering

-- Add market_filters column to servers table
ALTER TABLE servers 
ADD COLUMN IF NOT EXISTS market_filters TEXT;

-- Verify column was added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name = 'servers' 
AND column_name = 'market_filters';

-- Expected output: 
-- market_filters | text | YES

-- Sample usage:
-- UPDATE servers SET market_filters = 'Politics,Crypto,Sports' WHERE guild_id = 123456789;
-- UPDATE servers SET market_filters = NULL WHERE guild_id = 987654321;  -- Show all

