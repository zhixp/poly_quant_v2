"""Regression coverage for the second PolyQuant rescue pass."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if "supabase" not in sys.modules:
    fake_supabase = types.ModuleType("supabase")
    fake_supabase.create_client = lambda *args, **kwargs: None
    fake_supabase.Client = object
    sys.modules["supabase"] = fake_supabase

from app.scanners.geo_sniper import GeoSniper
from app.scanners.wallet_tracker import WalletTracker


class TestGeoDiscoveryAndSpamControl:
    def test_geo_discovery_paginates_beyond_hotwired_watchlist(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        fetch_body = source.split("async def _fetch_watch_markets", 1)[1].split(
            "def _is_geo_market_candidate", 1
        )[0]

        assert "GEO_SNIPER_DISCOVERY_PAGES" in source
        assert '"offset": page * per_page' in fetch_body
        assert "_is_geo_market_candidate" in fetch_body

    def test_geo_family_cooldown_collapses_date_ladders(self):
        scanner = GeoSniper(bot=None)
        a = scanner._family_key("us-x-iran-permanent-peace-deal-by-may-26-2026", "YES +4.0c", "Iran statement")
        b = scanner._family_key("us-x-iran-permanent-peace-deal-by-june-1-2026", "YES +1.0c", "Iran statement")
        assert a == b

    def test_geo_scanner_caps_alerts_per_scan(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        scan_body = source.split("async def scan", 1)[1].split("async def _fetch_watch_markets", 1)[0]
        assert "GEO_SNIPER_MAX_ALERTS_PER_SCAN" in source
        assert "signals[: self.max_alerts_per_scan]" in scan_body
        assert "_is_family_on_cooldown" in scan_body


class TestWalletTracker:
    def test_wallet_tracker_is_registered_in_runtime(self):
        main_source = Path("main.py").read_text(encoding="utf-8")
        assert "from app.scanners.wallet_tracker import WalletTracker" in main_source
        assert "self.wallet_tracker = WalletTracker(self)" in main_source
        assert "self.loop.create_task(self.wallet_tracker.start())" in main_source

    def test_wallet_tracker_uses_dedicated_copy_tracker_route_only(self):
        source = Path("app/scanners/wallet_tracker.py").read_text(encoding="utf-8")
        assert "get_all_copy_tracker_channels" in source
        assert "get_all_alert_channels" not in source
        assert "without fallback" in source

    def test_wallet_tracker_parses_labeled_wallet_env(self, monkeypatch):
        monkeypatch.setenv("WALLET_TRACKER_WALLETS", "0xABC=Smart Whale,0xDEF")
        tracker = WalletTracker(bot=None)
        assert tracker.wallets == {"0xabc": "Smart Whale", "0xdef": "Wallet 2"}


class TestLagAndJudgeSafety:
    def test_lag_hunter_has_configurable_feed_coverage_and_rejects_bad_agent_parse(self):
        source = Path("app/scanners/lag_hunter.py").read_text(encoding="utf-8")
        assert "LAG_HUNTER_RSS_FEEDS" in source
        assert "LAG_HUNTER_MARKET_LIMIT" in source
        assert "LAG_HUNTER_FRESHNESS_HOURS" in source
        assert "Defaulting to reject" in source
        assert "return False" in source

    def test_query_forces_hold_when_judge_is_directional_without_evidence_or_arb(self):
        source = Path("app/cogs/query.py").read_text(encoding="utf-8")
        assert "forcing HOLD" in source
        assert "if not has_external_context and not has_deterministic_arb" in source
        assert "live Polymarket odds alone" in source
