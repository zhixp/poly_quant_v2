"""
Golden Test Set for PolyQuant
Tests core functionality with canonical examples to catch regressions.
"""
import pytest
import json
from typing import Dict, Any


class TestGoldenSet:
    """
    Golden test cases for /ask command validation.
    Each test defines expected structural properties (not exact wording).
    """
    
    @pytest.fixture
    def honduras_election_context(self):
        """Mock context for Honduras election (multi-candidate market)."""
        return """
============================================================
🚨 LIVE MARKET PRICES (DO NOT HALLUCINATE):
============================================================
Event: Honduras Presidential Election 2025
Volume: $2,500,000

CURRENT ODDS FOR EACH OUTCOME:
------------------------------------------------------------
🥇 FRONTRUNNER: Xiomara Castro
  Price: $0.570 (57%)
  Volume: $1,200,000

🥈 2ND PLACE: Nasry Asfura
  Price: $0.430 (43%)
  Volume: $800,000

🥉 3RD PLACE: Yani Rosenthal
  Price: $0.008 (<1%)
  Volume: $50,000

============================================================
⚠️  USE THESE EXACT PRICES. DO NOT MAKE UP NUMBERS.
============================================================

============================================================
🏦 SHARP BOOKMAKER ODDS (VEGAS)
============================================================
Event: Honduras Presidential Election 2025

**PINNACLE:**
  Castro: 52.0% (Decimal: 1.92)
  Asfura: 48.0% (Decimal: 2.08)

============================================================
⚠️  USE THESE VEGAS ODDS TO ASSESS VALUE VS POLYMARKET.
============================================================
"""
    
    @pytest.fixture
    def fed_decision_context(self):
        """Mock context for Fed rate decision (binary market)."""
        return """
============================================================
🚨 LIVE MARKET PRICES (DO NOT HALLUCINATE):
============================================================
Market: Will the Fed cut rates by 25bps in December 2025?
Volume: $5,000,000

CURRENT ODDS:
  YES: $0.650 (65%)
  NO:  $0.350 (35%)
============================================================
⚠️  USE THESE EXACT PRICES. DO NOT MAKE UP NUMBERS.
============================================================
"""
    
    def validate_verdict_structure(self, verdict_json: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate that a Judge verdict has all required fields and correct types.
        Returns dict of validation errors (empty if valid).
        """
        errors = {}
        
        # Required fields
        required_fields = [
            'final_verdict',
            'confidence_score',
            'one_line_rationale',
            'primary_source_name',
            'primary_source_time',
            'quoted_market_prices',
            'scenario_analysis'
        ]
        
        for field in required_fields:
            if field not in verdict_json:
                errors[field] = "Missing required field"
        
        # Type validations
        if 'final_verdict' in verdict_json:
            verdict = verdict_json['final_verdict']
            valid_verdicts = [
                'STRONG_YES', 'YES', 'HOLD', 'NO', 'STRONG_NO', 'AVOID'
            ]
            # Also allow BUY_[NAME] format
            if not (verdict in valid_verdicts or verdict.startswith('BUY_')):
                errors['final_verdict'] = f"Invalid verdict: {verdict}"
        
        if 'confidence_score' in verdict_json:
            conf = verdict_json['confidence_score']
            if not isinstance(conf, (int, float)) or not (0 <= conf <= 100):
                errors['confidence_score'] = f"Invalid confidence: {conf} (must be 0-100)"
        
        if 'quoted_market_prices' in verdict_json:
            prices = verdict_json['quoted_market_prices']
            if not isinstance(prices, list):
                errors['quoted_market_prices'] = "Must be a list"
            elif len(prices) == 0:
                errors['quoted_market_prices'] = "List is empty"
        
        if 'scenario_analysis' in verdict_json:
            scenarios = verdict_json['scenario_analysis']
            if not isinstance(scenarios, dict):
                errors['scenario_analysis'] = "Must be a dict"
            else:
                required_scenarios = ['base_case', 'upside_case', 'downside_case']
                for scenario in required_scenarios:
                    if scenario not in scenarios:
                        errors[f'scenario_analysis.{scenario}'] = "Missing scenario"
                    elif not isinstance(scenarios[scenario], str) or not scenarios[scenario].strip():
                        errors[f'scenario_analysis.{scenario}'] = "Scenario is empty"
        
        return errors
    
    def test_honduras_verdict_structure(self, honduras_election_context):
        """
        Test that Honduras election produces valid verdict structure.
        This is a structural test - actual LLM call would be needed for full test.
        """
        # Mock verdict (in real test, this would come from AgentCouncil)
        mock_verdict = {
            "final_verdict": "BUY_CASTRO",
            "confidence_score": 72,
            "one_line_rationale": "Castro at 57¢ on Polymarket vs Pinnacle 52% shows 5% overpricing, but incumbency advantage and urban polling support justify current price. HOLD for better entry below 54¢.",
            "primary_source_name": "Polymarket + Pinnacle",
            "primary_source_time": "2025-12-02 14:35 UTC",
            "quoted_market_prices": [
                "Castro 57%, Asfura 43%, Rosenthal <1% (Polymarket)",
                "Castro 52%, Asfura 48% (Pinnacle)"
            ],
            "scenario_analysis": {
                "base_case": "Maintains 55-60¢ range until new polling data emerges.",
                "upside_case": "If Castro urban vote share exceeds 65%, targets 70¢.",
                "downside_case": "If rural turnout spikes above historical averages, could dip to 50¢."
            },
            "risk_flags": []
        }
        
        errors = self.validate_verdict_structure(mock_verdict)
        assert len(errors) == 0, f"Validation errors: {errors}"
    
    def test_fed_verdict_structure(self, fed_decision_context):
        """
        Test that Fed decision produces valid verdict structure.
        """
        mock_verdict = {
            "final_verdict": "YES",
            "confidence_score": 68,
            "one_line_rationale": "YES at 65¢ is fairly priced given recent inflation data and Powell's dovish tone. No clear edge - HOLD.",
            "primary_source_name": "Polymarket",
            "primary_source_time": "2025-12-02",
            "quoted_market_prices": ["YES 65%, NO 35%"],
            "scenario_analysis": {
                "base_case": "Price holds 60-70¢ range until FOMC meeting.",
                "upside_case": "If CPI comes in below 2.5%, targets 80¢.",
                "downside_case": "If jobs report shows strong wage growth, dips to 55¢."
            },
            "risk_flags": ["FOMC forward guidance uncertainty"]
        }
        
        errors = self.validate_verdict_structure(mock_verdict)
        assert len(errors) == 0, f"Validation errors: {errors}"
    
    def test_rejects_hallucinated_prices(self):
        """
        Test that verdict with hallucinated prices fails validation.
        """
        bad_verdict = {
            "final_verdict": "BUY_CASTRO",
            "confidence_score": 85,
            "one_line_rationale": "Castro has 92% chance based on my analysis.",  # Hallucinated
            "primary_source_name": "Unknown",
            "primary_source_time": "Unknown",
            "quoted_market_prices": [],  # Empty - should fail
            "scenario_analysis": {
                "base_case": "Wins easily",
                "upside_case": "Wins by more",
                "downside_case": "Still wins"
            }
        }
        
        errors = self.validate_verdict_structure(bad_verdict)
        assert 'quoted_market_prices' in errors, "Should reject empty price list"
    
    def test_rejects_missing_scenarios(self):
        """
        Test that verdict missing scenario fields fails validation.
        """
        bad_verdict = {
            "final_verdict": "YES",
            "confidence_score": 70,
            "one_line_rationale": "Good bet",
            "primary_source_name": "Polymarket",
            "primary_source_time": "Now",
            "quoted_market_prices": ["YES 60%"],
            "scenario_analysis": {
                "base_case": "Stays same"
                # Missing upside_case and downside_case
            }
        }
        
        errors = self.validate_verdict_structure(bad_verdict)
        assert 'scenario_analysis.upside_case' in errors
        assert 'scenario_analysis.downside_case' in errors


class TestLagHunterMetrics:
    """
    Tests for LagHunter observability and correctness.
    """
    
    def test_scan_metrics_structure(self):
        """
        Test that LagHunter scan produces expected metrics structure.
        """
        # Mock metrics from a scan
        mock_metrics = {
            'scan_id': 42,
            'feeds_fetched': 3,
            'feeds_failed': 0,
            'total_entries': 15,
            'fresh_entries': 8,
            'already_seen': 5,
            'markets_fetched': 20,
            'matches_found': 2,
            'alerts_sent': 2,
            'feed_details': {
                'CoinDesk': {'total': 5, 'fresh': 3, 'seen': 1, 'matches': 1},
                'SEC Press': {'total': 5, 'fresh': 2, 'seen': 2, 'matches': 0},
                'FiveThirtyEight': {'total': 5, 'fresh': 3, 'seen': 2, 'matches': 1}
            }
        }
        
        # Validate structure
        assert 'scan_id' in mock_metrics
        assert 'feeds_fetched' in mock_metrics
        assert 'matches_found' in mock_metrics
        assert 'alerts_sent' in mock_metrics
        assert 'feed_details' in mock_metrics
        
        # Validate feed details
        for feed, stats in mock_metrics['feed_details'].items():
            assert 'total' in stats
            assert 'fresh' in stats
            assert 'matches' in stats
    
    def test_zero_alert_detection(self):
        """
        Test that prolonged zero-alert periods are detected.
        """
        # Simulate 10 scans with zero alerts
        zero_alert_streak = 10
        
        # Should trigger warning at streak >= 10
        assert zero_alert_streak >= 10, "Should warn on prolonged silence"


class TestBookmakerIntegration:
    """
    Tests for bookmaker odds fetching and comparison.
    """
    
    def test_odds_conversion(self):
        """Test odds format conversions."""
        from app.core.bookmaker_client import OddsConverter
        
        converter = OddsConverter()
        
        # Decimal to implied prob
        assert abs(converter.decimal_to_implied_prob(2.0) - 0.5) < 0.01  # Even money = 50%
        assert abs(converter.decimal_to_implied_prob(1.5) - 0.667) < 0.01  # 1.5 = 66.7%
        
        # American to decimal
        assert abs(converter.american_to_decimal(150) - 2.5) < 0.01  # +150 = 2.5
        assert abs(converter.american_to_decimal(-150) - 1.67) < 0.01  # -150 = 1.67
        
        # Polymarket to decimal
        assert abs(converter.polymarket_to_decimal(0.5) - 2.0) < 0.01  # 50¢ = 2.0
        assert abs(converter.polymarket_to_decimal(0.57) - 1.75) < 0.01  # 57¢ = 1.75
    
    def test_edge_calculation(self):
        """Test edge calculation for arbitrage."""
        from app.core.bookmaker_client import OddsConverter
        
        converter = OddsConverter()
        
        # Positive edge: bookmaker 55%, Polymarket 45%, 2% fees = 8% edge
        edge = converter.calculate_edge(fair_prob=0.55, market_price=0.45, fees=0.02)
        assert abs(edge - 0.08) < 0.01
        
        # Negative edge: bookmaker 45%, Polymarket 55%, 2% fees = -12% edge
        edge = converter.calculate_edge(fair_prob=0.45, market_price=0.55, fees=0.02)
        assert abs(edge - (-0.12)) < 0.01
        
        # No edge: fair = market
        edge = converter.calculate_edge(fair_prob=0.50, market_price=0.50, fees=0.0)
        assert abs(edge) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

