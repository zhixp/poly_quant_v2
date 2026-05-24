# 🚨 Fix Database Errors

## What's Wrong

Your bot is running but getting these errors:
```
ERROR | Database | Failed to fetch new markets channels: 
{'code': '42703', 'message': 'column servers.new_markets_channel_id does not exist'}
```

## Why

The database doesn't have the new columns for Genesis Scanner yet.

## Fix (2 Minutes)

### Step 1: Open Supabase SQL Editor

1. Go to https://supabase.com
2. Open your project
3. Click "SQL Editor" in the left sidebar

### Step 2: Run Migration

Copy and paste this into the SQL Editor:

```sql
ALTER TABLE servers 
ADD COLUMN IF NOT EXISTS new_markets_channel_id BIGINT,
ADD COLUMN IF NOT EXISTS curated_channel_id BIGINT;
```

Click "Run" button.

### Step 3: Verify

Run this to verify columns were added:

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'servers' 
AND column_name IN ('new_markets_channel_id', 'curated_channel_id');
```

You should see:
```
new_markets_channel_id | bigint
curated_channel_id     | bigint
```

### Step 4: Restart Bot

```bash
# Stop bot (Ctrl+C)
# Start bot
python main.py
```

## What You'll See After Fix

✅ **Before (Errors):**
```
ERROR | Database | Failed to fetch new markets channels
ERROR | Database | Failed to fetch new markets channels
(repeating every few seconds)
```

✅ **After (Fixed):**
```
INFO | GenesisScanner | 🔮 Genesis Scan #1 complete
INFO | GenesisScanner | New: 32 | Quality: 0 | Analyzed: 0
(no more database errors)
```

## Alternative: Full Schema Recreate

If you want to start fresh, run `database_schema.sql` instead (includes ALL columns).

---

**Status:** Bot will work without this migration, but Genesis Scanner won't post alerts until columns are added.

