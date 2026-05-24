"""Regression tests for current PolyQuant rescue fixes."""
import sys
from pathlib import Path
from decimal import Decimal

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.market_data import MarketResolver
from app.core.bookmaker_client import BookmakerOdds, OddsConverter, ExecutableQuote


class TestPolymarketPriceParsing:
    def test_binary_yes_no_prices_follow_gamma_order(self):
        resolver = MarketResolver()
        market = {
            "question": "US x Iran permanent peace deal by May 31, 2026?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.365", "0.635"]',
            "volume": "45421923",
        }

        assert resolver._extract_yes_price(market) == pytest.approx(0.365)
        formatted = resolver._format_binary_market_data(market)
        assert "YES: $0.365 (36%)" in formatted
        assert "NO:  $0.635 (64%)" in formatted

    def test_binary_prices_work_when_outcome_order_is_reversed(self):
        resolver = MarketResolver()
        market = {
            "question": "Test market",
            "outcomes": '["No", "Yes"]',
            "outcomePrices": '["0.22", "0.78"]',
            "volume": "1000",
        }

        assert resolver._extract_yes_price(market) == pytest.approx(0.78)
        formatted = resolver._format_binary_market_data(market)
        assert "YES: $0.780 (78%)" in formatted
        assert "NO:  $0.220 (22%)" in formatted

    def test_event_url_with_child_market_preserves_child_slug(self):
        resolver = MarketResolver()
        parsed = resolver._parse_polymarket_url(
            "https://polymarket.com/event/us-x-iran-permanent-peace-deal-by/us-x-iran-permanent-peace-deal-by-may-31"
        )
        assert parsed == {
            "type": "event_market",
            "event_slug": "us-x-iran-permanent-peace-deal-by",
            "market_slug": "us-x-iran-permanent-peace-deal-by-may-31",
        }

    def test_missing_outcome_labels_fall_back_to_yes_first(self):
        resolver = MarketResolver()
        market = {
            "question": "Missing labels",
            "outcomePrices": '["0.26", "0.74"]',
        }

        assert resolver._extract_yes_price(market) == pytest.approx(0.26)


class TestCrossVenueComparison:
    def test_calculate_two_way_arbitrage_profit_when_yes_no_sum_below_one(self):
        converter = OddsConverter()
        arb = converter.calculate_prediction_market_arb(
            polymarket_yes_price=0.36,
            external_no_price=0.55,
            fees=0.0,
        )
        assert arb["is_arbitrage"] is True
        assert arb["total_cost"] == pytest.approx(0.91)
        assert arb["guaranteed_profit_pct"] == pytest.approx(9.0)

    def test_compares_correct_outcome_names_with_aliases(self):
        book = BookmakerOdds(
            venue="kalshi",
            market_id="KXIRANPEACE-26MAY31",
            market_name="US and Iran peace deal by May 31?",
            outcomes={"yes": 0.38, "no": 0.62},
            implied_probs={"yes": 0.38, "no": 0.62},
            timestamp="live",
            raw_data={},
        )
        converter = OddsConverter()
        result = converter.compare_prediction_market_prices(
            polymarket_prices={"Yes": 0.365, "No": 0.635},
            external_prices=book.implied_probs,
            fees=0.0,
        )
        assert result["matched_outcomes"]["Yes"]["external_price"] == pytest.approx(0.38)
        assert result["matched_outcomes"]["No"]["external_price"] == pytest.approx(0.62)

    def test_bookmaker_client_does_not_emit_mock_pinnacle_odds(self):
        source = Path("app/core/bookmaker_client.py").read_text(encoding="utf-8")
        pinnacle_body = source.split("async def _fetch_pinnacle", 1)[1].split(
            "async def _fetch_betfair", 1
        )[0]
        assert "mock_data" not in pinnacle_body
        assert "return None" in pinnacle_body

    def test_polymarket_token_mapping_handles_reversed_labels(self):
        tokens = OddsConverter.polymarket_tokens_by_outcome(
            outcomes=["No", "Yes"],
            token_ids=["NO_TOKEN", "YES_TOKEN"],
        )
        assert tokens["yes"] == "YES_TOKEN"
        assert tokens["no"] == "NO_TOKEN"

    def test_polymarket_best_ask_selects_lowest_valid_executable_ask(self):
        quote = OddsConverter.best_polymarket_ask({
            "asks": [
                {"price": "0.42", "size": "0"},
                {"price": "0.39", "size": "12"},
                {"price": "0.41", "size": "25"},
            ]
        })
        assert quote.price == Decimal("0.39")
        assert quote.size == Decimal("12")

    def test_missing_polymarket_ask_returns_watch_not_alert(self):
        result = OddsConverter.calculate_equal_payout_arb(
            yes_ask=None,
            no_ask=ExecutableQuote(price=Decimal("0.55"), size=Decimal("100")),
            min_profit=Decimal("0.01"),
            min_size=Decimal("10"),
        )
        assert result["status"] == "WATCH"

    def test_missing_kalshi_implied_ask_when_opposite_bid_missing(self):
        asks = OddsConverter.kalshi_implied_asks({
            "orderbook_fp": {
                "yes_dollars": [["0.40", "50"]],
                "no_dollars": [],
            }
        })
        assert asks["Yes"] is None
        assert asks["No"].price == Decimal("0.60")

    def test_profitable_exact_equal_payout_arb(self):
        result = OddsConverter.calculate_equal_payout_arb(
            yes_ask=ExecutableQuote(price=Decimal("0.36"), size=Decimal("100")),
            no_ask=ExecutableQuote(price=Decimal("0.55"), size=Decimal("80")),
            fees_per_unit=Decimal("0.015"),
            slippage_buffer_per_unit=Decimal("0.005"),
            min_profit=Decimal("0.01"),
            min_size=Decimal("10"),
        )
        assert result["status"] == "ARB_ALERT"
        assert result["cost_per_unit"] == Decimal("0.930")
        assert result["profit_per_unit"] == Decimal("0.070")
        assert result["max_units"] == Decimal("80")
        assert result["total_profit"] == Decimal("5.600")



