-- Add dedicated Geo Sniper channel to keep geopolitical mispricing alerts out of generic channels.
-- Run in Supabase SQL Editor.

ALTER TABLE servers
ADD COLUMN IF NOT EXISTS geo_channel_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_servers_geo_channel
    ON servers(geo_channel_id)
    WHERE geo_channel_id IS NOT NULL;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'servers'
  AND column_name = 'geo_channel_id';
