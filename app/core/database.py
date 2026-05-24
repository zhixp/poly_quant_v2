from supabase import create_client, Client
from app.config import Config
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("Database")

class Database:
    def __init__(self):
        try:
            if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
                logger.warning("Supabase credentials not configured - Cache disabled")
                self.client = None
            else:
                self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                logger.info("✅ Supabase connected (Cache enabled)")
        except Exception as e:
            logger.warning(f"Supabase connection failed: {e} - Cache disabled")
            self.client = None

    def get_cache(self, query: str):
        """
        Checks DB for a recent answer to this exact question.
        Per poly.md Section 4: Returns cached answer if found within last 6 hours.
        """
        if not self.client: return None
        try:
            # Calculate cutoff time (6 hours ago) using Python datetime
            cutoff = (datetime.utcnow() - timedelta(hours=6)).isoformat()
            
            response = self.client.table("analysis_logs")\
                .select("response, created_at")\
                .eq("query", query)\
                .gte("created_at", cutoff)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"⚡ Cache HIT for query: {query[:50]}...")
                return response.data[0]['response']
            
            logger.info(f"💾 Cache MISS - fetching fresh data")
            return None
        except Exception as e:
            logger.warning(f"DB Read Error: {e}")
            return None

    def save_log(self, query: str, response: str, guild_id: int = None):
        """Saves the Answer for future recall."""
        if not self.client: return
        try:
            self.client.table("analysis_logs").insert({
                "query": query, 
                "response": response,
                "guild_id": guild_id
            }).execute()
        except Exception as e:
            logger.error(f"DB Write Error: {e}")
    
    # ===== MULTI-TENANT FUNCTIONS =====
    
    async def get_server_config(self, guild_id: int):
        """Fetches server configuration."""
        if not self.client: return None
        try:
            response = self.client.table("servers")\
                .select("*")\
                .eq("guild_id", guild_id)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to fetch server config: {e}")
            return None
    
    async def register_server(self, guild_id: int, guild_name: str):
        """Registers a new server."""
        if not self.client: return
        try:
            self.client.table("servers").insert({
                "guild_id": guild_id,
                "guild_name": guild_name,
                "tier": "free",
                "enabled": True,
                "is_banned": False,
                "max_queries_per_day": 50,
                "query_count_today": 0
            }).execute()
        except Exception as e:
            # If already exists, update name
            try:
                self.client.table("servers")\
                    .update({"guild_name": guild_name})\
                    .eq("guild_id", guild_id)\
                    .execute()
            except:
                logger.error(f"Failed to register server: {e}")
    
    async def update_server_setting(self, guild_id: int, key: str, value):
        """Updates a server setting."""
        if not self.client: return
        try:
            self.client.table("servers")\
                .update({key: value})\
                .eq("guild_id", guild_id)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to update setting {key}: {e}")
    
    async def increment_query_count(self, guild_id: int):
        """Increments query count for rate limiting."""
        if not self.client: return
        try:
            # Use PostgreSQL increment
            self.client.rpc("increment_query_count", {"g_id": guild_id}).execute()
        except Exception as e:
            logger.error(f"Failed to increment query count: {e}")
    
    async def reset_query_count(self, guild_id: int):
        """Resets daily query count."""
        if not self.client: return
        try:
            self.client.table("servers")\
                .update({
                    "query_count_today": 0,
                    "last_reset": "now()"
                })\
                .eq("guild_id", guild_id)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to reset query count: {e}")
    
    async def get_all_alert_channels(self):
        """Legacy generic alert channels. Do not use for new dedicated routes."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, alert_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("alert_channel_id", "null")\
                .execute()
            
            return [(r['guild_id'], r['alert_channel_id']) for r in response.data]
        except Exception as e:
            logger.error(f"Failed to fetch alert channels: {e}")
            return []

    async def get_all_ask_channels(self):
        """/ask response channels."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, ask_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("ask_channel_id", "null")\
                .execute()
            return [(r['guild_id'], r['ask_channel_id']) for r in response.data]
        except Exception as e:
            logger.error(f"Failed to fetch ask channels: {e}")
            return []

    async def get_all_lag_hunter_channels(self):
        """Lag Hunter alert channels."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, lag_hunter_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("lag_hunter_channel_id", "null")\
                .execute()
            return [(r['guild_id'], r['lag_hunter_channel_id']) for r in response.data]
        except Exception as e:
            logger.error(f"Failed to fetch lag hunter channels: {e}")
            return []
    
    async def get_all_new_markets_channels(self):
        """Returns all enabled new markets channels with filters (Genesis firehose)."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, new_markets_channel_id, market_filters")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("new_markets_channel_id", "null")\
                .execute()
            
            return [(r['guild_id'], r['new_markets_channel_id'], r.get('market_filters')) for r in response.data]
        except Exception as e:
            error_text = str(e)
            logger.error(f"Failed to fetch new markets channels: {error_text}")
            if "new_markets_channel_id" in error_text or "market_filters" in error_text:
                logger.warning("New markets channel columns missing. Run the dedicated channel migrations.")
            return []
    

    async def get_all_geo_channels(self):
        """Returns all enabled dedicated Geo Sniper channels."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, geo_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("geo_channel_id", "null")\
                .execute()
            return [(r['guild_id'], r['geo_channel_id']) for r in response.data]
        except Exception as e:
            error_text = str(e)
            logger.error(f"Failed to fetch geo channels: {error_text}")
            if "geo_channel_id" in error_text:
                logger.warning("Geo channel column missing. Run DATABASE_MIGRATION_GEO_CHANNEL.sql.")
            return []

    async def get_all_copy_tracker_channels(self):
        """Returns all enabled copy tracker channels."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, copy_tracker_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("copy_tracker_channel_id", "null")\
                .execute()
            return [(r['guild_id'], r['copy_tracker_channel_id']) for r in response.data]
        except Exception as e:
            error_text = str(e)
            logger.error(f"Failed to fetch copy tracker channels: {error_text}")
            if "copy_tracker_channel_id" in error_text:
                logger.warning("Copy tracker column missing. Run DATABASE_MIGRATION_COPY_TRACKER.sql.")
            return []

    async def get_all_curated_channels(self):
        """Legacy curated channels. Do not use for new dedicated routes."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, curated_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("curated_channel_id", "null")\
                .execute()
            
            return [(r['guild_id'], r['curated_channel_id']) for r in response.data]
        except Exception as e:
            error_text = str(e)
            logger.error(f"Failed to fetch curated channels: {error_text}")
            
            if "curated_channel_id" in error_text:
                logger.warning(
                    "Curated channel column missing. Run DATABASE_MIGRATION_GENESIS.sql "
                    "to enable Genesis curated alerts."
                )
                return []
            return []

    async def get_all_curated_markets_channels(self):
        """Genesis curated markets channels."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, curated_markets_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("curated_markets_channel_id", "null")\
                .execute()
            return [(r['guild_id'], r['curated_markets_channel_id']) for r in response.data]
        except Exception as e:
            logger.error(f"Failed to fetch curated markets channels: {e}")
            return []

    async def get_all_arb_channels(self):
        """Arbitrage alert channels."""
        if not self.client: return []
        try:
            response = self.client.table("servers")\
                .select("guild_id, arb_channel_id")\
                .eq("enabled", True)\
                .eq("is_banned", False)\
                .not_.is_("arb_channel_id", "null")\
                .execute()
            return [(r['guild_id'], r['arb_channel_id']) for r in response.data]
        except Exception as e:
            logger.error(f"Failed to fetch arb channels: {e}")
            return []
    
    async def ban_server(self, guild_id: int, reason: str):
        """Bans a server."""
        if not self.client: return
        try:
            self.client.table("servers")\
                .update({
                    "is_banned": True,
                    "ban_reason": reason,
                    "banned_at": "now()"
                })\
                .eq("guild_id", guild_id)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to ban server: {e}")
    
    async def unban_server(self, guild_id: int):
        """Unbans a server."""
        if not self.client: return
        try:
            self.client.table("servers")\
                .update({
                    "is_banned": False,
                    "ban_reason": None,
                    "banned_at": None
                })\
                .eq("guild_id", guild_id)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to unban server: {e}")
    
    async def upgrade_server(self, guild_id: int, tier: str, max_queries: int):
        """Upgrades server tier."""
        if not self.client: return
        try:
            self.client.table("servers")\
                .update({
                    "tier": tier,
                    "max_queries_per_day": max_queries
                })\
                .eq("guild_id", guild_id)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to upgrade server: {e}")
    
    async def get_server_stats(self):
        """Returns global statistics."""
        if not self.client: return {}
        try:
            response = self.client.table("servers")\
                .select("tier, is_banned, enabled")\
                .execute()
            
            data = response.data
            return {
                "total_servers": len(data),
                "active_servers": len([s for s in data if s['enabled'] and not s['is_banned']]),
                "banned_servers": len([s for s in data if s['is_banned']]),
                "free_tier": len([s for s in data if s['tier'] == 'free']),
                "pro_tier": len([s for s in data if s['tier'] == 'pro']),
                "enterprise_tier": len([s for s in data if s['tier'] == 'enterprise'])
            }
        except Exception as e:
            logger.error(f"Failed to fetch stats: {e}")
            return {}
    
    # ===== GENESIS SCANNER PERSISTENCE =====
    
    async def get_seen_markets(self, since: 'datetime') -> list:
        """
        Returns list of seen market_ids since a given date.
        Used by Genesis Scanner to avoid restart spam.
        """
        if not self.client:
            return []
        try:
            response = self.client.table("seen_markets")\
                .select("market_id, event_slug")\
                .gte("seen_at", since.isoformat())\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            error_text = str(e)
            # If table doesn't exist, return empty (will be created on first save)
            if "seen_markets" in error_text or "does not exist" in error_text:
                logger.info("seen_markets table not found - run DATABASE_MIGRATION_GENESIS_V2.sql")
                return []
            logger.error(f"Failed to fetch seen markets: {e}")
            return []
    
    async def save_seen_market(self, market_id: str, event_slug: str):
        """
        Saves a market as seen (prevents re-alerting after restart).
        """
        if not self.client:
            return
        try:
            self.client.table("seen_markets").upsert({
                "market_id": market_id,
                "event_slug": event_slug,
                "seen_at": "now()"
            }, on_conflict="market_id").execute()
        except Exception as e:
            error_text = str(e)
            if "seen_markets" in error_text or "does not exist" in error_text:
                # Table doesn't exist yet - log once
                logger.debug(f"seen_markets table missing, market not persisted: {market_id}")
            else:
                logger.debug(f"Could not save seen market: {e}")
    
    async def cleanup_old_seen_markets(self, days_retention: int = 7):
        """
        Clean up old seen market records to prevent table bloat.
        """
        if not self.client:
            return
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
            
            self.client.table("seen_markets")\
                .delete()\
                .lt("seen_at", cutoff)\
                .execute()
            
            logger.debug(f"Cleaned up seen markets older than {days_retention} days")
        except Exception as e:
            logger.debug(f"Could not cleanup old seen markets: {e}")
    
    # ===== SERVER FILTER METHODS =====
    
    async def get_server_filters(self, guild_id: int, filter_type: str = "new_markets") -> list:
        """
        Get market category filters for a server.
        filter_type: 'new_markets' or 'lag_hunter'
        Returns list of category strings, or empty list if not set.
        """
        if not self.client:
            return []
        try:
            column = "market_filters" if filter_type == "new_markets" else "lag_hunter_filters"
            response = self.client.table("servers")\
                .select(column)\
                .eq("guild_id", guild_id)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                filters_str = response.data[0].get(column)
                if filters_str:
                    return [f.strip() for f in filters_str.split(',') if f.strip()]
            return []
        except Exception as e:
            logger.debug(f"Could not fetch filters for {guild_id}: {e}")
            return []
    
    async def update_server_filters(self, guild_id: int, categories: list, filter_type: str = "new_markets"):
        """
        Update market category filters for a server.
        filter_type: 'new_markets' or 'lag_hunter'
        categories: list of category strings, or empty list to clear.
        """
        if not self.client:
            return False
        try:
            column = "market_filters" if filter_type == "new_markets" else "lag_hunter_filters"
            filters_str = ','.join(categories) if categories else None
            
            self.client.table("servers")\
                .update({column: filters_str})\
                .eq("guild_id", guild_id)\
                .execute()
            
            return True
        except Exception as e:
            logger.error(f"Failed to update filters for {guild_id}: {e}")
            return False
    
    # ===== GENERIC QUERY METHODS (for MarketMappingService) =====
    
    async def fetch_all(self, query: str, *params):
        """
        Execute a raw SQL query and return all rows.
        Used by MarketMappingService for custom queries.
        """
        if not self.client:
            return []
        try:
            # Supabase doesn't support raw SQL directly, so we use RPC
            # For now, return empty - real implementation would need custom RPC functions
            logger.warning(f"fetch_all called but not fully implemented: {query[:50]}")
            return []
        except Exception as e:
            logger.error(f"fetch_all error: {e}")
            return []
    
    async def fetch_one(self, query: str, *params):
        """
        Execute a raw SQL query and return one row.
        Used by MarketMappingService for custom queries.
        """
        if not self.client:
            return None
        try:
            logger.warning(f"fetch_one called but not fully implemented: {query[:50]}")
            return None
        except Exception as e:
            logger.error(f"fetch_one error: {e}")
            return None
    
    async def execute(self, query: str, *params):
        """
        Execute a raw SQL query without returning results.
        Used by MarketMappingService for INSERT/UPDATE/DELETE.
        """
        if not self.client:
            return
        try:
            logger.warning(f"execute called but not fully implemented: {query[:50]}")
        except Exception as e:
            logger.error(f"execute error: {e}")

# Global Instance
db = Database()
