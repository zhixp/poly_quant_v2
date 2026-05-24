# 🔄 Slash Command Sync Guide

## 🎯 Problem: Slash Commands Not Appearing?

Discord slash commands can take **up to 1 hour** to sync globally. This guide shows how to **force instant sync** for your server.

---

## 🚀 Quick Solution: Force Sync

### **Option 1: Instant Sync to Your Server (Recommended)**

In Discord, run:
```
!serverinfo
```

This shows your server ID and the exact sync command. Then run:
```
!sync YOUR_SERVER_ID
```

**Example:**
```
!serverinfo
→ Shows: Server ID: 504583329400750080

!sync 504583329400750080
→ ✅ Commands available INSTANTLY!
```

### **Option 2: Global Sync (Slow)**

```
!sync
```

**Note:** Takes up to 1 hour to propagate to all servers.

---

## 📋 Available Commands

### **`!sync [guild_id]`** (Owner Only)

Force syncs slash commands to Discord.

**Usage:**
```bash
# Instant sync to specific server (your current server ID shown by !serverinfo)
!sync 504583329400750080

# Global sync (slow, all servers)
!sync
```

**Output:**
```
✅ Force Synced 2 commands to guild 504583329400750080
Commands available instantly in that server!

Commands synced:
• /setup - Configure PolyQuant for your server
• /admin - Admin-only server management
```

### **`!serverinfo`** (Everyone)

Shows server information including the ID needed for force sync.

**Usage:**
```
!serverinfo
```

**Output:**
```
📋 Server Information
Server ID: 504583329400750080
Force Sync Command: !sync 504583329400750080
Owner: @YourName
Members: 42
Created: 2 years ago
```

---

## 🔧 How Slash Command Sync Works

### **Global Sync (Default)**
```
Bot starts → tree.sync() → Discord API
                            ↓
                      Propagates to all servers (1 hour)
```

### **Guild-Specific Sync (Force)**
```
!sync GUILD_ID → tree.sync(guild=guild) → Discord API
                                           ↓
                                    Available INSTANTLY
```

---

## 🎮 Step-by-Step Tutorial

### **First Time Setup:**

1. **Invite bot to your server** (if not already)
   - Make sure bot has `applications.commands` scope

2. **Get your server ID:**
   ```
   !serverinfo
   ```
   Copy the Server ID shown

3. **Force sync commands:**
   ```
   !sync YOUR_SERVER_ID_HERE
   ```

4. **Verify commands appear:**
   - Type `/` in Discord
   - Should see `/setup` and `/admin`

5. **Test a command:**
   ```
   /setup action:View Current Settings
   ```

---

## 🚨 Troubleshooting

### **Commands Still Don't Appear**

**Check 1: Bot Permissions**
```
Discord Developer Portal → Your App → OAuth2 → URL Generator
✅ Check: bot
✅ Check: applications.commands
```

**Check 2: Re-invite Bot**
```
Generate new invite URL with applications.commands scope
Re-invite bot to your server
Run !sync GUILD_ID again
```

**Check 3: Developer Mode**
```
Discord Settings → Advanced → Enable Developer Mode
Right-click server icon → Copy ID
Use that ID in !sync command
```

### **"Permission Denied" Error**

The `!sync` command is **owner-only**. Make sure:
1. You set `OWNER_ID` in `.env`
2. The ID matches YOUR Discord User ID
3. You're using the correct Discord account

**Get your User ID:**
```
Discord Settings → Advanced → Enable Developer Mode
Right-click your username → Copy ID
Add to .env: OWNER_ID=YOUR_ID_HERE
```

### **Sync Works But Commands Have Wrong Description**

You changed the command code but didn't restart the bot:
```bash
# Stop bot
Ctrl+C

# Start bot
python main.py

# Force sync again
!sync YOUR_GUILD_ID
```

---

## 💡 Pro Tips

### **Development Workflow:**

```bash
1. Edit command code (e.g., app/cogs/setup.py)
2. Restart bot: python main.py
3. Force sync: !sync GUILD_ID
4. Test instantly in Discord
```

