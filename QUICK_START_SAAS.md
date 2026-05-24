# 🚀 PolyQuant SaaS - Quick Start Guide

## 1️⃣ Setup Database (5 minutes)

### **A. Create Supabase Project**
1. Go to [supabase.com](https://supabase.com)
2. Create new project
3. Note your `Project URL` and `anon/public key`

### **B. Run SQL Schema**
1. In Supabase dashboard → **SQL Editor**
2. Copy contents of `database_schema.sql`
3. Click **Run**
4. Verify: Check **Table Editor** → see `servers` and `analysis_logs`

---

## 2️⃣ Configure Environment

### **A. Copy Template**
```bash
cp .env.example .env
```

### **B. Fill Required Variables**
```env
# REQUIRED
DISCORD_TOKEN=your_bot_token            # From Discord Developer Portal
OWNER_ID=123456789                       # Your Discord User ID
GEMINI_KEYS=key1,key2                   # From Google AI Studio
SUPABASE_URL=https://xxx.supabase.co    # From Supabase dashboard
SUPABASE_KEY=your_anon_key              # From Supabase dashboard
```

### **C. Get Discord User ID**
1. Enable Developer Mode (Discord Settings → Advanced)
2. Right-click your username → "Copy ID"
3. Paste into `OWNER_ID`

---

## 3️⃣ Install Dependencies

```bash
python -m pip install -r requirements.txt --upgrade
```

---

## 4️⃣ Start Bot

```bash
python main.py
```

### **Expected Output:**
```
✅ PolyQuant Online: YourBot#1234
📍 Connected to 1 server(s):
   - TestServer (ID: 123456789)
✅ Slash commands loaded
✅ Synced 2 slash command(s)
📡 Lag Hunter: Active
✅ All systems operational
```

### **🚀 Force Sync Commands (Instant Availability)**

Slash commands can take up to 1 hour to appear globally. For **instant** sync:

```bash
# 1. Get your server ID
!serverinfo

# 2. Force sync to your server (instant)
!sync YOUR_SERVER_ID

# Example:
!sync 504583329400750080
→ ✅ Commands available IMMEDIATELY!
```

**See:** `SLASH_COMMAND_SYNC_GUIDE.md` for full details.

---

## 5️⃣ Test Commands

### **In Discord (As Server Admin):**

```
/setup action:View Current Settings
→ Shows current config (if registered)

/setup action:Set Alert Channel channel:#news-lag
→ Configures Lag Hunter alerts

/setup action:Set Query Channel channel:#trading-intel
→ Configures AI responses
```

### **Test Query:**
```
!ask Will Bitcoin hit 100k?
→ Should check rate limits and return analysis
```

### **As Bot Owner:**
```
/admin action:View Stats
→ Shows global platform statistics

/admin action:List Servers
→ Lists all connected servers with status
```

---

## 6️⃣ Verify Multi-Tenancy

### **Test Auto-Registration:**
1. Invite bot to a NEW server
2. Check logs: `🆕 Joined new server`
3. Bot sends welcome message
4. Run: `SELECT * FROM servers;` in Supabase
5. Verify new row created

### **Test Rate Limits:**
```bash
# Run 51 queries quickly
for i in {1..51}; do
    echo "!ask Test $i" 
done

# 51st should return:
"⏱️ Daily Limit Reached"
```

### **Test Lag Hunter Broadcast:**
1. Configure alert channel in Server A
2. Configure alert channel in Server B
3. Wait for lag detection (or manually trigger)
4. Verify alert sent to BOTH servers

---

## ✅ Success Checklist

- [ ] Bot starts without errors
- [ ] `/setup` command appears in Discord
- [ ] `/admin` command works for owner
- [ ] Server config saved to database
- [ ] Rate limits work (50 free queries/day)
- [ ] Lag alerts broadcast to all servers
- [ ] Admin can ban/unban servers
- [ ] Tier upgrades work

---

## 🚨 Troubleshooting

### **Slash Commands Don't Appear**

```python
# In Discord Developer Portal:
1. Bot → OAuth2 → URL Generator
2. Check: bot, applications.commands
3. Re-invite bot with new URL
```

### **Database Connection Failed**

```python
# Check Supabase credentials
- URL format: https://your-project.supabase.co
- Key: anon/public key (NOT service_role)
- Run: SELECT 1; in SQL Editor to test connection
```

### **Rate Limits Not Working**

```sql
-- Check if function exists
SELECT * FROM pg_proc WHERE proname = 'increment_query_count';

-- Manually reset counter
UPDATE servers SET query_count_today = 0 WHERE guild_id = YOUR_GUILD_ID;
```

### **"/admin not working"**

```bash
# Verify OWNER_ID in .env matches your Discord User ID
echo $OWNER_ID

# Check logs for permission denial
grep "Access Denied" logs.txt
```

---

## 📖 Next Steps

1. **Read Full Guide:** `SAAS_MIGRATION_GUIDE.md`
2. **Customize Tiers:** Edit limits in `server_manager.py`
3. **Add Payment:** Integrate Stripe webhooks
4. **Monitor Usage:** Check `/admin stats` daily
5. **Scale:** Add more Gemini keys for higher throughput

---

## 🎉 You're Live!

Your bot is now a **production SaaS platform**:
- ✅ Multi-server support
- ✅ Tiered subscriptions
- ✅ Rate limiting
- ✅ Admin controls
- ✅ Database-backed

**Welcome to the SaaS world!** 🚀

---

*Quick Start v1.0 • PolyQuant Multi-Tenant Platform*

