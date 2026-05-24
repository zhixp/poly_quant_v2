# 🎯 /filter Command - User Guide

## New Simplified Filtering System

Instead of the complex `/setup` command, use the new `/filter` command to control what markets you see!

---

## 🚀 Quick Start

### Filter New Markets (Genesis Scanner)
```
/filter action:New Markets categories:Politics,Crypto,Sports
```
→ Only see Politics, Crypto, and Sports markets

### Filter Lag Hunter Alerts
```
/filter action:Lag Hunter categories:Politics,Macro
```
→ Only see Politics and Macro breaking news alerts

### Show All (Clear Filters)
```
/filter action:Show All
```
→ Receive alerts for all categories

### View Current Filters
```
/filter action:View Current Filters
```
→ See what categories you're currently filtering

---

## 📋 Available Categories

- **Politics** - Elections, government, policy
- **Crypto** - Bitcoin, Ethereum, DeFi, NFTs
- **Sports** - NFL, NBA, Soccer, etc.
- **Macro** - Fed decisions, inflation, GDP
- **Economics** - Market indices, commodities
- **Pop Culture** - Entertainment, celebrities
- **Science** - Technology, research, discoveries

---

## 🛡️ Automatic Spam Protection

**These markets are ALWAYS blocked (all servers):**
- ✅ 15m price predictions (e.g., "BTC up or down in 15m")
- ✅ 5m price predictions
- ✅ 1h price predictions
- ✅ 4h price predictions
- ✅ 30m price predictions
- ✅ Up/Down markets (e.g., "XRP up or down?")
- ✅ Crypto up/down spam

**You don't need to do anything - these are auto-filtered!**

---

## 📊 Examples

### Example 1: Politics + Crypto Only
```
/filter action:New Markets categories:Politics,Crypto
```

**What you'll see:**
- ✅ "Will Trump win 2024?" (Politics)
- ✅ "Bitcoin reach $100k?" (Crypto)
- ❌ "Lakers vs Warriors" (Sports - filtered)
- ❌ "BTC up in 15m?" (Spam - auto-blocked)

### Example 2: Sports Only
```
/filter action:New Markets categories:Sports
```

**What you'll see:**
- ✅ "Lakers vs Warriors" (Sports)
- ✅ "Super Bowl winner?" (Sports)
- ❌ "Trump win 2024?" (Politics - filtered)
- ❌ "ETH up in 1h?" (Spam - auto-blocked)

### Example 3: Everything
```
/filter action:Show All
```

**What you'll see:**
- ✅ All Politics markets
- ✅ All Crypto markets
- ✅ All Sports markets
- ✅ All other categories
- ❌ Spam still blocked (15m, 1h, up/down)

---

## 🔧 How It Works

### Per-Server Filtering
- Each Discord server can set its own filters
- Server A: Politics only
- Server B: Crypto + Sports
- Server C: Everything
- **All independent!**

### Two Types of Alerts
1. **New Markets (Genesis Scanner)** - All new markets from Polymarket
2. **Lag Hunter Alerts** - Breaking news matched to markets

**You can filter BOTH independently!**

---

## ⚠️ Common Mistakes

### ❌ Wrong: Spaces in categories
```
/filter action:New Markets categories:Politics, Crypto, Sports
```
**Problem:** Spaces after commas

### ✅ Right: No spaces
```
/filter action:New Markets categories:Politics,Crypto,Sports
```

### ❌ Wrong: Invalid category
```
/filter action:New Markets categories:Bitcoin
```
**Problem:** "Bitcoin" is not a category (use "Crypto")

### ✅ Right: Valid categories
```
/filter action:New Markets categories:Crypto
```

---

## 🧪 Testing

### Test 1: Set Filters
```
/filter action:New Markets categories:Politics,Crypto
→ Should confirm: "Filters Updated! Categories: Politics,Crypto"
```

### Test 2: Verify Filters
```
/filter action:View Current Filters
→ Should show: "Active Filters: Politics,Crypto"
```

### Test 3: Check Alerts
```
Wait for Genesis Scanner to find new markets
→ Should only see Politics and Crypto markets
→ Sports/Other should not appear
```

### Test 4: Clear Filters
```
/filter action:Show All
→ Should confirm: "Filters Cleared!"
→ Should start seeing all categories again
```

---

## 🎯 Pro Tips

### Tip 1: Start Narrow, Then Expand
```
Day 1: /filter categories:Politics
       → See only politics, decide if you want more
Day 2: /filter categories:Politics,Crypto
       → Add crypto to your feed
```

### Tip 2: Different Filters for Different Channels
```
#politics-alerts: /filter categories:Politics
#crypto-alerts: /filter categories:Crypto
#all-markets: /filter action:Show All
```

### Tip 3: Check Filters Regularly
```
/filter action:View Current Filters
→ Reminds you what you're filtering
```

---

## 🚨 Spam Protection Details

### What Gets Auto-Blocked:

**Time-based price predictions:**
- "BTC price in 15m?"
- "ETH up or down in 5m?"
- "XRP price in 1h?"
- "SOL price in 4h?"

**Up/Down markets:**
- "Crypto up or down?"
- "BTC up?"
- "ETH down?"

**Why we block these:**
- High frequency (dozens per day)
- Low signal (random noise)
- Not actionable (too short timeframe)
- Spam the feed

---

## 📖 FAQ

**Q: Can I filter by multiple categories?**
A: Yes! Use comma-separated: `Politics,Crypto,Sports`

**Q: Can I see ONLY spam markets?**
A: No - spam is always blocked for all servers

**Q: Does this affect /ask command?**
A: No - `/ask` works on any market you provide

**Q: Can I have different filters for Genesis vs LagHunter?**
A: Currently they share the same filters. Future update may separate them.

**Q: What if I misspell a category?**
A: Bot will show error with list of valid categories

**Q: Can I add custom categories?**
A: Not yet - only predefined categories available

---

## 🎉 Summary

**Before:**
- Received ALL markets (100+ per day)
- Lots of spam (15m, 1h, up/down)
- No control over what you see

**After:**
- Choose specific categories (Politics, Crypto, etc.)
- Spam auto-blocked (15m, 1h, up/down)
- Clean, focused feed

**Command:**
```
/filter action:New Markets categories:Politics,Crypto
```

**Result:** Only Politics + Crypto alerts, no spam! 🎯

---

*Last Updated: 2025-12-02*
*Feature: Per-Server Market Filters + Unified Spam Guard*
*Status: LIVE - Ready to use after redeploy*

