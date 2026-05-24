-- Database Migration: Add Genesis Scanner Columns
-- Run this in Supabase SQL Editor to add the missing columns

-- Add the two new columns to the servers table
ALTER TABLE servers 
ADD COLUMN IF NOT EXISTS new_markets_channel_id BIGINT,
ADD COLUMN IF NOT EXISTS curated_channel_id BIGINT;

-- Verify columns were added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'servers' 
AND column_name IN ('new_markets_channel_id', 'curated_channel_id');

-- Expected output: 
-- new_markets_channel_id | bigint
-- curated_channel_id     | bigint