### **Multi-Server Setup:**

```bash
# Sync to Server A (your test server)
!sync 111111111111111111

# Sync to Server B (your production server)
!sync 222222222222222222

# Once tested, global sync for all others
!sync
```

### **Check What's Synced:**

The bot logs synced commands on startup:
```
✅ Synced 2 slash command(s)
```

Check `logs.txt` or terminal for details.

---

## 📖 Command Reference

| Command | Who Can Use | Speed | Scope |
|---------|-------------|-------|-------|
| `!sync` | Owner only | 1 hour | All servers |
| `!sync GUILD_ID` | Owner only | Instant | One server |
| `!serverinfo` | Everyone | N/A | Shows info |

---

## 🔒 Security Notes

### **Why is !sync Owner-Only?**

Syncing commands triggers Discord API rate limits. If anyone could sync:
- Malicious users could spam sync
- Bot could get rate-limited
- Commands would fail for everyone

### **Alternative: Trusted Users**

If you want to allow specific users to sync:

Edit `main.py`:
```python
TRUSTED_SYNCERS = [123456789, 987654321]  # User IDs

@bot.command()
async def sync(ctx, guild_id: int = None):
    if ctx.author.id not in TRUSTED_SYNCERS and not await bot.is_owner(ctx.author):
        await ctx.send("❌ Not authorized")
        return
    # ... rest of sync code
```

---

## 🎯 Common Scenarios

### **Scenario 1: Fresh Bot Deployment**

```bash
1. Bot starts → Auto-syncs globally
2. Wait 1 hour OR force sync to test server
3. Verify commands work in test server
4. Leave global sync to propagate naturally
```

### **Scenario 2: Added New Slash Command**

```bash
1. Add command code (e.g., new cog)
2. Restart bot
3. !sync YOUR_DEV_SERVER_ID
4. Test new command
5. If works, !sync (global) for production
```

### **Scenario 3: Commands Disappeared**

```bash
# Usually happens after bot restart without proper sync
!sync YOUR_GUILD_ID

# If still missing, check bot permissions and re-invite
```

---

## ✅ Success Checklist

After running force sync, you should see:

- [ ] `/setup` appears in Discord command autocomplete
- [ ] `/admin` appears (for owner)
- [ ] Commands have descriptions
- [ ] Commands execute without errors
- [ ] Bot logs show: "✅ Synced 2 slash command(s)"

---

## 📚 Related Documentation

- `QUICK_START_SAAS.md` - Full setup guide
- `SAAS_MIGRATION_GUIDE.md` - Architecture details
- `app/cogs/setup.py` - Setup command code
- `app/cogs/admin.py` - Admin command code

---

## 🆘 Still Having Issues?

### **Debug Checklist:**

```bash
# 1. Check bot is running
ps aux | grep python  # Linux/Mac
tasklist | findstr python  # Windows

# 2. Check bot logs for errors
cat logs.txt | grep ERROR

# 3. Verify bot token
echo $DISCORD_TOKEN  # Should show token

# 4. Test basic bot connectivity
# In Discord: !serverinfo
# Should respond immediately

# 5. Check cogs loaded
# Look for: "✅ Slash commands loaded" in logs
```

### **Emergency Reset:**

```bash
# 1. Stop bot completely
taskkill /F /IM python.exe

# 2. Clear command cache (Discord side)
# Discord Dev Portal → Your App → General Information
# Click "Reset Bot Token" (if desperate)

# 3. Fresh restart
python main.py

# 4. Force sync
!sync YOUR_GUILD_ID
```

---

## 🎉 Summary

**Instant Slash Commands in 3 Steps:**

1. Run `!serverinfo` to get your server ID
2. Run `!sync YOUR_SERVER_ID` 
3. Commands appear **immediately** in Discord

**That's it!** No more waiting hours for global sync.

---

*Last Updated: 2025-12-01*  
*PolyQuant Multi-Tenant SaaS Platform*

