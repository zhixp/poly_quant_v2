"""
Metrics and Monitoring Module
Lightweight counters for production observability.
"""
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("Metrics")


class MetricsCollector:
    """
    Simple in-memory metrics collector for production monitoring.
    Tracks key events and provides summary statistics.
    """
    
    def __init__(self):
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = {}
        self.last_events: Dict[str, datetime] = {}
        self.start_time = datetime.now()
    
    def increment(self, metric_name: str, value: int = 1):
        """Increment a counter metric."""
        self.counters[metric_name] += value
        self.last_events[metric_name] = datetime.now()
    
    def set_gauge(self, metric_name: str, value: float):
        """Set a gauge metric to a specific value."""
        self.gauges[metric_name] = value
        self.last_events[metric_name] = datetime.now()
    
    def get_counter(self, metric_name: str) -> int:
        """Get current value of a counter."""
        return self.counters.get(metric_name, 0)
    
    def get_gauge(self, metric_name: str) -> float:
        """Get current value of a gauge."""
        return self.gauges.get(metric_name, 0.0)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all metrics.
        Returns dict suitable for logging or display.
        """
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            'uptime_seconds': uptime,
            'uptime_hours': uptime / 3600,
            'counters': dict(self.counters),
            'gauges': dict(self.gauges),
            'last_events': {
                k: v.isoformat() for k, v in self.last_events.items()
            }
        }
    
    def log_summary(self):
        """Log current metrics summary."""
        summary = self.get_summary()
        logger.info(f"📊 Metrics Summary (uptime: {summary['uptime_hours']:.1f}h)")
        logger.info(f"  Counters: {summary['counters']}")
        logger.info(f"  Gauges: {summary['gauges']}")
    
    def reset(self):
        """Reset all metrics (useful for testing)."""
        self.counters.clear()
        self.gauges.clear()
        self.last_events.clear()
        self.start_time = datetime.now()


# Global metrics instance
metrics = MetricsCollector()


# Metric name constants for consistency
class MetricNames:
    """Standard metric names used across the application."""
    
    # /ask command metrics
    ASK_REQUESTS = "ask.requests.total"
    ASK_CACHE_HITS = "ask.cache.hits"
    ASK_CACHE_MISSES = "ask.cache.misses"
    ASK_ERRORS = "ask.errors.total"
    ASK_JSON_PARSE_FAILURES = "ask.json_parse_failures"
    
    # LagHunter metrics
    LAG_HUNTER_SCANS = "lag_hunter.scans.total"
    LAG_HUNTER_MATCHES = "lag_hunter.matches.total"
    LAG_HUNTER_ALERTS = "lag_hunter.alerts.total"
    LAG_HUNTER_ERRORS = "lag_hunter.errors.total"
    LAG_HUNTER_ZERO_ALERT_STREAK = "lag_hunter.zero_alert_streak"  # Gauge
    
    # GenesisScanner metrics
    GENESIS_SCANS = "genesis.scans.total"
    GENESIS_MARKETS_DISCOVERED = "genesis.markets.discovered"
    GENESIS_MARKETS_ANALYZED = "genesis.markets.analyzed"
    GENESIS_CURATED_ALERTS = "genesis.curated.alerts"
    GENESIS_ERRORS = "genesis.errors.total"
    
    # Market data metrics
    MARKET_DATA_FETCHES = "market_data.fetches.total"
    MARKET_DATA_ERRORS = "market_data.errors.total"
    VEGAS_ODDS_FETCHES = "vegas_odds.fetches.total"
    VEGAS_ODDS_ERRORS = "vegas_odds.errors.total"
    
    # Database metrics
    DB_QUERIES = "db.queries.total"
    DB_ERRORS = "db.errors.total"
    
    # Rate limiting
    RATE_LIMIT_HITS = "rate_limit.hits.total"


def track_request(metric_name: str):
    """Decorator to track function calls as metrics."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            metrics.increment(metric_name)
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                metrics.increment(f"{metric_name}.errors")
                raise
        
        def sync_wrapper(*args, **kwargs):
            metrics.increment(metric_name)
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                metrics.increment(f"{metric_name}.errors")
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

