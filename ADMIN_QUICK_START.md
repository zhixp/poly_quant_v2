# Admin Quick Start Guide

## New Admin Commands

All commands require administrator permissions and show ephemeral responses (only visible to you).

---

## 1. Verify Server Configuration

```
/debug_config
```

**What it shows:**
- Server tier (free/pro/enterprise)
- Enabled/banned status
- Alert channel configuration
- Query channel configuration
- Rate limit status
- Whether LagHunter will broadcast to this server

**When to use:**
- After running `/setup`
- When LagHunter seems silent
- To verify multi-tenant configuration

**Example output:**
```
🔧 SERVER CONFIGURATION DEBUG

Guild: My Trading Server (123456789)
Tier: FREE
Enabled: ✅ Yes
Banned: ✅ No

Channels:
  Alert Channel: #lag-alerts
  Query Channel: ❌ Not Set

Rate Limits:
  Queries Today: 12/50
  Last Reset: 2025-12-02 00:00 UTC

Global Status:
  Total servers with alerts: 5

LagHunter Status:
  ✅ This server WILL receive lag alerts
```

---

## 2. Test LagHunter System

```
/test_lag_hunter force_alert:True
```

**What it does:**
- Runs one LagHunter scan in test mode
- Ignores seen_links cache
- Sends synthetic test alert to your alert channel
- Returns detailed metrics

**When to use:**
- After configuring alert channel
- When debugging why alerts aren't appearing
- To verify Discord broadcast path

**Example output:**
```
🧪 LAGHUNTER TEST RESULTS

Status: ✅ Success
Test Alert Sent: ✅ Yes

Last Scan Metrics:
  Scan ID: #42
  Feeds OK: 3/3
  Total Entries: 15
  Fresh Entries: 8
  Already Seen: 5
  Markets Fetched: 20
  Matches Found: 2
  Alerts Sent: 2

Interpretation:
  ✅ System operational
```

**Common issues:**

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Test Alert Sent: ❌ No | No alert channel configured | Run `/setup`, set alert channel |
| Feeds OK: 0/3 | Network/RSS issue | Check logs, verify RSS URLs |
| Markets Fetched: 0 | Polymarket API down | Check ClobClient connection |
| Matches Found: 0 | No keyword overlap | Normal - wait for relevant news |

---

## 3. Monitor LagHunter Performance

```
/lag_hunter_stats
```

**What it shows:**
- Total scans completed
- Zero-alert streak (how many scans with no alerts)
- Seen links cache size
- Last scan summary with per-feed details

**When to use:**
- To verify LagHunter is running
- To understand why alerts are rare
- To monitor system health

**Example output:**
```
📊 LAGHUNTER RUNTIME STATISTICS

Total Scans: 1,470
Zero-Alert Streak: 3 scans
Seen Links: 1,234 cached

Last Scan Summary:
  Scan ID: #1470
  Feeds: 3 OK, 0 failed
  Entries: 15 total, 8 fresh
  Markets: 20
  Matches: 1
  Alerts: 1

Per-Feed Details:
  CoinDesk: 5 entries, 3 fresh, 1 matches
  SEC Press: 5 entries, 2 fresh, 0 matches
  FiveThirtyEight: 5 entries, 3 fresh, 0 matches
```

---

## 4. View System-Wide Metrics

```
/metrics
```

**What it shows:**
- System uptime
- `/ask` command statistics (requests, cache hits, errors)
- LagHunter statistics (scans, matches, alerts)
- Market data fetch counts
- Rate limiting hits
- Derived metrics (cache hit rate, alert rate)

**When to use:**
- Production health monitoring
- Performance analysis
- Debugging issues

**Example output:**
```
📊 SYSTEM METRICS

Uptime: 24.5 hours

📞 /ask Command:
  Total Requests: 1,234
  Cache Hits: 456
  Cache Misses: 778
  JSON Parse Failures: 3
  Errors: 2

🔍 Lag Hunter:
  Total Scans: 1,470
  Total Matches: 42
  Total Alerts: 38
  Zero-Alert Streak: 0 scans
  Errors: 0

📊 Market Data:
  Polymarket Fetches: 1,234
  Vegas Odds Fetches: 42
  Errors: 1

⚡ Rate Limiting:
  Rate Limit Hits: 5

Cache Hit Rate: 37.0%
Lag Hunter Alert Rate: 2.6%
```

**What's good:**
- Cache hit rate >20% (saves LLM calls)
- Low error counts (<1% of requests)
- LagHunter alert rate 1-5% (not too noisy, not silent)
- Zero-alert streak <10 (system is finding matches)

**What's bad:**
- Cache hit rate <10% (queries too diverse)
- High error counts (>5%)
- Zero-alert streak >20 (system may be broken)
- JSON parse failures >5% (prompt issues)

---

## Common Workflows

### Initial Setup

1. **Configure server:**
   ```
   /setup
   ```
   Follow prompts to set alert and query channels.

2. **Verify configuration:**
   ```
   /debug_config
   ```
   Confirm alert_channel_id is set.

