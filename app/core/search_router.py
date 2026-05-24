"""
Unified search router for PolyQuant.
Waterfall strategy: Serper -> Tavily -> DuckDuckGo.
All results normalized into a shared schema.
"""
import asyncio
import logging
from typing import List, Dict, Optional

import aiohttp

from app.config import Config

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

logger = logging.getLogger("SearchRouter")


class SerperHydra:
    """Round-robin Serper.dev client with key rotation."""

    SEARCH_URL = "https://google.serper.dev/search"

    def __init__(self, api_keys: List[str]):
        self.keys = api_keys or []
        self._index = 0

    @property
    def has_keys(self) -> bool:
        return bool(self.keys)

    def _next_key(self) -> Optional[str]:
        if not self.keys:
            return None
        key = self.keys[self._index]
        self._index = (self._index + 1) % len(self.keys)
        return key

    async def search(self, query: str, max_results: int = 5) -> List[Dict]:
        api_key = self._next_key()
        if not api_key:
            return []

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": max_results}

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(self.SEARCH_URL, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(f"Serper returned {resp.status}: {text[:120]}")
                        return []
                    data = await resp.json()
        except Exception as exc:
            logger.warning(f"Serper request failed: {exc}")
            return []

        results = []
        organic = data.get("organic", []) or []
        news = data.get("news", []) or []

        for item in organic[:max_results]:
            results.append({
                "title": item.get("title", "Untitled result"),
                "url": item.get("link") or item.get("url"),
                "content": item.get("snippet") or item.get("summary") or "",
                "source": "Serper/Google",
            })

        for item in news[: max(0, max_results - len(results))]:
            results.append({
                "title": item.get("title", "News result"),
                "url": item.get("link") or item.get("url"),
                "content": (item.get("snippet") or item.get("summary") or ""),
                "source": item.get("source") or "Serper News",
            })

        return results


class SearchRouter:
    """
    Performs cascading search across Serper, Tavily, and DuckDuckGo.
    Returns normalized result dictionaries to simplify downstream usage.
    """

    def __init__(self):
        self.serper = SerperHydra(Config.SERPER_KEYS)
        self.tavily = None
        if Config.TAVILY_API_KEY and TavilyClient:
            try:
                self.tavily = TavilyClient(api_key=Config.TAVILY_API_KEY)
            except Exception as exc:
                logger.warning(f"Failed to initialize Tavily client: {exc}")
        if not TavilyClient and Config.TAVILY_API_KEY:
            logger.warning("tavily library not installed; Tavily search disabled")

        if DDGS:
            try:
                self.ddg = DDGS()
            except Exception as exc:
                logger.warning(f"Failed to initialize DuckDuckGo search: {exc}")
                self.ddg = None
        else:
            self.ddg = None

    async def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Return normalized search results."""
        if self.serper.has_keys:
            serper_results = await self.serper.search(query, max_results)
            if serper_results:
                return serper_results

        tavily_results = await self._search_tavily(query, max_results)
        if tavily_results:
            return tavily_results

        ddg_results = await self._search_ddg(query, max_results)
        if ddg_results:
            return ddg_results

        return []

    async def deep_search(self, query: str, max_results: int = 5) -> str:
        """Legacy interface: returns formatted string for prompts."""
        results = await self.search(query, max_results)
        if not results:
            return ""

        lines = [
            "=" * 60,
            "📰 EXTERNAL INTEL",
            "=" * 60,
        ]
        for idx, item in enumerate(results, start=1):
            lines.append(f"{idx}. {item['title']} ({item['source']})")
            if item.get("url"):
                lines.append(f"URL: {item['url']}")
            if item.get("content"):
                snippet = item["content"]
                if len(snippet) > 500:
                    snippet = snippet[:500] + "..."
                lines.append(snippet)
            lines.append("")

        return "\n".join(lines).strip()

    async def _search_tavily(self, query: str, max_results: int) -> List[Dict]:
        if not self.tavily:
            return []

        def run_search():
            return self.tavily.search(query=query, search_depth="basic", max_results=max_results)

        try:
            response = await asyncio.to_thread(run_search)
        except Exception as exc:
            logger.warning(f"Tavily search failed: {exc}")
            return []

        normalized = []
        for item in response.get("results", []):
            normalized.append({
                "title": item.get("title") or "Tavily result",
                "url": item.get("url"),
                "content": item.get("content") or "",
                "source": item.get("source") or "Tavily",
            })
            if len(normalized) >= max_results:
                break
        return normalized

    async def _search_ddg(self, query: str, max_results: int) -> List[Dict]:
        if not self.ddg:
            return []

        def run_search():
            return list(self.ddg.text(query, max_results=max_results))

        try:
            results = await asyncio.to_thread(run_search)
        except Exception as exc:
            logger.warning(f"DuckDuckGo search failed: {exc}")
            return []

        normalized = []
        for item in results:
            normalized.append({
                "title": item.get("title") or "DuckDuckGo result",
                "url": item.get("href"),
                "content": item.get("body") or "",
                "source": "DuckDuckGo",
            })
        return normalized

