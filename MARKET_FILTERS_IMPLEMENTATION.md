# 🎯 Market Filters Implementation - Complete Guide

## Feature: Per-Server Market Category Filtering

Allow Discord admins to filter Genesis Scanner alerts by category (Politics, Crypto, Sports, etc.) to reduce spam.

---

## ✅ Changes Applied

### 1. Database Schema (`database_schema.sql`)
- ✅ Added `market_filters TEXT` column to servers table
- ✅ Created migration file `DATABASE_MIGRATION_FILTERS.sql`

### 2. Server Manager (`app/core/server_manager.py`)
- ✅ Added `market_filters` to `ServerConfig` class
- ✅ Added `set_market_filters()` method

### 3. Database Module (`app/core/database.py`)
- ✅ Updated `get_all_new_markets_channels()` to return (guild_id, channel_id, filters) tuples
- ✅ Added backwards compatibility fallback

### 4. Genesis Scanner (`app/scanners/genesis_scanner.py`)
- ✅ Updated `_post_to_firehose()` to handle per-server filters
- ✅ Added spam guard: Auto-filters "15m" and "5m" price prediction markets
- ✅ Added per-server category filtering logic

---

## ⏳ Remaining Changes

### 5. Setup Command (`app/cogs/setup.py`)

**Add filters parameter and action:**

```python
# Line 20-39: Update command signature
@app_commands.describe(
    action="What to configure",
    channel="The channel to use (for alert/query actions)",
    filters="Comma-separated categories (e.g., Politics,Crypto,Sports) or leave empty for all"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Set Alert Channel (Lag Hunter notifications)", value="alert"),
    app_commands.Choice(name="Set Query Channel (AI analysis responses)", value="query"),
    app_commands.Choice(name="Set New Markets Channel (All new markets)", value="newmarkets"),
    app_commands.Choice(name="Set Curated Channel (High-confidence picks)", value="curated"),
    app_commands.Choice(name="Set Market Filters (Filter by category)", value="filters"),  # NEW
    app_commands.Choice(name="Enable Bot", value="enable"),
    app_commands.Choice(name="Disable Bot", value="disable"),
    app_commands.Choice(name="View Current Settings", value="status")
])
@app_commands.checks.has_permissions(manage_guild=True)
async def setup(
    self, 
    interaction: discord.Interaction, 
    action: app_commands.Choice[str],
    channel: discord.TextChannel = None,
    filters: str = None  # NEW
):
```

**Add filters action handler (after line 130):**

```python
elif action_value == "filters":
    if not filters:
        # Clear filters (show all)
        success = await server_manager.set_market_filters(guild_id, None)
        if success:
            await interaction.followup.send(
                "✅ **Market Filters Cleared!**\n"
                "Your server will now receive alerts for ALL categories.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ **Error:** Failed to clear filters.",
                ephemeral=True
            )
    else:
        # Validate and set filters
        valid_categories = ['politics', 'crypto', 'sports', 'macro', 'economics', 'pop culture', 'science']
        filter_list = [f.strip().lower() for f in filters.split(',')]
        invalid = [f for f in filter_list if f not in valid_categories]
        
        if invalid:
            await interaction.followup.send(
                f"❌ **Error:** Invalid categories: {', '.join(invalid)}\n\n"
                f"**Valid categories:** {', '.join(valid_categories)}",
                ephemeral=True
            )
            return
        
        # Save filters
        success = await server_manager.set_market_filters(guild_id, filters)
        if success:
            await interaction.followup.send(
                f"✅ **Market Filters Updated!**\n"
                f"Your server will only receive alerts for: **{filters}**\n\n"
                f"To clear filters and see all categories, run:\n"
                f"`/setup action:Set Market Filters` (leave filters empty)",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ **Error:** Failed to set filters.",
                ephemeral=True
            )
```

**Update status display (around line 220):**

```python
# After curated_channel field, add:
embed.add_field(
    name="Market Filters",
    value=config.market_filters if config.market_filters else "❌ Not Set (Showing All)",
    inline=False
)
```

---

## 🗄️ Database Migration

**Run in Supabase SQL Editor:**

```sql
-- Add market_filters column
ALTER TABLE servers 
ADD COLUMN IF NOT EXISTS market_filters TEXT;

-- Verify
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'servers' 
AND column_name = 'market_filters';
```

---

## 📖 Usage Examples

### Set Filters (Politics + Crypto only)
```
/setup action:Set Market Filters filters:Politics,Crypto
```

### Set Filters (Sports only)
```
/setup action:Set Market Filters filters:Sports
```

### Clear Filters (Show all)
```
/setup action:Set Market Filters
```
(Leave filters parameter empty)

### View Current Filters
```
/setup action:View Current Settings
```

---

## 🛡️ Spam Protection

**Auto-filtered markets:**
- Any market with "15m" in the title (e.g., "BTC price in 15m")
- Any market with "5m" in the title (e.g., "ETH price in 5m")

These are automatically blocked for ALL servers to prevent price prediction spam.

---

## 🎯 Valid Categories

- `Politics`
- `Crypto`
- `Sports`
- `Macro`
- `Economics`
- `Pop Culture`
- `Science`

(Case-insensitive, comma-separated)

---

## 🧪 Testing

### Test 1: Set Filters
```
/setup action:Set Market Filters filters:Politics,Crypto
→ Should confirm filters set
→ Check /setup status shows "Politics,Crypto"
```

### Test 2: Verify Filtering
```
Wait for Genesis Scanner to find new markets
→ Should only see Politics and Crypto markets
→ Sports/Other categories should be filtered out
```

### Test 3: Clear Filters
```
/setup action:Set Market Filters
→ Should confirm filters cleared
→ Check /setup status shows "Not Set (Showing All)"
```

### Test 4: Spam Guard
```
Wait for a "15m" or "5m" price prediction market
→ Should NOT appear in any server (auto-filtered)
→ Check logs for "Filtered spam market"
```

---

## 📊 Expected Behavior

### Before Filters:
```
Server receives:
- Politics market ✅
- Crypto market ✅
- Sports market ✅
- Pop Culture market ✅
Total: 4 alerts
```

### After Setting "Politics,Crypto":
```
Server receives:
- Politics market ✅
- Crypto market ✅
- Sports market ❌ (filtered)
- Pop Culture market ❌ (filtered)
Total: 2 alerts
```

---

## 🔍 Debugging

### Check if filters are working:
```
Look for logs:
"Filtered {category} market for guild {guild_id} (allowed: [...])"
```

### Check spam guard:
```
Look for logs:
"Filtered spam market: {question}"
```

### Check database:
```sql
SELECT guild_name, market_filters 
FROM servers 
WHERE market_filters IS NOT NULL;
```

---

## ✅ Deployment Checklist

- [x] Database schema updated
- [x] Migration file created
- [x] ServerConfig updated
- [x] Database module updated
- [x] Genesis Scanner updated with filtering logic
- [x] Spam guard implemented
- [ ] Setup command updated (needs manual edit)
- [ ] Database migration run in Supabase
- [ ] Code pushed to GitHub
- [ ] Railway redeployed
- [ ] Tested in Discord

---

## 🚀 Next Steps

1. **Apply remaining setup.py changes** (see section 5 above)
2. **Run database migration** in Supabase
3. **Commit and push** all changes
4. **Test** with `/setup action:Set Market Filters filters:Politics,Crypto`
5. **Verify** filtering works by watching Genesis alerts

---

**Status:** 80% Complete - Setup command needs manual update
**Priority:** HIGH - Reduces spam significantly
**Impact:** Improves user experience, reduces noise


