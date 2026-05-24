# 🚀 PolyQuant: Single-Tenant → Multi-Tenant SaaS Migration

## 📋 Overview

Your PolyQuant bot has been transformed from a **personal single-tenant bot** into a **production-ready multi-tenant SaaS platform**. Multiple Discord servers can now use the bot simultaneously with:

- ✅ **Per-server configuration** (alert channels, query channels)
- ✅ **Tiered subscriptions** (Free, Pro, Enterprise)
- ✅ **Rate limiting** (prevent abuse)
- ✅ **Admin controls** (ban/unban, upgrade servers)
- ✅ **Smart caching** (5-minute cache to avoid DB hammering)
- ✅ **Broadcast lag alerts** to all configured servers

---

## 🏗️ Architecture Changes

### **Before (Single-Tenant)**
```
One Bot → One Server → Hardcoded Channel
```

### **After (Multi-Tenant SaaS)**
```
One Bot → Many Servers → Dynamic Channel Configuration
          ↓
    Server Manager (Cache Layer)
          ↓
    Supabase Database (Multi-Tenant Data)
```

---

## 📦 New Files Created

| File | Purpose |
|------|---------|
| `app/core/server_manager.py` | Multi-tenant config manager with caching |
| `app/cogs/setup.py` | User-facing `/setup` slash commands |
| `app/cogs/admin.py` | Owner-only `/admin` commands |
| `database_schema.sql` | Supabase SQL schema |
| `SAAS_MIGRATION_GUIDE.md` | This file |

---

## 🗄️ Database Setup

### **Step 1: Run SQL Schema in Supabase**

1. Go to your Supabase dashboard
2. Navigate to **SQL Editor**
3. Copy and paste the entire contents of `database_schema.sql`
4. Click **Run**

This creates:
- `servers` table (guild configurations)
- `analysis_logs` table (with guild tracking)
- Indexes for performance
- PostgreSQL functions for atomic operations

### **Step 2: Enable Daily Reset (Optional)**

To automatically reset query counters at midnight UTC:

```sql
-- Enable pg_cron extension (Supabase)
SELECT cron.schedule(
    'reset-query-counters', 
    '0 0 * * *', 
    'SELECT reset_daily_counters()'
);
```

---

## ⚙️ Environment Variables

Add to your `.env` file:

```env
# Existing vars
DISCORD_TOKEN=your_bot_token
GEMINI_KEYS=key1,key2,key3
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# NEW: Owner Discord User ID for /admin commands
OWNER_ID=your_discord_user_id
```

**How to get your Discord User ID:**
1. Enable Developer Mode in Discord (Settings → Advanced)
2. Right-click your username
3. Click "Copy ID"

---

## 🎮 User Commands (Server Owners)

### `/setup` Command
Allows server admins to configure PolyQuant:

```
/setup action:Set Alert Channel channel:#news-lag
→ Configures Lag Hunter alerts

/setup action:Set Query Channel channel:#trading-intel
→ Configures AI analysis responses

/setup action:Enable
→ Enables the bot in the server

/setup action:Disable
→ Disables the bot (stops responses)

/setup action:View Current Settings
→ Shows current configuration + usage stats
```

**Requirements:**
- User must have **Manage Server** permission
- Bot must have **Send Messages** permission in target channel

---

## 👑 Admin Commands (Bot Owner Only)

### `/admin` Command
Manage the entire SaaS platform:

```bash
# Ban a misbehaving server
/admin action:Ban Server server_id:123456789 reason:Spam

# Unban a server
/admin action:Unban Server server_id:123456789

# Upgrade a server tier
/admin action:Upgrade Server server_id:123456789 tier:Pro

# View global statistics
/admin action:View Stats

# List all connected servers
/admin action:List Servers
```

---

## 📊 Subscription Tiers

| Tier | Queries/Day | Price | Features |
|------|-------------|-------|----------|
| **Free** | 50 | $0 | Basic access, standard support |
| **Pro** | 500 | TBD | Priority processing, email support |
| **Enterprise** | Unlimited | TBD | Dedicated support, SLA, custom features |

**Tier Limits Enforced:**
- Queries reset at midnight UTC
- Bot auto-rejects requests when limit reached
- Upgrade message shown to server admins

---

## 🔧 Integration Testing

### **Test 1: Server Registration (Auto)**

1. Invite bot to a new server
2. Check logs: `🆕 Joined new server: YourServer (ID: 123)`
3. Bot sends welcome message with setup instructions
4. Verify in database: `SELECT * FROM servers WHERE guild_id = 123;`

### **Test 2: Setup Commands**

```
/setup action:Set Alert Channel channel:#test-alerts
→ Should confirm: "✅ Alert Channel Set!"

/setup action:View Current Settings
→ Should show:
   - Status: 🟢 Enabled
   - Tier: FREE
   - Daily Queries: 0 / 50
   - Alert Channel: #test-alerts
```

### **Test 3: Rate Limiting**

```python
# Simulate 51 queries in same day
for i in range(51):
    !ask Test question {i}

# 51st query should return:
"⏱️ Daily Limit Reached - Your server has used all 50 queries for today."
```

### **Test 4: Admin Commands**

```
/admin action:View Stats
→ Shows:
   - Total Servers: 3
   - Active Servers: 3
   - Free Tier: 2
   - Pro Tier: 1

/admin action:Upgrade Server server_id:123 tier:Pro
→ "⬆️ Server Upgraded to PRO (500 queries/day)"
```

