# 🔐 Environment Variables Reference

## Required for SaaS Platform

Copy this to your `.env` file:

```env
# === DISCORD ===
DISCORD_TOKEN=your_discord_bot_token_here
OWNER_ID=your_discord_user_id_here

# === GEMINI AI (Comma-separated for round-robin) ===
GEMINI_KEYS=key1,key2,key3

# === SEARCH APIS (Optional - Waterfall will skip if missing) ===
TAVILY_API_KEY=your_tavily_key_here
BRAVE_API_KEY=your_brave_key_here
EXA_KEYS=key1,key2

# === SPECIALIST APIS (Optional) ===
COURT_LISTENER_TOKEN=your_court_listener_token
CRYPTOPANIC_API_KEY=your_cryptopanic_key

# === DATABASE (Required for Multi-Tenant) ===
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key_here

# === MONITORING (Optional - for error alerts) ===
ADMIN_WEBHOOK_URL=your_discord_webhook_url_for_errors

# === GEO SNIPER (Optional - Polymarket geopolitical alerts) ===
GEO_SNIPER_ENABLED=true
GEO_SNIPER_INTERVAL_SECONDS=300
GEO_SNIPER_EVENT_SLUGS=us-x-iran-permanent-peace-deal-by
GEO_SNIPER_MIN_PRICE_MOVE=0.07
GEO_SNIPER_MIN_WHALE_USDC=5000
# Optional comma-separated catalyst URLs to parse directly
GEO_SNIPER_DIRECT_SOURCES=https://edition.cnn.com/2026/05/23/middleeast/iran-us-progress-framework-diplomacy-intl
# X/Twitter is disabled by default until Grok API integration is added.
GEO_SNIPER_ENABLE_X_BRIDGE=false
# Ignored unless GEO_SNIPER_ENABLE_X_BRIDGE=true
GEO_SNIPER_X_RSS_FEEDS=
```

## How to Get Each Variable

### **DISCORD_TOKEN**
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application → Bot
3. Click "Reset Token" and copy

### **OWNER_ID** (NEW - For Admin Commands)
1. Enable Developer Mode in Discord (Settings → Advanced)
2. Right-click your username
3. Click "Copy ID"

### **GEMINI_KEYS**
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create API keys (recommend 3+ for load balancing)
3. Separate with commas: `key1,key2,key3`

### **SUPABASE_URL & SUPABASE_KEY**
1. Create project at [supabase.com](https://supabase.com)
2. Dashboard → Settings → API
3. Copy `URL` and `anon/public` key (NOT service_role!)

---

## Variable Importance

| Variable | Required | Purpose |
|----------|----------|---------|
| `DISCORD_TOKEN` | ✅ Yes | Bot authentication |
| `OWNER_ID` | ✅ Yes | Admin command access |
| `GEMINI_KEYS` | ✅ Yes | AI analysis engine |
| `SUPABASE_URL` | ✅ Yes | Multi-tenant database |
| `SUPABASE_KEY` | ✅ Yes | Database authentication |
| `TAVILY_API_KEY` | ⚠️ Optional | Enhanced search (Tier 2) |
| `BRAVE_API_KEY` | ⚠️ Optional | Large index search (Tier 3) |
| `EXA_KEYS` | ⚠️ Optional | Document search (Tier 4) |
| `ADMIN_WEBHOOK_URL` | ⚠️ Optional | Error monitoring |
| `GEO_SNIPER_ENABLED` | ⚠️ Optional | Enable/disable geopolitical scanner |
| `GEO_SNIPER_EVENT_SLUGS` | ⚠️ Optional | Comma-separated Polymarket events to watch |
| `GEO_SNIPER_DIRECT_SOURCES` | ⚠️ Optional | Catalyst URLs to parse for rule-language signals |

### Geo X/Grok note

`GEO_SNIPER_ENABLE_X_BRIDGE` defaults to `false`. Leave it false for now.
`GEO_SNIPER_X_RSS_FEEDS` is ignored unless that flag is explicitly set to `true`.
Use Truth Social, direct catalyst pages, and normal RSS feeds until Grok API is plugged in.

---

*Save this as `.env` in your project root*

