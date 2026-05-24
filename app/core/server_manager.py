"""
Server Manager: Multi-Tenant Configuration Layer
Handles server permissions, settings, and caching to avoid DB hammering.
"""
import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from app.core.database import db

logger = logging.getLogger("ServerManager")

class ServerConfig:
    """Represents a single server's configuration."""
    def __init__(self, data: dict):
        from datetime import timezone
        from dateutil import parser
        
        self.guild_id = data.get('guild_id')
        self.alert_channel_id = data.get('alert_channel_id')
        self.query_channel_id = data.get('query_channel_id')
        self.ask_channel_id = data.get('ask_channel_id')
        self.lag_hunter_channel_id = data.get('lag_hunter_channel_id')
        self.new_markets_channel_id = data.get('new_markets_channel_id')  # Genesis firehose
        self.curated_channel_id = data.get('curated_channel_id')  # Genesis curated
        self.curated_markets_channel_id = data.get('curated_markets_channel_id')
        self.arb_channel_id = data.get('arb_channel_id')
        self.copy_tracker_channel_id = data.get('copy_tracker_channel_id')  # Wallet/copy-trade alerts
        self.geo_channel_id = data.get('geo_channel_id')  # Geo Sniper mispricing alerts only
        self.market_filters = data.get('market_filters')  # Comma-separated categories or None
        self.tier = data.get('tier', 'free')  # free, pro, enterprise
        self.is_banned = data.get('is_banned', False)
        self.enabled = data.get('enabled', True)
        self.max_queries_per_day = data.get('max_queries_per_day', 50)
        self.query_count_today = data.get('query_count_today', 0)
        
        # Parse last_reset (comes as ISO string from Supabase)
        last_reset_raw = data.get('last_reset')
        if isinstance(last_reset_raw, str):
            try:
                # Parse ISO format string to datetime
                parsed = parser.isoparse(last_reset_raw)
                # Ensure timezone-aware
                if parsed.tzinfo is None:
                    self.last_reset = parsed.replace(tzinfo=timezone.utc)
                else:
                    self.last_reset = parsed
            except:
                self.last_reset = datetime.now(timezone.utc)
        elif isinstance(last_reset_raw, datetime):
            # Already datetime, ensure timezone-aware
            if last_reset_raw.tzinfo is None:
                self.last_reset = last_reset_raw.replace(tzinfo=timezone.utc)
            else:
                self.last_reset = last_reset_raw
        else:
            self.last_reset = datetime.now(timezone.utc)