### **Test 5: Lag Hunter Broadcast**

1. Configure alert channels in 3 different servers
2. Trigger a lag detection (or wait for real RSS feed)
3. Verify alert sent to **all 3 channels simultaneously**

---

## 🔒 Security Features

### **1. Permission Checks**
- `/setup` requires **Manage Server** permission
- `/admin` only works for bot owner (OWNER_ID)
- Rate limits prevent spam

### **2. Ban System**
```python
# Ban a server (they can't use bot at all)
/admin action:Ban Server server_id:123 reason:ToS Violation

# Server members see:
"⛔ This server is banned from using PolyQuant."
```

### **3. Cache Layer (Anti-DB Hammering)**
- Server configs cached for 5 minutes
- Avoids hitting Supabase on every command
- Cache auto-invalidates on config changes

---

## 📈 Monetization Ready

### **Current State:**
- ✅ Tiered system implemented
- ✅ Rate limiting functional
- ✅ Usage tracking per server
- ✅ Upgrade prompts on limit

### **Next Steps (Business Logic):**
1. **Payment Integration:**
   - Add Stripe/PayPal webhook handlers
   - Auto-upgrade on successful payment
   - Subscription expiration logic

2. **Premium Features:**
   - Priority queue for Pro/Enterprise
   - Longer cache retention for Pro
   - Custom Gemini models for Enterprise

3. **Analytics Dashboard:**
   - Revenue per tier
   - Most active servers
   - Query success rates

---

## 🚨 Monitoring & Alerts

### **Key Metrics to Watch:**

```python
# Daily check via /admin stats
- Total Servers: Track growth
- Active Servers: % of enabled servers
- Banned Servers: Flag abuse patterns
- Tier Distribution: Free → Paid conversion rate
```

### **Watchdog Alerts:**

The system now only alerts on:
- ❌ **Persistent errors** (3+ consecutive failures)
- ⛔ **Banned server access attempts**
- 🚨 **Rate limit abuse** (if enhanced)

**No more spam!** Normal operations don't trigger alerts.

---

## 🔄 Migration Checklist

- [x] Database schema created
- [x] Server manager with caching
- [x] Slash commands (setup + admin)
- [x] Multi-tenant lag hunter
- [x] Rate limiting system
- [x] Auto-registration on guild join
- [x] Permission checks
- [x] Ban/unban system
- [x] Tier upgrade system
- [x] Usage tracking

### **Deployment Steps:**

1. ✅ **Database:** Run `database_schema.sql` in Supabase
2. ✅ **Environment:** Add `OWNER_ID` to `.env`
3. ✅ **Bot Restart:** `python main.py`
4. ✅ **Command Sync:** Bot auto-syncs `/setup` and `/admin` on startup
5. ✅ **Test:** Invite bot to test server, run `/setup status`

---

## 📞 Support & Maintenance

### **Adding New Tiers:**

Edit `app/core/server_manager.py`:

```python
tier_limits = {
    'free': 50,
    'pro': 500,
    'enterprise': 99999,
    'vip': 10000  # NEW TIER
}
```

### **Adjusting Rate Limits:**

```python
# In server_manager.upgrade_server()
await db.upgrade_server(guild_id, 'pro', 1000)  # Increase Pro to 1000/day
```

### **Manual Database Operations:**

```sql
-- Check server status
SELECT guild_id, guild_name, tier, enabled, query_count_today 
FROM servers 
WHERE tier = 'pro';

-- Reset a server's query count
UPDATE servers 
SET query_count_today = 0, last_reset = NOW() 
WHERE guild_id = 123456789;

-- Force upgrade a server
UPDATE servers 
SET tier = 'enterprise', max_queries_per_day = 99999 
WHERE guild_id = 123456789;
```

---

## 🎉 Success Indicators

Your SaaS migration is successful when:

1. ✅ Bot joins new servers and sends welcome message
2. ✅ `/setup` command shows in Discord autocomplete
3. ✅ Server admins can configure channels
4. ✅ Rate limits work (51st query denied)
5. ✅ Lag alerts broadcast to all configured servers
6. ✅ `/admin stats` shows accurate data
7. ✅ Banned servers can't use bot
8. ✅ No false Watchdog alerts

---

## 🚀 Next-Level Features (Future)

1. **Web Dashboard:**
   - Server owners view usage stats
   - Self-service subscription management
   - Historical query analytics

2. **Webhooks:**
   - Custom lag alerts per server
   - Slack/Teams integration
   - API for enterprise clients

3. **Advanced AI:**
   - Server-specific training data
   - Custom agent personalities per tier
   - Backtesting engine for Pro+

4. **White-Label:**
   - Custom bot names per server
   - Branded embeds
   - Enterprise-only features

---

## 📖 Summary

**You now have a production-ready multi-tenant SaaS bot!**

- 🏢 **Multi-Tenant:** One bot serves many servers
- 💰 **Monetization-Ready:** Tiered subscriptions + rate limits
- 🛡️ **Secure:** Permission checks, ban system, caching
- 📊 **Observable:** Admin commands, usage tracking
- 🚀 **Scalable:** Database-backed, async-first

**From "bot for me" → "bot for everyone"** 🎯

---

*Migration Completed: 2025-12-01*  
*Architecture: Multi-Tenant SaaS Platform*  
*Stack: Discord.py + Supabase + AsyncIO*

