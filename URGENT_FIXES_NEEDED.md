# Urgent Fixes Needed

## Critical Issues Preventing `/ask` from Working

### 1. ❌ **API Keys Invalid** (HIGHEST PRIORITY)

**Problem:** All 3 Gemini API keys are failing:
- `403 Your API key was reported as leaked`
- `400 API Key not found. Please pass a valid API key`

**Fix:** You need to generate new Gemini API keys:

1. Go to https://makersuite.google.com/app/apikey
2. Generate 3 new API keys
3. Update your `.env` file:
   ```
   GEMINI_API_KEY_1=your_new_key_1
   GEMINI_API_KEY_2=your_new_key_2
   GEMINI_API_KEY_3=your_new_key_3
   ```
4. Restart the bot

**Why this happened:** Your keys were likely exposed in a public repository or logs.

---

### 2. ⚠️ **MarketMappingService Database Methods** (MEDIUM PRIORITY)

**Problem:** `'Database' object has no attribute 'fetch_all'`

**Temporary Fix:** I've added stub methods to `app/core/database.py` that return empty results. This prevents crashes but means:
- Vegas odds won't work yet
- Market mappings won't be fetched

**Proper Fix (when you have time):**

The MarketMappingService needs either:

**Option A: Use Supabase Table API (Recommended)**
```python
# In app/core/market_mapping.py, replace raw SQL with Supabase calls
async def get_mappings_for_polymarket(self, event_slug: str):
    if not db.client:
        return []
    
    response = db.client.table("market_mappings")\
        .select("*")\
        .eq("polymarket_event_slug", event_slug)\
        .eq("status", "active")\
        .execute()
    
    return [MarketMapping(**row) for row in response.data]
```

**Option B: Create RPC Functions in Supabase**
```sql
-- In Supabase SQL Editor
CREATE OR REPLACE FUNCTION get_market_mappings(p_event_slug TEXT)
RETURNS SETOF market_mappings AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM market_mappings
    WHERE polymarket_event_slug = p_event_slug
    AND status = 'active';
END;
$$ LANGUAGE plpgsql;
```

---

### 3. ⚠️ **Market Data Parse Error** (MEDIUM PRIORITY)

**Problem:** `could not convert string to float: '"'`

**Location:** `app/core/market_data.py` line ~189

**Likely Cause:** Polymarket API response format changed or contains unexpected data.

**Debug Steps:**
1. Add logging to see raw API response:
   ```python
   # In app/core/market_data.py, around line 115
   logger.debug(f"Raw Polymarket API response: {data}")
   ```

2. Check what `outcomePrices` looks like - it might be:
   - A string instead of a list
   - Contains quoted numbers like `'"0.57"'` instead of `'0.57'`

**Quick Fix:**
```python
# In _format_multi_market_data, around line 188
outcome_prices = market.get('outcomePrices', ['0.50', '0.50'])
if isinstance(outcome_prices, str):
    # Handle string format
    outcome_prices = outcome_prices.strip('"').split(',')

yes_price = float(str(outcome_prices[1]).strip('"')) if len(outcome_prices) > 1 else 0.5
```

---

### 4. ⚠️ **Database Cache Query Syntax** (LOW PRIORITY)

**Problem:** `invalid input syntax for type timestamp with time zone: "now() - interval '6 hours'"`

**Fix:** Replace in `app/core/database.py` line 31:
```python
# OLD (broken):
.gte("created_at", "now() - interval '6 hours'")

# NEW (working):
from datetime import datetime, timedelta
cutoff = (datetime.now() - timedelta(hours=6)).isoformat()
.gte("created_at", cutoff)
```

---

## Quick Test After Fixes

1. **Fix API keys** (most important)
2. Restart bot: `python main.py`
3. Test: `/ask https://polymarket.com/event/maduro-out-in-2025`
4. Check logs for:
   - ✅ No "API Key not found" errors
   - ✅ "War Room: Deploying 4 Specialist Agents"
   - ✅ "War Room: Judge is Deliberating"
   - ✅ Response appears in Discord

---

## Workaround: Disable Vegas Odds Temporarily

If you want `/ask` to work immediately without fixing everything:

**In `app/cogs/query.py`, comment out Vegas odds:**
```python
# 2.5 Fetch Vegas/Bookmaker Odds (Cross-venue arbitrage data)
# vegas_data = await self._fetch_vegas_odds(safe_question, market_data)
vegas_data = None  # Temporarily disabled
```

This will let the bot work without the MarketMappingService.

---

## Priority Order

1. **Fix API keys** ← Do this first, nothing works without it
2. **Test `/ask` with Vegas disabled** ← Verify basic functionality
3. **Fix Market Data parser** ← So Polymarket prices show up
4. **Fix database cache query** ← Improves performance
5. **Implement MarketMappingService properly** ← For Vegas odds feature

---

## Current Status

✅ **Working:**
- LagHunter (scanning RSS feeds every 60s)
- Server configuration
- Admin commands (`/debug_config`, `/test_lag_hunter`, etc.)
- Database logging

❌ **Broken:**
- `/ask` command (API keys invalid)
- Polymarket price fetching (parse error)
- Vegas odds integration (database methods missing)
- Cache lookups (SQL syntax error)

---

## Need Help?

Check logs for specific errors:
```
2025-12-02 12:39:17,801 | ERROR | AgentCouncil | ⏱️ Agent Council Timeout!
```

This means the 4 specialist agents couldn't complete within 30 seconds because all API keys failed.