class TestGeoSniperRouting:
    def test_geo_sniper_uses_dedicated_geo_channel_not_generic_alert_channel(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        send_alert_body = source.split("async def _send_alert", 1)[1].split(
            "async def test_once", 1
        )[0]
        assert "get_all_geo_channels" in send_alert_body
        assert "get_all_alert_channels" not in send_alert_body
        assert "get_all_curated_channels" not in send_alert_body
        assert "get_all_new_markets_channels" not in send_alert_body
        assert "get_all_lag_hunter_channels" not in send_alert_body
        assert "get_all_arb_channels" not in send_alert_body

    def test_geo_sniper_missing_channel_config_warns_and_skips_without_fallback(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        send_alert_body = source.split("async def _send_alert", 1)[1].split(
            "async def test_once", 1
        )[0]

        assert "if not alert_channels:" in send_alert_body
        assert "logger.warning" in send_alert_body
        assert "geo_channel_id" in send_alert_body
        assert "without fallback" in send_alert_body
        assert "return False" in send_alert_body

    def test_geo_sniper_manual_test_uses_same_dedicated_sender(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        test_once_body = source.split("async def test_once", 1)[1].split(
            "def _prices", 1
        )[0]

        assert "self._send_alert(sample)" in test_once_body
        assert "get_all_alert_channels" not in test_once_body

    def test_setup_exposes_geo_channel_action(self):
        source = Path("app/cogs/setup.py").read_text(encoding="utf-8")
        assert 'value="geo_channel"' in source
        assert "set_geo_channel" in source

    def test_truth_social_and_x_rss_bridge_are_supported_sources(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        assert "truthsocial.com/@realDonaldTrump.rss" in source
        assert "GEO_SNIPER_X_RSS_FEEDS" in source

    def test_x_bridge_is_disabled_by_default_until_grok_integration(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        config_body = source.split("def _configured_rss_feeds", 1)[1].split(
            "async def _analyze_market", 1
        )[0]

        assert "GEO_SNIPER_ENABLE_X_BRIDGE" in config_body
        assert 'os.getenv("GEO_SNIPER_ENABLE_X_BRIDGE", "false")' in config_body
        assert "GEO_SNIPER_X_RSS_FEEDS configured but ignored" in config_body
        assert "return feeds" in config_body

    def test_geo_sniper_does_not_treat_fokus_as_us_geo_keyword(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        keyword_body = source.split("def _has_geo_keyword", 1)[1].split(
            "def _has_geo_confirmation_term", 1
        )[0]
        broad_watch_body = source.split("Add high-volume active geopolitical markets", 1)[1].split(
            "return markets", 1
        )[0]

        assert "tokens = set" in keyword_body
        assert 'normalized in {"us", "u.s."}' in keyword_body
        assert '"us" in tokens' in keyword_body
        assert "normalized in tokens" in keyword_body
        assert "k in question" not in broad_watch_body

    def test_geo_sniper_excludes_esports_from_broad_watchlist(self):
        source = Path("app/scanners/geo_sniper.py").read_text(encoding="utf-8")
        exclusion_body = source.split("def _is_non_geo_market", 1)[1].split(
            "def _has_geo_keyword", 1
        )[0]
        broad_watch_body = source.split("Add high-volume active geopolitical markets", 1)[1].split(
            "return markets", 1
        )[0]

        assert "NON_GEO_CATEGORIES" in source
        assert "esports" in source
        assert "counter-strike" in exclusion_body
        assert "valorant" in exclusion_body
        assert "map winner" in exclusion_body
        assert "self._is_non_geo_market(market)" in broad_watch_body


class TestGenesisDedicatedRouting:
    def test_genesis_uses_dedicated_new_and_curated_market_channels(self):
        source = Path("app/scanners/genesis_scanner.py").read_text(encoding="utf-8")
        scan_body = source.split("async def scan", 1)[1].split("def _group_markets_by_event", 1)[0]

        assert "get_all_new_markets_channels" in scan_body
        assert "get_all_curated_markets_channels" in scan_body
        assert "get_all_curated_channels" not in scan_body
        assert "get_all_alert_channels" not in scan_body

    def test_genesis_curated_alert_skips_and_warns_without_dedicated_channel(self):
        source = Path("app/scanners/genesis_scanner.py").read_text(encoding="utf-8")
        curated_body = source.split("async def _post_to_curated", 1)[1].split(
            "def _extract_outcome_name", 1
        )[0]

        assert "if not curated_channels:" in curated_body
        assert "curated_markets_channel_id" in curated_body
        assert "logger.warning" in curated_body


class TestLagStyleDedicatedRouting:
    def test_lag_hunter_uses_dedicated_lag_hunter_channel_only(self):
        source = Path("app/scanners/lag_hunter.py").read_text(encoding="utf-8")
        alert_body = source.split("async def alert_discord", 1)[1].split(
            "async def _fetch_vegas_for_alert", 1
        )[0]

        assert "get_all_lag_hunter_channels" in alert_body
        assert "get_all_alert_channels" not in alert_body
        assert "lag_hunter_channel_id" in alert_body
        assert "logger.warning" in alert_body

    def test_inefficiency_scanner_uses_dedicated_lag_hunter_channel_only(self):
        source = Path("app/scanners/inefficiency_scanner.py").read_text(encoding="utf-8")
        broadcast_body = source.split("async def _broadcast_embed", 1)[1].split(
            "def _extract_yes_price", 1
        )[0]

        assert "get_all_lag_hunter_channels" in broadcast_body
        assert "get_all_alert_channels" not in broadcast_body
        assert "lag_hunter_channel_id" in broadcast_body
        assert "logger.warning" in broadcast_body

    def test_basket_scanner_uses_dedicated_lag_hunter_channel_only(self):
        source = Path("app/scanners/basket_scanner.py").read_text(encoding="utf-8")
        broadcast_body = source.split("async def _broadcast_alert", 1)[1].split(
            "def _extract_prices", 1
        )[0]

        assert "get_all_lag_hunter_channels" in broadcast_body
        assert "get_all_alert_channels" not in broadcast_body
        assert "lag_hunter_channel_id" in broadcast_body
        assert "logger.warning" in broadcast_body


class TestRuntimeSafety:
    def test_main_guards_background_tasks_against_duplicate_on_ready(self):
        source = Path("main.py").read_text(encoding="utf-8")
        assert "_background_tasks_started" in source
        assert "skipping duplicate startup" in source

    def test_legacy_prefix_ask_redirects_before_old_analysis_path(self):
        source = Path("main.py").read_text(encoding="utf-8")
        prefix_body = source.split("@bot.command()\nasync def ask", 1)[1].split("@bot.event", 1)[0]
        redirect_index = prefix_body.index("`!ask` is disabled")
        return_index = prefix_body.index("return")
        old_search_index = prefix_body.index("bot.router.deep_search")
        assert redirect_index < return_index < old_search_index


class TestScannerExtractionSafety:
    def test_inefficiency_scanner_does_not_use_max_price_as_yes(self):
        source = Path("app/scanners/inefficiency_scanner.py").read_text(encoding="utf-8")
        extract_body = source.split("def _extract_yes_price", 1)[1]
        assert "return max(cleaned)" not in extract_body
        assert "yes_index = 0" in extract_body
        assert "json.loads" in extract_body

    def test_basket_scanner_parses_json_string_prices_and_outcomes(self):
        source = Path("app/scanners/basket_scanner.py").read_text(encoding="utf-8")
        assert "def _json_list" in source
        assert "json.loads" in source
        assert 'self._json_list(market.get("outcomePrices"))' in source
        assert 'self._json_list(market.get("outcomes"))' in source


class TestExactMappingSafety:
    def test_no_mapping_is_not_exact_active(self):
        source = Path("app/core/market_mapping.py").read_text(encoding="utf-8")
        assert "if not mapping or not market_slug:" in source
        assert "return False" in source

    def test_fuzzy_candidate_mapping_is_excluded_from_live_arb(self):
        source = Path("app/core/market_mapping.py").read_text(encoding="utf-8")
        exact_body = source.split("def is_exact_active_mapping", 1)[1]
        assert 'mapping.status != "active"' in exact_body
        assert "return False" in exact_body

    def test_exact_market_only_lookup_does_not_allow_event_level_fallback(self):
        source = Path("app/core/market_mapping.py").read_text(encoding="utf-8")
        assert "exact_market_only" in source
        assert "and not exact_market_only" in source

    def test_query_arb_context_uses_exact_active_kalshi_mapping_only(self):
        source = Path("app/cogs/query.py").read_text(encoding="utf-8")
        assert "exact_market_only=bool(market_slug)" in source
        assert "is_exact_active_mapping" in source
        assert "check_polymarket_kalshi_arb" in source
        assert "No fuzzy mappings or midpoint/last prices" in source
        assert "DETERMINISTIC ARBITRAGE CONTEXT (AUTHORITATIVE" in source
        assert "Fuzzy matching used: false" in source
        assert "Do not claim executable arbitrage unless status is" in source


class TestAskHallucinationGuardrails:
    def test_query_injects_answer_guardrails_before_agent_council(self):
        source = Path("app/cogs/query.py").read_text(encoding="utf-8")
        assert "def _build_answer_guardrails" in source
        assert "Live Polymarket odds are prices, not proof" in source
        assert "YES means the exact market question resolves true" in source
        assert "final_verdict must be HOLD" in source
        assert "Sources are limited to the data shown above" in source
        assert "Data verified across multiple sources" not in source

        ask_body = source.split("async def ask", 1)[1].split("# 5. The Council Deliberates", 1)[0]
        assert "answer_guardrails = self._build_answer_guardrails" in ask_body
        assert "context_parts = [answer_guardrails]" in ask_body

    def test_judge_prompt_forbids_price_only_directional_claims(self):
        source = Path("app/Prompts/judge.py").read_text(encoding="utf-8")
        assert "Live market prices are not evidence" in source
        assert "final_verdict must be HOLD" in source
        assert "NO means the exact market question resolves false" in source
        assert "Do not reinterpret NO as a different team" in source
        assert "DO NOT invent match scores" in source


class TestRuntimeIdentityDiagnostics:
    def test_admin_identity_command_exposes_runtime_fingerprint_without_secrets(self):
        source = Path("app/cogs/admin.py").read_text(encoding="utf-8")
        assert '@app_commands.command(name="identity"' in source
        assert "POLYQUANT RUNTIME IDENTITY" in source
        assert "Interaction application" in source
        assert "Git commit" in source
        assert "Git remote" in source
        assert "sys.executable" in source
        assert "os.getcwd()" in source
        identity_body = source.split("async def identity", 1)[1].split(
            '@app_commands.command(name="debug_config"', 1
        )[0]
        assert "DISCORD_TOKEN" not in identity_body
        assert "SUPABASE_KEY" not in identity_body
        assert "GEMINI_KEYS" not in identity_body


class TestArbAlertRoutingGuardrails:
    def test_deterministic_arb_checker_has_no_discord_send_path(self):
        source = Path("app/core/bookmaker_client.py").read_text(encoding="utf-8")
        checker_body = source.split("async def check_polymarket_kalshi_arb", 1)[1].split(
            "async def _fetch_pinnacle", 1
        )[0]

        assert "channel.send" not in checker_body
        assert ".send(embed" not in checker_body
        assert "get_all_alert_channels" not in checker_body
        assert "get_all_arb_channels" not in checker_body

    def test_query_arb_context_is_not_a_live_discord_arb_alert_path(self):
        source = Path("app/cogs/query.py").read_text(encoding="utf-8")
        arb_context_body = source.split("def _format_arb_check", 1)[1].split(
            "@app_commands.command", 1
        )[0]

        assert "DETERMINISTIC ARBITRAGE CONTEXT" in arb_context_body
        assert "channel.send" not in arb_context_body
        assert ".send(embed" not in arb_context_body
        assert "get_all_alert_channels" not in arb_context_body
        assert "get_all_arb_channels" not in arb_context_body

    def test_any_future_live_arb_sender_must_use_dedicated_arb_channels(self):
        arb_related_sources = []
        for path in Path("app").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "ARB_ALERT" in source or "check_polymarket_kalshi_arb" in source:
                arb_related_sources.append((path, source))

        assert arb_related_sources
        for path, source in arb_related_sources:
            assert "get_all_alert_channels" not in source, f"{path} uses generic alert channels"
            sends_discord_alert = "channel.send" in source or ".send(embed" in source
            if sends_discord_alert:
                assert "get_all_arb_channels" in source, f"{path} sends arb alerts without arb_channel_id routing"


class TestDedicatedChannelPrimitives:
    def test_schema_and_migration_define_dedicated_channel_columns(self):
        schema = Path("database_schema.sql").read_text(encoding="utf-8")
        migration = Path("DATABASE_MIGRATION_DEDICATED_CHANNELS.sql").read_text(encoding="utf-8")
        for column in [
            "ask_channel_id",
            "lag_hunter_channel_id",
            "new_markets_channel_id",
            "curated_markets_channel_id",
            "arb_channel_id",
            "geo_channel_id",
            "copy_tracker_channel_id",
        ]:
            assert column in schema
            assert column in migration or column in {"new_markets_channel_id", "geo_channel_id", "copy_tracker_channel_id"}
        assert "ADD COLUMN IF NOT EXISTS arb_channel_id" in migration

    def test_database_exposes_dedicated_channel_getters_without_alert_fallback(self):
        source = Path("app/core/database.py").read_text(encoding="utf-8")
        for getter in [
            "get_all_ask_channels",
            "get_all_lag_hunter_channels",
            "get_all_new_markets_channels",
            "get_all_curated_markets_channels",
            "get_all_arb_channels",
            "get_all_geo_channels",
            "get_all_copy_tracker_channels",
        ]:
            assert f"async def {getter}" in source

        new_markets_body = source.split("async def get_all_new_markets_channels", 1)[1].split(
            "async def get_all_geo_channels", 1
        )[0]
        assert "get_all_alert_channels" not in new_markets_body
        assert "Falling back to alert channels" not in new_markets_body

    def test_server_manager_exposes_dedicated_channel_setters_and_getters(self):
        source = Path("app/core/server_manager.py").read_text(encoding="utf-8")
        for name in [
            "ask",
            "lag_hunter",
            "new_markets",
            "curated_markets",
            "arb",
            "geo",
            "copy_tracker",
        ]:
            assert f"{name}_channel_id" in source

        for method in [
            "set_ask_channel",
            "set_lag_hunter_channel",
            "set_new_markets_channel",
            "set_curated_markets_channel",
            "set_arb_channel",
            "set_geo_channel",
            "set_copy_tracker_channel",
        ]:
            assert f"async def {method}" in source

    def test_setup_exposes_dedicated_channel_actions(self):
        source = Path("app/cogs/setup.py").read_text(encoding="utf-8")
        for action_value in [
            "ask_channel",
            "lag_hunter_channel",
            "new_markets_channel",
            "curated_markets_channel",
            "arb_channel",
            "geo_channel",
            "copy_tracker_channel",
        ]:
            assert f'value="{action_value}"' in source

        for setter in [
            "set_ask_channel",
            "set_lag_hunter_channel",
            "set_new_markets_channel",
            "set_curated_markets_channel",
            "set_arb_channel",
            "set_geo_channel",
            "set_copy_tracker_channel",
        ]:
            assert setter in source

        assert 'value="alert"' not in source
        assert 'value="query"' not in source
        assert 'value="newmarkets"' not in source
        assert 'value="curated"' not in source
        assert 'value="geo"' not in source
        assert 'value="copytracker"' not in source

    def test_setup_status_reads_dedicated_channel_fields(self):
        source = Path("app/cogs/setup.py").read_text(encoding="utf-8")
        status_body = source.split('if action_value == "status":', 1)[1].split(
            'if action_value == "ask_channel":', 1
        )[0]
        for field in [
            "config.ask_channel_id",
            "config.lag_hunter_channel_id",
            "config.new_markets_channel_id",
            "config.curated_markets_channel_id",
            "config.arb_channel_id",
            "config.geo_channel_id",
            "config.copy_tracker_channel_id",
        ]:
            assert field in status_body

        assert "config.alert_channel_id" not in status_body
        assert "config.query_channel_id" not in status_body
        assert "config.curated_channel_id" not in status_body
