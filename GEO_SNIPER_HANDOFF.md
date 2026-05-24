# PolyQuant Geo Sniper Handoff

## What changed

Added a read-only geopolitical Polymarket strategy to the Discord bot.

### New module

- `app/scanners/geo_sniper.py`

Capabilities:

- Watches configured Polymarket geopolitical event ladders.
- Default watchlist: `us-x-iran-permanent-peace-deal-by`.
- Pulls live Gamma API market prices.
- Pulls CLOB price history using the YES token when condition history is empty.
- Pulls recent Data API trades to detect large flow.
- Parses direct catalyst URLs and RSS feeds for geopolitics language.
- Uses Truth Social, direct catalyst pages, and normal RSS by default.
- Does not use X/Twitter by default; `GEO_SNIPER_X_RSS_FEEDS` is ignored unless `GEO_SNIPER_ENABLE_X_BRIDGE=true`.
- Special handling for US/Iran permanent peace deadline markets:
  - distinguishes MOU/framework/headline pumps from qualifying permanent agreement language;
  - alerts when source language supports a possible NO edge;
  - marks invalidation risk if official wording says permanent/lasting/final end of hostilities.
- Posts Discord embeds to existing configured alert channels.
- No trading support. Alerts are watch/consider-only; user decides.

### Bot wiring

- `main.py`
  - imports `GeoSniper`
  - initializes `self.geo_sniper`
  - starts it in `on_ready()`

### Admin slash commands

- `app/cogs/admin.py`
  - `/test_geo_sniper force_alert:true|false`
  - `/geo_sniper_stats`

### Env vars

Documented in `ENV_VARIABLES.md`:

```env
GEO_SNIPER_ENABLED=true
GEO_SNIPER_INTERVAL_SECONDS=300
GEO_SNIPER_EVENT_SLUGS=us-x-iran-permanent-peace-deal-by
GEO_SNIPER_MIN_PRICE_MOVE=0.07
GEO_SNIPER_MIN_WHALE_USDC=5000
GEO_SNIPER_DIRECT_SOURCES=https://edition.cnn.com/2026/05/23/middleeast/iran-us-progress-framework-diplomacy-intl
GEO_SNIPER_ENABLE_X_BRIDGE=false
GEO_SNIPER_X_RSS_FEEDS=
```

## Verification

Ran:

```bash
python -m py_compile app/scanners/geo_sniper.py main.py app/cogs/admin.py test_price_parsing.py
uv run --with supabase --with pytest --with pytest-asyncio --with aiohttp --with discord.py --with python-dateutil python -m pytest tests/test_golden_set.py test_price_parsing.py -q
```

Result:

- `10 passed`
- one upstream `audioop` deprecation warning from `discord.py`

Smoke scan result with Discord send patched out:

- markets checked: 34
- source hits: 3
- signals found: 7
- confirms US/Iran ladder logic is firing on framework/MOU language.

## Deploy notes

1. Put this worktree on VPS.
2. Install requirements normally.
3. Ensure `.env` has `DISCORD_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_KEYS`.
4. Set `GEO_SNIPER_ENABLED=true`.
5. In Discord, configure an alert channel via existing `/setup` if not already done.
6. Run `/test_geo_sniper force_alert:true` in Discord.
7. Run `/geo_sniper_stats` after a few minutes.
8. Leave `GEO_SNIPER_ENABLE_X_BRIDGE=false` until Grok API integration is added.

## Safety

- No hardcoded secrets added.
- No wallet/trading functions added.
- No X/Twitter login, cookies, browser session, or dummy-account scraping in the bot.
- Alerts route through the dedicated Geo channel config.
- Existing tests now include a pytest marker for the async market resolver test.