3. **Test system:**
   ```
   /test_lag_hunter force_alert:True
   ```
   Verify synthetic alert appears in alert channel.

4. **Monitor for real alerts:**
   Wait 5-10 minutes, then check:
   ```
   /lag_hunter_stats
   ```
   Should show scans incrementing.

### Debugging Silent LagHunter

1. **Check configuration:**
   ```
   /debug_config
   ```
   Ensure alert_channel_id is set.

2. **Run test:**
   ```
   /test_lag_hunter force_alert:True
   ```
   If test alert fails, check channel permissions.

3. **Check stats:**
   ```
   /lag_hunter_stats
   ```
   Look at:
   - Feeds OK (should be 3/3)
   - Fresh Entries (should be >0)
   - Matches Found (may be 0 if no relevant news)

4. **Check logs:**
   Look for:
   - `📡 LagHunter Scan #N complete` messages
   - `⚠️ LagHunter: N scans with zero alerts` warnings
   - Any error messages

### Monitoring Production Health

**Daily check:**
```
/metrics
```

**What to look for:**
- Uptime (should be stable)
- Error rates (should be <1%)
- Cache hit rate (should be >20%)
- LagHunter alert rate (should be 1-5%)

**Weekly check:**
```
/lag_hunter_stats
```

**What to look for:**
- Total scans should be ~10,080 per week (1 per minute)
- Zero-alert streak should reset regularly
- Seen links cache should grow but not explode

---

## Troubleshooting

### "No servers configured for lag alerts"

**Cause:** No servers have set alert_channel_id.

**Fix:**
1. Run `/setup` in at least one server
2. Set an alert channel when prompted
3. Verify with `/debug_config`

### "Channel not found for guild"

**Cause:** Alert channel was deleted or bot lost access.

**Fix:**
1. Run `/setup` again
2. Choose a new alert channel
3. Verify bot has "Send Messages" permission in that channel

### "Test alert sent but didn't appear"

**Cause:** Bot lacks permissions in alert channel.

**Fix:**
1. Check bot role has "Send Messages" and "Embed Links" permissions
2. Check channel-specific permission overrides
3. Try a different channel

### High JSON parse failures

**Cause:** Judge prompt changes broke JSON output.

**Fix:**
1. Check logs for example of failed JSON
2. Verify Judge prompt OUTPUT SCHEMA is valid
3. Test with `/ask` and inspect response

### Zero-alert streak >20

**Cause:** Either no relevant news or system broken.

**Fix:**
1. Run `/test_lag_hunter` to verify system works
2. Check RSS feeds are accessible
3. Check Polymarket API is responding
4. Review keyword matching logic (may be too strict)

---

## Best Practices

### Alert Channel Setup

✅ **Do:**
- Create dedicated channel (e.g., #lag-alerts)
- Limit to admins/traders only (reduce noise)
- Enable notifications for this channel
- Test with `/test_lag_hunter` after setup

❌ **Don't:**
- Use high-traffic general channel
- Mix with other bot alerts
- Disable notifications (defeats purpose)

### Monitoring Cadence

- **Real-time:** Watch alert channel for LagHunter pings
- **Daily:** Run `/metrics` to check system health
- **Weekly:** Run `/lag_hunter_stats` to verify scan counts
- **After changes:** Always run `/test_lag_hunter`

### Rate Limit Management

- **Free tier:** 50 queries/day
- **Pro tier:** 500 queries/day
- **Enterprise:** Unlimited

**If hitting limits:**
1. Check `/metrics` to see query volume
2. Consider upgrading tier
3. Use cache more (ask similar questions)
4. Limit number of users with access

---

## Advanced: Market Mappings

### Adding Cross-Venue Mappings

Market mappings enable Vegas odds comparison. To add a mapping:

1. **Find Polymarket event slug:**
   - URL: `https://polymarket.com/event/honduras-presidential-election`
   - Slug: `honduras-presidential-election`

2. **Get bookmaker market ID:**
   - From bookmaker API or web scraping
   - Example: Pinnacle market ID `pol-12345`

3. **Insert into database:**
   ```sql
   INSERT INTO market_mappings 
     (polymarket_event_slug, venue, venue_market_id, normalized_name) 
   VALUES 
     ('honduras-presidential-election', 'pinnacle', 'pol-12345', 'Honduras Presidential Election 2025');
   ```

4. **Verify:**
   - Run `/ask` with Polymarket URL
   - Should see Vegas odds in context
   - LagHunter alerts should show cross-venue odds

### Viewing Mappings

```sql
SELECT * FROM market_mappings WHERE status = 'active';
```

### Disabling Mappings

```sql
UPDATE market_mappings 
SET status = 'disabled' 
WHERE id = 123;
```

---

## Support

If you encounter issues:

1. Check logs for error messages
2. Run diagnostic commands (`/debug_config`, `/test_lag_hunter`)
3. Review metrics (`/metrics`, `/lag_hunter_stats`)
4. Check database for configuration issues
5. Verify bot permissions in Discord

For bugs or feature requests, refer to the main repository documentation.