class ServerManager:
    """
    Multi-Tenant Configuration Manager with Smart Caching.
    Cache expires every 5 minutes to avoid stale data.
    """
    def __init__(self):
        self.cache: Dict[int, ServerConfig] = {}
        self.cache_expires: Dict[int, datetime] = {}
        self.cache_ttl = timedelta(minutes=5)
        self.global_banned_guilds = set()
        
    async def get_server_config(self, guild_id: int) -> Optional[ServerConfig]:
        """
        Fetches server config with intelligent caching.
        Returns None if server is not registered or banned.
        """
        # Check if banned (global check)
        if guild_id in self.global_banned_guilds:
            return None
        
        # Check cache first
        now = datetime.now()
        if guild_id in self.cache:
            if now < self.cache_expires.get(guild_id, datetime.min):
                return self.cache[guild_id]
        
        # Cache miss or expired - fetch from DB
        config_data = await db.get_server_config(guild_id)
        if not config_data:
            return None
        
        config = ServerConfig(config_data)
        
        # Update cache
        self.cache[guild_id] = config
        self.cache_expires[guild_id] = now + self.cache_ttl
        
        # Update banned list
        if config.is_banned:
            self.global_banned_guilds.add(guild_id)
            return None
        
        return config
    
    async def register_server(self, guild_id: int, guild_name: str) -> bool:
        """Registers a new server (called on bot join)."""
        try:
            await db.register_server(guild_id, guild_name)
            logger.info(f"✅ Registered new server: {guild_name} ({guild_id})")
            # Invalidate cache
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to register server {guild_id}: {e}")
            return False
    
    async def set_alert_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the lag alert channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'alert_channel_id', channel_id)
            # Invalidate cache
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set alert channel: {e}")
            return False
    
    async def set_query_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the query channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'query_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set query channel: {e}")
            return False

    async def set_ask_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the dedicated /ask response channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'ask_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set ask channel: {e}")
            return False

    async def set_lag_hunter_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the dedicated Lag Hunter alert channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'lag_hunter_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set lag hunter channel: {e}")
            return False
    
    async def toggle_server(self, guild_id: int, enabled: bool) -> bool:
        """Enable/disable bot for a server."""
        try:
            await db.update_server_setting(guild_id, 'enabled', enabled)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to toggle server: {e}")
            return False
    
    async def increment_query_count(self, guild_id: int) -> bool:
        """Increments query count and checks rate limits."""
        config = await self.get_server_config(guild_id)
        if not config:
            return False
        
        # Check if we need to reset daily counter (use timezone-aware comparison)
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        # Ensure both datetimes are comparable
        if isinstance(config.last_reset, datetime):
            if config.last_reset.tzinfo is None:
                last_reset = config.last_reset.replace(tzinfo=timezone.utc)
            else:
                last_reset = config.last_reset
            
            if (now - last_reset).days >= 1:
                await db.reset_query_count(guild_id)
                config.query_count_today = 0
        
        # Check rate limit
        if config.query_count_today >= config.max_queries_per_day:
            logger.warning(f"Rate limit exceeded for guild {guild_id}")
            return False
        
        await db.increment_query_count(guild_id)
        return True
    
    async def get_all_alert_channels(self) -> List[tuple]:
        """
        Legacy generic alert channels. Do not use for new dedicated routes.
        """
        try:
            return await db.get_all_alert_channels()
        except Exception as e:
            logger.error(f"Failed to fetch alert channels: {e}")
            return []

    async def get_all_ask_channels(self) -> List[tuple]:
        """Returns list of (guild_id, channel_id) for /ask responses."""
        try:
            return await db.get_all_ask_channels()
        except Exception as e:
            logger.error(f"Failed to fetch ask channels: {e}")
            return []

    async def get_all_lag_hunter_channels(self) -> List[tuple]:
        """Returns list of (guild_id, channel_id) for Lag Hunter only."""
        try:
            return await db.get_all_lag_hunter_channels()
        except Exception as e:
            logger.error(f"Failed to fetch lag hunter channels: {e}")
            return []
    
    async def get_all_new_markets_channels(self) -> List[tuple]:
        """
        Returns list of (guild_id, channel_id) for Genesis Scanner firehose.
        """
        try:
            return await db.get_all_new_markets_channels()
        except Exception as e:
            logger.error(f"Failed to fetch new markets channels: {e}")
            return []
    
    async def get_all_curated_channels(self) -> List[tuple]:
        """
        Returns list of (guild_id, channel_id) for Genesis Scanner curated alerts.
        """
        try:
            return await db.get_all_curated_channels()
        except Exception as e:
            logger.error(f"Failed to fetch curated channels: {e}")
            return []

    async def get_all_curated_markets_channels(self) -> List[tuple]:
        """Returns list of (guild_id, channel_id) for Genesis curated market alerts."""
        try:
            return await db.get_all_curated_markets_channels()
        except Exception as e:
            logger.error(f"Failed to fetch curated markets channels: {e}")
            return []

    async def get_all_arb_channels(self) -> List[tuple]:
        """Returns list of (guild_id, channel_id) for arbitrage alerts only."""
        try:
            return await db.get_all_arb_channels()
        except Exception as e:
            logger.error(f"Failed to fetch arb channels: {e}")
            return []
    
    async def set_new_markets_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the Genesis Scanner firehose channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'new_markets_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set new markets channel: {e}")
            return False
    
    async def set_curated_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the Genesis Scanner curated channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'curated_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set curated channel: {e}")
            return False

    async def set_curated_markets_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the Genesis Scanner curated markets channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'curated_markets_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set curated markets channel: {e}")
            return False

    async def set_arb_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the dedicated arbitrage alert channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'arb_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set arb channel: {e}")
            return False
    
    async def get_all_geo_channels(self) -> List[tuple]:
        """Returns list of (guild_id, channel_id) for Geo Sniper mispricing alerts."""
        try:
            return await db.get_all_geo_channels()
        except Exception as e:
            logger.error(f"Failed to fetch geo channels: {e}")
            return []

    async def set_geo_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the dedicated Geo Sniper channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'geo_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set geo channel: {e}")
            return False

    async def get_all_copy_tracker_channels(self) -> List[tuple]:
        """Returns list of (guild_id, channel_id) for copy tracker alerts."""
        try:
            return await db.get_all_copy_tracker_channels()
        except Exception as e:
            logger.error(f"Failed to fetch copy tracker channels: {e}")
            return []

    async def set_copy_tracker_channel(self, guild_id: int, channel_id: int) -> bool:
        """Sets the copy tracker alert channel for a server."""
        try:
            await db.update_server_setting(guild_id, 'copy_tracker_channel_id', channel_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set copy tracker channel: {e}")
            return False

    async def set_market_filters(self, guild_id: int, filters: str) -> bool:
        """
        Sets market category filters for Genesis Scanner.
        filters: Comma-separated categories (e.g., 'Politics,Crypto,Sports') or None for all
        """
        try:
            await db.update_server_setting(guild_id, 'market_filters', filters)
            if guild_id in self.cache:
                del self.cache[guild_id]
            return True
        except Exception as e:
            logger.error(f"Failed to set market filters: {e}")
            return False
    
    # ===== ADMIN FUNCTIONS =====
    
    async def ban_server(self, guild_id: int, reason: str = "Violation of ToS") -> bool:
        """Bans a server (admin only)."""
        try:
            await db.ban_server(guild_id, reason)
            self.global_banned_guilds.add(guild_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            logger.warning(f"⛔ Banned server {guild_id}: {reason}")
            return True
        except Exception as e:
            logger.error(f"Failed to ban server: {e}")
            return False
    
    async def unban_server(self, guild_id: int) -> bool:
        """Unbans a server (admin only)."""
        try:
            await db.unban_server(guild_id)
            self.global_banned_guilds.discard(guild_id)
            if guild_id in self.cache:
                del self.cache[guild_id]
            logger.info(f"✅ Unbanned server {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to unban server: {e}")
            return False
    
    async def upgrade_server(self, guild_id: int, tier: str) -> bool:
        """Upgrades a server tier (admin only)."""
        try:
            tier_limits = {
                'free': 50,
                'pro': 500,
                'enterprise': 99999
            }
            await db.upgrade_server(guild_id, tier, tier_limits.get(tier, 50))
            if guild_id in self.cache:
                del self.cache[guild_id]
            logger.info(f"⬆️ Upgraded server {guild_id} to {tier}")
            return True
        except Exception as e:
            logger.error(f"Failed to upgrade server: {e}")
            return False
    
    async def get_server_stats(self) -> dict:
        """Returns global statistics (admin only)."""
        try:
            return await db.get_server_stats()
        except Exception as e:
            logger.error(f"Failed to fetch stats: {e}")
            return {}

# Global instance
server_manager = ServerManager()


