# 🔮 Genesis Scanner: Multi-Tenant SaaS Guide

## Overview

The **Genesis Scanner** is now fully integrated with your multi-tenant SaaS architecture. Each server admin can configure their own Genesis channels independently.

---

## How It Works

### Multi-Tenant Broadcasting
Just like LagHunter, GenesisScanner broadcasts to **ALL servers** that have configured channels:

1. **Server A** sets up `#new-markets` → Gets firehose alerts
2. **Server B** sets up `#curated-picks` → Gets only high-confidence alerts  
3. **Server C** sets up both → Gets both types of alerts
4. **Server D** sets up nothing → Gets no alerts

**No global configuration needed!** Each server is independent.

---

## Database Schema Updates

Add these columns to your `servers` table:

```sql
-- Run this in Supabase SQL Editor:
ALTER TABLE servers ADD COLUMN IF NOT EXISTS new_markets_channel_id BIGINT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS curated_channel_id BIGINT;
```

**Or** drop and recreate using the updated `database_schema.sql` file.

---

## Server Admin Setup

### Using /setup Command

Admins configure Genesis Scanner for their server:

```
/setup action:Set New Markets Channel channel:#new-markets
→ Configures firehose feed (ALL new markets)

/setup action:Set Curated Channel channel:#curated-picks
→ Configures high-confidence picks only
```

### View Configuration

```
/setup action:View Current Settings
```

Shows all configured channels including Genesis Scanner channels.

---

## Channel Types

### 1. New Markets Channel (Firehose)

**What it posts:**
- Every new market from Polymarket
- Updates every 30 seconds as markets are created
- Simple embeds with basic info

**Who should use:**
- Traders who want to see everything
- Servers focused on early market discovery
- Research/analytics teams

**Volume:** High (potentially 10-50 posts per day)

---

### 2. Curated Channel (High-Confidence)

**What it posts:**
- Only markets with extreme Hydra confidence (>75% or <25%)
- Includes AI analysis rationale
- Tagged "🚨 POTENTIAL EASY WIN"

**Who should use:**
- Traders focused on quality over quantity
- Servers that want only the best opportunities
- Signal-focused communities

**Volume:** Low (1-5 posts per day, sometimes none)

---

## How Genesis Scanner Works

### The Pipeline

```
1. Poll Gamma API every 30 seconds
   ↓
2. Detect new markets (not in seen_market_ids)
   ↓
3. PHASE 1: Broadcast to ALL firehose channels
   ↓
4. PHASE 2: Filter for quality
   - Category: Politics, Crypto, Macro, Economics, Sports
   - Liquidity: > $0
   ↓
5. Run Hydra AI analysis (quick assessment)
   ↓
6. If confidence >75% or <25%:
   → Broadcast to ALL curated channels
```

### Quality Filters

Markets must pass these criteria for Hydra analysis:
- **Category:** Politics, Crypto, Macro, Economics, or Sports  
- **Liquidity:** > $0 (has real trading activity)

All other markets are skipped (saves Hydra API calls).

### Confidence Thresholds

Curated alerts only trigger for **extreme confidence**:
- **>75%:** High-confidence opportunity (strong YES/NO conviction)
- **<25%:** Contrarian opportunity (market mispriced, fade the crowd)

Normal confidence (25-75%) is filtered out (wait for better edges).

---

## Performance & Scaling

### Resources

**Per Scan (30s cycle):**
- Network: ~1KB (API call)
- CPU: Minimal (mostly async I/O)
- Hydra calls: 0-3 (only quality markets)

**Memory:** ~50KB per 1000 seen markets

### Multi-Tenant Load

The scanner broadcasts to **all configured servers in parallel**:
- 1 server = 1 Discord API call
- 100 servers = 100 Discord API calls (parallel, ~1s total)

No performance issues expected even at 1000+ servers.

### Supabase Queries

Only 2 queries per scan (cached by server_manager):
1. `get_all_new_markets_channels()` - Fetch firehose servers
2. `get_all_curated_channels()` - Fetch curated servers

Both cached with 5-min TTL → 12 DB queries/hour.

---

## Admin Commands

### Debug Configuration
```
/debug_config
```
Shows if Genesis channels are configured for this server.

### View Metrics
```
/metrics
```
Shows Genesis Scanner statistics:
- Total scans
- Markets discovered
- Markets analyzed
- Curated alerts sent

---

## Best Practices

### Channel Setup Recommendations

**Small Server (<100 members):**
- Just curated channel
- Low noise, high signal

**Medium Server (100-1000 members):**
- Both channels
- Different roles: Firehose for researchers, Curated for traders

**Large Server (1000+ members):**
- Both channels in separate categories
- Mute firehose by default, unmute curated

### Notification Settings

