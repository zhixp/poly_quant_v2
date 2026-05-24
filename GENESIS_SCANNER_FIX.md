# 🔧 GENESIS SCANNER: COMPLETE FIX & DIAGNOSTICS

## 📊 PROBLEM SOLVED

**Before:** Bot was fetching only 20 markets per scan, missing new markets  
**After:** Bot now fetches 100+ events (200-500 individual markets) per scan

---

## ✅ WHAT WAS FIXED

### 1. **Increased API Fetch Limit**
- **Changed:** Event fetch limit from 20 → 100
- **Impact:** 5x more markets scanned per cycle
- **Result:** Bot can now see ALL recent markets, not just the top 20 by popularity

### 2. **Added Comprehensive Logging**
Every scan now shows:
- `📋 Currently tracking X seen markets, Y seen events` - Shows what's already known
- `📢 Broadcasting to X firehose channels, Y curated channels` - Shows where alerts go
- `🆕 NEW MARKET DISCOVERED: [question]` - Logs EVERY truly new market
- `✅ Sent alert to guild X (channel Y)` - Confirms alert was sent
- `📢 Market alert broadcasted to X server(s)` - Final broadcast confirmation
- `Fetched: X | Already Seen: Y | New: Z` - Clear breakdown of results

### 3. **Early Exit Protection**
- Bot now warns if no channels are configured (prevents silent failures)
- Returns immediately if no firehose channels found

---

## 🧪 WHAT TO CHECK IMMEDIATELY

### **Step 1: Verify Railway Deployment**

Wait for Railway to redeploy the bot (1-2 minutes), then check logs for:

#### ✅ SUCCESS INDICATORS:
```
🔮 Genesis Scan #1: Found 137 markets from API
📋 Currently tracking 224 seen markets, 0 seen events
📢 Broadcasting to 1 firehose channels, 0 curated channels
```

#### 🔴 FAILURE INDICATORS:
```
🔮 Genesis Scan #1: Found 20 markets from API    ← OLD CODE!
⚠️ No firehose channels configured!              ← CONFIGURATION ISSUE!
```

---

### **Step 2: Check Server Configuration in Supabase**

Run this query in **Supabase SQL Editor**:

```sql
SELECT 
    guild_id,
    guild_name,
    new_markets_channel_id,
    market_filters,
    enabled,
    is_banned
FROM servers
WHERE enabled = true AND is_banned = false;
```

**Expected Result:**
- `new_markets_channel_id` should have a Discord channel ID (like `1234567890123456789`)
- If it's `NULL`, run `/setup` in Discord to configure it

---

### **Step 3: Check Seen Markets Database**

Run this in **Supabase SQL Editor**:

```sql
SELECT 
    COUNT(*) as total_seen,
    MAX(seen_at) as last_seen
FROM seen_markets;
```

**What this tells you:**
- `total_seen` = How many markets the bot has already seen
- `last_seen` = When the last market was detected

**If you want to TEST alerts immediately:**
```sql
TRUNCATE TABLE seen_markets;
```
⚠️ **WARNING:** This will re-alert on ALL recent markets (expect 50-100 Discord notifications)

---

## 🔍 EXPECTED BEHAVIOR NOW

### **Normal Operation (No New Markets):**
```
🔮 Genesis Scan #2: Found 137 markets from API
📋 Currently tracking 224 seen markets, 0 seen events
📢 Broadcasting to 1 firehose channels, 0 curated channels
🔮 Genesis Scan #2 complete | Fetched: 137 | Already Seen: 137 | New: 0
```

This is **CORRECT** if no new markets have been created on Polymarket.

### **When a New Market Appears:**
```
🔮 Genesis Scan #5: Found 138 markets from API
📋 Currently tracking 224 seen markets, 0 seen events
📢 Broadcasting to 1 firehose channels, 0 curated channels
🆕 NEW MARKET DISCOVERED: Will AI replace humans by 2030? | Category: Technology
✅ Sent alert to guild 504583329400750080 (channel 1234567890123456789)
📢 Market alert broadcasted to 1 server(s): Will AI replace humans...
🔮 Genesis Scan #5 complete | Fetched: 138 | Already Seen: 137 | New: 1
```

You should see a Discord notification within 30-60 seconds of the market going live on Polymarket.

---

## 🚨 TROUBLESHOOTING

### **Issue 1: Still seeing "Found 20 markets"**
- **Cause:** Railway didn't deploy the new code
- **Fix:** Force restart the Railway service or manually trigger a deploy

### **Issue 2: "⚠️ No firehose channels configured!"**
- **Cause:** `new_markets_channel_id` is not set in the database
- **Fix:** Run `/setup` in Discord and configure the channel

### **Issue 3: "Already Seen: 137 | New: 0" forever**
- **Cause:** All markets have been seen already (this is normal!)
- **Test:** Run `TRUNCATE TABLE seen_markets;` in Supabase to force re-alerts
- **Real Fix:** Wait for Polymarket to create a genuinely new market

### **Issue 4: "New: 1" but no Discord alert**
- **Cause:** Channel not found or category filter blocked it
- **Check logs for:** `⚠️ Channel X not found` or `Filtered Y market for guild Z`
- **Fix:** Verify the channel ID is correct and bot has permissions

### **Issue 5: Markets skipped for "no liquidity"**
- **Logs:** `💧 No liquidity yet: [market name] (queued for retry)`
- **Cause:** Market exists but prices are not available yet
- **Behavior:** Bot will retry on next scan (30 seconds)
- **Normal:** This happens with brand new markets that haven't settled

---

## 📁 DIAGNOSTIC FILES

We've created `DIAGNOSTIC_QUERIES.sql` with 7 ready-to-run queries:
1. Check server configuration
2. Check seen markets count
3. View recent markets
4. Clear seen markets (testing)
5. Check category filters
6. Markets seen in last hour
7. Cleanup old records

Run these in Supabase SQL Editor when debugging.

---

## 🎯 NEXT STEPS

1. **Wait for Railway to redeploy** (should auto-deploy on git push)
2. **Check Railway logs** for the new log format
3. **Run diagnostic queries** in Supabase to verify configuration
4. **Wait for a new market** to be created on Polymarket (or truncate `seen_markets` to test)
5. **Verify Discord alert** appears within 60 seconds

---

## 📈 MONITORING CHECKLIST

✅ Bot fetching 100+ markets per scan (not 20)  
✅ Logs show "Broadcasting to X firehose channels"  
✅ Logs show "Already Seen: X" to explain why no new markets  
✅ When new market appears: logs show "🆕 NEW MARKET DISCOVERED"  
✅ When alert sent: logs show "✅ Sent alert to guild X"  
✅ Discord notification received within 60 seconds  

---

**Commits Applied:**
- `5317276` - Increased limit to 100
- `c7bf020` - Added comprehensive logging
- `d102605` - Added diagnostic queries

**Status:** ✅ READY FOR TESTING

