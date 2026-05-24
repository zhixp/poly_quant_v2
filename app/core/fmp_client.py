"""Financial Modeling Prep client for macro + earnings data."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from app.config import Config

logger = logging.getLogger("FMPClient")


class FMPClient:
    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self):
        self.api_key = Config.FMP_API_KEY

    def _auth_params(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("FMP API key not configured")
        return {"apikey": self.api_key}

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if params is None:
            params = {}
        try:
            params.update(self._auth_params())
        except ValueError:
            logger.warning("FMP API key missing; skipping request")
            return []

        url = f"{self.BASE_URL}/{path}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(f"FMP request failed ({resp.status}): {text[:120]}")
                        return []
                    return await resp.json()
        except Exception as exc:
            logger.warning(f"FMP request error: {exc}")
            return []

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        symbol = (symbol or "").upper().strip()
        if not symbol:
            return {}
        data = await self._get(f"quote/{symbol}")
        if isinstance(data, list) and data:
            return data[0]
        return {}

    async def get_earnings_calendar(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        start = datetime.utcnow().strftime("%Y-%m-%d")
        end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        params = {"from": start, "to": end, "limit": 50}
        data = await self._get("earning_calendar", params)
        return data if isinstance(data, list) else []

    async def get_economic_calendar(self, days_back: int = 1, days_ahead: int = 1) -> List[Dict[str, Any]]:
        start = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        params = {"from": start, "to": end, "limit": 200}
        data = await self._get("economic_calendar", params)
        return data if isinstance(data, list) else []


fmp_client = FMPClient()