**Firehose Channel:**
- ✅ Create dedicated channel (#new-markets)
- ⚠️ Mute by default (high volume)
- 💡 Pin a message explaining it's a feed

**Curated Channel:**
- ✅ Enable notifications
- ✅ Pin to top of channel list
- 💡 Restrict to traders/premium roles

---

## Comparison to Global Config

### ❌ Old Approach (What I Initially Built)
```python
# .env file (WRONG - not multi-tenant!)
NEW_MARKETS_CHANNEL_ID=123456789
CURATED_CHANNEL_ID=987654321
```

**Problems:**
- Only works for ONE server
- Breaks multi-tenant SaaS
- Requires bot restart to change

### ✅ New Approach (Multi-Tenant SaaS)
```
Each server admin runs:
/setup action:Set New Markets Channel channel:#their-channel
```

**Benefits:**
- ✅ Works for unlimited servers
- ✅ Each server configures independently
- ✅ No bot restart needed
- ✅ Respects banned/disabled servers
- ✅ Matches your existing LagHunter architecture

---

## Database Migration

If you already have the old schema, add the new columns:

```sql
-- Add Genesis Scanner channels to existing servers table
ALTER TABLE servers 
ADD COLUMN IF NOT EXISTS new_markets_channel_id BIGINT,
ADD COLUMN IF NOT EXISTS curated_channel_id BIGINT;
```

No data migration needed - servers start with `NULL` (no channels configured).

---

## Troubleshooting

### No Alerts Appearing

**Check:**
1. Run `/debug_config` - Are channels configured?
2. Check bot permissions in channels (Send Messages, Embed Links)
3. Check logs for "No servers configured for new markets alerts"
4. Verify server is not disabled or banned

### Only Firehose Working

**Expected!** Curated alerts are rare (high bar).
- Check `/metrics` - How many markets analyzed?
- Curated requires Hydra confidence >75% or <25%
- Some days may have zero curated alerts (normal)

### Too Many Alerts

**For Firehose:** This is expected (it's a firehose!)
- Mute the channel
- Or disable with `/setup action:Set New Markets Channel` (leave empty)

**For Curated:** Should be rare - check logs for issues

---

## Integration with Existing Features

### Works With
- ✅ `/setup` command (extended with new options)
- ✅ `/debug_config` (shows Genesis config)
- ✅ `/metrics` (tracks Genesis stats)
- ✅ Multi-tenant server management
- ✅ Enabled/disabled/banned server filtering

### Independent From
- ✅ LagHunter (runs in parallel)
- ✅ `/ask` command (different purpose)
- ✅ Rate limiting (scanners don't count against query limits)

---

## Migration Checklist

- [ ] **Database:** Add columns to `servers` table
- [ ] **Bot:** Deploy updated code
- [ ] **Test:** Run `/setup status` in test server
- [ ] **Configure:** Set up Genesis channels in your servers
- [ ] **Monitor:** Check `/metrics` after 1 hour

---

## Example Workflow

### Server Admin Perspective

```
1. Join server
2. Invite PolyQuant bot
3. Run /setup status
   → See all configuration options
4. Decide which alerts they want:
   - Just LagHunter? Set alert_channel_id only
   - Want new markets? Set new_markets_channel_id
   - Want high-confidence only? Set curated_channel_id
   - Want everything? Set all channels
5. Channels start receiving alerts within 30 seconds
```

### Bot Owner Perspective

```
1. Deploy bot with Genesis Scanner
2. Bot automatically discovers new markets
3. Broadcasts to all configured servers
4. Monitor with /metrics
5. No manual configuration needed per server
```

---

## Revenue Implications

### Potential Premium Feature

Consider making Genesis Scanner a **Pro/Enterprise** feature:

```python
# In genesis_scanner.py, before broadcasting:
if config.tier == 'free':
    # Skip Genesis alerts for free tier
    continue
```

**Value Proposition:**
- Free tier: LagHunter + /ask command
- Pro tier: + Genesis Scanner (early market discovery)
- Enterprise: + Priority Hydra analysis

---

## Success Indicators

GenesisScanner is working correctly when:

1. ✅ `/metrics` shows `genesis.scans.total` incrementing
2. ✅ Servers with channels configured receive alerts
3. ✅ Firehose posts new markets as they appear
4. ✅ Curated posts are rare but high-quality
5. ✅ Logs show: "Genesis Scanner Active - Will broadcast to all configured servers"

---

## Support

For issues or questions:
1. Check `/debug_config` output
2. Review bot logs for errors
3. Verify database columns exist
4. Test with `/metrics` command

---

*Genesis Scanner: Multi-Tenant Market Discovery*  
*Broadcasts to Unlimited Servers*  
*Each Server Configures Independently*  
*No Global Configuration Required*

**Your SaaS architecture is preserved!** 🎯

