-- Add dedicated Discord channel for wallet/copy-tracker alerts
-- Run this in Supabase SQL Editor before using /setup copytracker.

ALTER TABLE servers
ADD COLUMN IF NOT EXISTS copy_tracker_channel_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_servers_copy_tracker_channel
    ON servers(copy_tracker_channel_id)
    WHERE copy_tracker_channel_id IS NOT NULL;
